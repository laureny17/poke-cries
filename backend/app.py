"""
Flask API for Pokémon Cry Similarity.
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import os
from pathlib import Path
import json
import numpy as np
from src.data_pipeline import (
    build_similarity_matrix,
    get_generation_pokemon,
    load_similarity_data,
    save_similarity_data,
    get_pokemon_info,
)
from src.pokeapi_client import get_pokemon_data, get_pokemon_species
from src.similarity import get_similar_pokemon, normalize_similarity, compute_distance
from src.similarity import compute_overview_layout

app = Flask(__name__)

# Allow local dev frontends explicitly.
cors_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173",
).split(",")
CORS(
    app,
    resources={r"/api/*": {"origins": [origin.strip() for origin in cors_origins]}},
)

# Global state
similarity_data = None
DATA_FILE = Path(__file__).parent / "data" / "similarity_data.json"


def _calibrate_similarity_scores(scores: list[float]) -> dict[float, float]:
    """Spread tightly-clustered cosine scores into a more useful visual range."""
    if not scores:
        return {}

    arr = np.array(scores, dtype=float)
    mean = float(np.mean(arr))
    std = float(np.std(arr))

    # Handle degenerate case where all similarities are effectively identical.
    if std < 1e-8:
        return {score: 0.5 for score in scores}

    scaled = {}
    for score in scores:
        z = (score - mean) / (std * 1.5)
        # Sigmoid maps to (0, 1) and amplifies small differences around the mean.
        calibrated = 1.0 / (1.0 + np.exp(-z))
        scaled[score] = float(calibrated)

    return scaled


def load_data():
    """Load similarity data into memory."""
    global similarity_data
    if similarity_data is None and DATA_FILE.exists():
        similarity_data = load_similarity_data(DATA_FILE)
        if similarity_data is not None and not similarity_data.get("overview_layout"):
            overview_layout = compute_overview_layout(
                list(similarity_data.get("pokemon_info", {}).keys()),
                similarity_data.get("similarities", {}),
            )
            similarity_data["overview_layout"] = overview_layout
            save_similarity_data(similarity_data, DATA_FILE)


@app.route("/api/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok"})


@app.route("/api/pokemon", methods=["GET"])
def get_pokemon_list():
    """
    Get list of all Pokémon with their data.

    Query parameters:
    - generation: Filter by generation (1-9)
    - limit: Maximum number to return
    """
    load_data()

    if similarity_data is None:
        return jsonify({"error": "No similarity data loaded"}), 503

    generation = request.args.get("generation", type=int)
    limit = request.args.get("limit", type=int, default=100)

    pokemon_list = []

    for pid, info in similarity_data["pokemon_info"].items():
        # Filter by generation if specified
        if generation:
            gen_name = info.get("generation", "")
            if f"generation-{generation}" not in gen_name:
                continue

        pokemon_list.append({
            "id": pid,
            **info,
        })

        if len(pokemon_list) >= limit:
            break

    return jsonify(pokemon_list)


@app.route("/api/pokemon/<int:pokemon_id>", methods=["GET"])
def get_pokemon(pokemon_id: int):
    """Get details for a specific Pokémon."""
    load_data()

    # Prefer cached matrix info when available.
    info = None
    if similarity_data is not None:
        info = similarity_data.get("pokemon_info", {}).get(pokemon_id)

    # Fallback to live fetch from PokéAPI/cache if missing.
    pokemon_data = get_pokemon_data(pokemon_id)
    species_data = get_pokemon_species(pokemon_id)
    if not pokemon_data or not species_data:
        return jsonify({"error": "Pokémon not found"}), 404

    flavor_entries = species_data.get("flavor_text_entries", [])
    description = ""
    for entry in flavor_entries:
        language = entry.get("language", {}).get("name")
        if language == "en":
            description = entry.get("flavor_text", "")
            description = description.replace("\n", " ").replace("\f", " ").strip()
            if description:
                break

    habitat = species_data.get("habitat", {}).get("name") if species_data.get("habitat") else None
    cries = pokemon_data.get("cries", {})

    details = {
        "id": pokemon_id,
        "name": pokemon_data.get("name", ""),
        "height": pokemon_data.get("height", 0),
        "weight": pokemon_data.get("weight", 0),
        "sprite_url": pokemon_data.get("sprites", {}).get("front_default"),
        "generation": species_data.get("generation", {}).get("name", ""),
        "types": [t.get("type", {}).get("name") for t in pokemon_data.get("types", []) if t.get("type")],
        "habitat": habitat,
        "description": description,
        "cry_url": cries.get("latest"),
        "cry_url_legacy": cries.get("legacy"),
    }

    if info:
        details = {**details, **info, **{"habitat": habitat, "description": description, "cry_url": cries.get("latest"), "cry_url_legacy": cries.get("legacy")}}

    return jsonify(details)


@app.route("/api/similarity/<int:pokemon_id>", methods=["GET"])
def get_similarity_neighbors(pokemon_id: int):
    """
    Get Pokémon most similar to the given Pokémon.

    Query parameters:
    - top_k: Number of similar Pokémon to return (default 20)
    - min_similarity: Minimum similarity threshold (0-1, default 0.5)
    """
    load_data()

    if similarity_data is None:
        return jsonify({"error": "No similarity data loaded"}), 503

    if pokemon_id not in similarity_data["pokemon_info"]:
        return jsonify({"error": "Pokémon not found"}), 404

    top_k = request.args.get("top_k", type=int, default=20)
    min_similarity = request.args.get("min_similarity", type=float, default=0.5)

    similar = get_similar_pokemon(
        pokemon_id,
        similarity_data["similarities"],
        top_k=top_k,
        min_similarity=0.0,
    )

    # Build a calibration map from all available neighbors for this pokemon.
    all_neighbor_scores = [
        score
        for (pid1, pid2), score in similarity_data["similarities"].items()
        if pid1 == pokemon_id and pid2 != pokemon_id
    ]
    calibration_map = _calibrate_similarity_scores(all_neighbor_scores)

    result = []
    for neighbor_id, score in similar:
        calibrated_score = calibration_map.get(score, score)
        if calibrated_score < min_similarity:
            continue

        if neighbor_id in similarity_data["pokemon_info"]:
            info = similarity_data["pokemon_info"][neighbor_id]
            result.append({
                "id": neighbor_id,
                "similarity": float(calibrated_score),
                "raw_similarity": float(score),
                "distance": compute_distance(calibrated_score),
                **info,
            })

    return jsonify(result)


@app.route("/api/similarity-matrix", methods=["GET"])
def get_similarity_matrix():
    """
    Get the complete similarity matrix for visualization.

    Query parameters:
    - generation: Filter by generation (1-9)
    - min_similarity: Minimum similarity threshold (0-1)
    """
    load_data()

    if similarity_data is None:
        return jsonify({"error": "No similarity data loaded"}), 503

    generation = request.args.get("generation", type=int)
    min_similarity = request.args.get("min_similarity", type=float, default=0.0)

    # Filter Pokémon by generation if specified
    filtered_pokemon = {}
    for pid, info in similarity_data["pokemon_info"].items():
        if generation:
            gen_name = info.get("generation", "")
            if f"generation-{generation}" not in gen_name:
                continue
        filtered_pokemon[pid] = info

    # Build nodes
    nodes = []
    pid_to_idx = {}
    for idx, (pid, info) in enumerate(filtered_pokemon.items()):
        pid_to_idx[pid] = idx
        nodes.append({
            "id": idx,
            "pokemon_id": pid,
            "overview_x": similarity_data.get("overview_layout", {}).get(pid, {}).get("x"),
            "overview_y": similarity_data.get("overview_layout", {}).get(pid, {}).get("y"),
            **info,
        })

    # Build links (edges only above min_similarity)
    links = []
    for (pid1, pid2), score in similarity_data["similarities"].items():
        if score < min_similarity:
            continue

        if pid1 not in pid_to_idx or pid2 not in pid_to_idx:
            continue

        if pid1 < pid2:  # Avoid duplicates
            links.append({
                "source": pid_to_idx[pid1],
                "target": pid_to_idx[pid2],
                "similarity": float(score),
                "distance": compute_distance(score),
            })

    return jsonify({
        "nodes": nodes,
        "links": links,
    })


@app.route("/api/generations", methods=["GET"])
def get_generations():
    """Get list of available generations."""
    generations = []
    for gen_id in range(1, 10):
        pokemon_ids = get_generation_pokemon(gen_id)
        if pokemon_ids:
            generations.append({
                "id": gen_id,
                "name": f"Generation {gen_id}",
                "pokemon_count": len(pokemon_ids),
            })

    return jsonify(generations)


@app.route("/api/admin/build-matrix", methods=["POST"])
def build_similarity_matrix_endpoint():
    """
    Build the similarity matrix (computationally expensive).

    POST data:
    - generation: Generation to build for (default: all)
    - force: Force rebuild even if cached
    """
    generation = request.json.get("generation")
    force = request.json.get("force", False)

    # Check if already built
    if not force and DATA_FILE.exists():
        return jsonify({"error": "Data already built. Set force=true to rebuild"}), 400

    try:
        if generation:
            pokemon_ids = get_generation_pokemon(generation)
        else:
            # Get all Pokémon
            pokemon_ids = list(range(1, 1026))  # All Pokémon up to Gen 9

        data = build_similarity_matrix(pokemon_ids)
        save_similarity_data(data, DATA_FILE)

        # Reload into memory
        global similarity_data
        similarity_data = data

        return jsonify({
            "success": True,
            "pokemon_count": len(data["pokemon_info"]),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    load_data()
    port = int(os.getenv("PORT", "8000"))
    app.run(debug=True, host="0.0.0.0", port=port)
