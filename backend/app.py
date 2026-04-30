# using Flask API for pokemon cry similarity

from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import numpy as np
from src.pokeapi_client import get_pokemon_data, get_pokemon_species
from src.data_store import DATA_FILE, load_similarity_data, save_similarity_data

app = Flask(__name__)

# allow local dev frontends explicitly.
cors_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001,http://localhost:5173,http://127.0.0.1:5173,https://poke-cries.onrender.com",
).split(",")
CORS(
    app,
    resources={r"/*": {"origins": [origin.strip() for origin in cors_origins]}},
)

# global state for cached similarity data (keeps the app less comutationally intensive)
similarity_data = None
GENERATION_ROMAN = {
    1: "i",
    2: "ii",
    3: "iii",
    4: "iv",
    5: "v",
    6: "vi",
    7: "vii",
    8: "viii",
    9: "ix",
}


# spread tightly-clustered cosine scores into a range that is more visually useful for our visualization
def _calibrate_similarity_scores(scores: list[float]) -> dict[float, float]:
    if not scores:
        return {}

    arr = np.array(scores, dtype=float)
    mean = float(np.mean(arr))
    std = float(np.std(arr))

    # handle the degenerate case where all similarities are basically the same
    if std < 1e-8:
        return {score: 0.5 for score in scores}

    scaled = {}
    for score in scores:
        z = (score - mean) / (std * 1.5)
        # sigmoid maps to (0, 1) and makes tiny gaps around the mean easier to see
        calibrated = 1.0 / (1.0 + np.exp(-z))
        scaled[score] = float(calibrated)

    return scaled


def _matches_generation(gen_name: str, generation: int) -> bool:
    expected_roman = GENERATION_ROMAN.get(generation)
    return gen_name in {f"generation-{generation}", f"generation-{expected_roman}"}

# load similarity data into memory
def load_data():
    global similarity_data
    if similarity_data is None and DATA_FILE.exists():
        similarity_data = load_similarity_data(DATA_FILE)


# health check
@app.route("/health", methods=["GET"])
@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/pokemon", methods=["GET"])
@app.route("/api/pokemon", methods=["GET"])
def get_pokemon_list():
    """
    get list of all pokemon w/ their data

    params:
    - generation: filter by pokemon generation (1-9)
    - limit: max number to return
    """
    load_data()

    if similarity_data is None:
        return jsonify({"error": "No similarity data loaded"}), 503

    generation = request.args.get("generation", type=int)
    limit = request.args.get("limit", type=int, default=100)

    pokemon_list = []

    for pid, info in similarity_data["pokemon_info"].items():
        # skip entries outside the requested generation, if any
        if generation:
            gen_name = info.get("generation", "")
            if not _matches_generation(gen_name, generation):
                continue

        pokemon_list.append({
            "id": pid,
            **info,
        })

        if len(pokemon_list) >= limit:
            break

    return jsonify(pokemon_list)


@app.route("/pokemon/<int:pokemon_id>", methods=["GET"])
@app.route("/api/pokemon/<int:pokemon_id>", methods=["GET"])
def get_pokemon(pokemon_id: int):
    """get details for a specific pokémon."""
    load_data()

    # prefer cached matrix info when we already have it
    info = None
    if similarity_data is not None:
        info = similarity_data.get("pokemon_info", {}).get(pokemon_id)

    # fall back to live fetch from pokeapi/cache if the local data is missing
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
    preferred_cry_url = cries.get("legacy") or cries.get("latest")

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
        "cry_url": preferred_cry_url,
        "cry_url_legacy": cries.get("legacy"),
    }

    if info:
        details = {**details, **info, **{"habitat": habitat, "description": description, "cry_url": preferred_cry_url, "cry_url_legacy": cries.get("legacy")}}

    return jsonify(details)


@app.route("/similarity/<int:pokemon_id>", methods=["GET"])
@app.route("/api/similarity/<int:pokemon_id>", methods=["GET"])
def get_similarity_neighbors(pokemon_id: int):
    """
    get pokémon most similar to the given pokémon

    params:
    - top_k: number of similar pokemon to return (default 20)
    - min_similarity: minimum similarity threshold (0-1, default 0.5)
    """
    load_data()

    if similarity_data is None:
        return jsonify({"error": "No similarity data loaded"}), 503

    if pokemon_id not in similarity_data["pokemon_info"]:
        return jsonify({"error": "Pokémon not found"}), 404

    from src.similarity import compute_distance, get_similar_pokemon

    top_k = request.args.get("top_k", type=int, default=20)
    min_similarity = request.args.get("min_similarity", type=float, default=0.5)

    similar = get_similar_pokemon(
        pokemon_id,
        similarity_data["similarities"],
        top_k=top_k,
        min_similarity=0.0,
    )

    # build a calibration map from all available neighbors for this pokemon
    # so we can spread out the scores more evenly for visualization purposes
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


@app.route("/similarity-matrix", methods=["GET"])
@app.route("/api/similarity-matrix", methods=["GET"])
def get_similarity_matrix():
    """
    get the complete similarity matrix for visualization

    params:
    - generation: filter by generation (1-9)
    - min_similarity: minimum similarity threshold (0-1)
    """
    load_data()

    if similarity_data is None:
        return jsonify({"error": "No similarity data loaded"}), 503

    generation = request.args.get("generation", type=int)
    min_similarity = request.args.get("min_similarity", type=float, default=0.0)

    from src.similarity import compute_distance, compute_overview_layout

    # filter pokemon by generation first
    filtered_pokemon = {}
    for pid, info in similarity_data["pokemon_info"].items():
        if generation:
            gen_name = info.get("generation", "")
            if not _matches_generation(gen_name, generation):
                continue
        filtered_pokemon[pid] = info

    if generation:
        overview_layout = compute_overview_layout(
            list(filtered_pokemon.keys()),
            similarity_data.get("similarities", {}),
            similarity_data.get("vectors", {}),
        )
    else:
        overview_layout = similarity_data.get("overview_layout", {})

    # build nodes for the frontend graph view
    nodes = []
    pid_to_idx = {}
    for idx, (pid, info) in enumerate(filtered_pokemon.items()):
        pid_to_idx[pid] = idx
        nodes.append({
            "id": idx,
            "pokemon_id": pid,
            "overview_x": overview_layout.get(pid, {}).get("x"),
            "overview_y": overview_layout.get(pid, {}).get("y"),
            "representativeness": overview_layout.get(pid, {}).get("representativeness"),
            "cluster_id": overview_layout.get(pid, {}).get("cluster_id"),
            "cluster_size": overview_layout.get(pid, {}).get("cluster_size"),
            "cluster_representative_id": overview_layout.get(pid, {}).get("cluster_representative_id"),
            **info,
        })

    # only keep edges that clear the similarity threshold
    links = []
    for (pid1, pid2), score in similarity_data["similarities"].items():
        if score < min_similarity:
            continue

        if pid1 not in pid_to_idx or pid2 not in pid_to_idx:
            continue

        if pid1 < pid2:  # avoid duplicates
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


# get list of all generations along w/ counts of how many pokemon they have (for filtering UI)
@app.route("/generations", methods=["GET"])
@app.route("/api/generations", methods=["GET"])
def get_generations():
    from src.data_pipeline import get_generation_pokemon

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


@app.route("/admin/build-matrix", methods=["POST"])
@app.route("/api/admin/build-matrix", methods=["POST"])
def build_similarity_matrix_endpoint():
    """
    build the similarity matrix (computationally expensive!!)

    post data:
    - generation: the pokemon generation to build for (default: all)
    - force: force rebuild even if cached
    """
    generation = request.json.get("generation")
    force = request.json.get("force", False)

    from src.data_pipeline import build_similarity_matrix, get_generation_pokemon

    # skip rebuilds unless the caller explicitly forces one
    if not force and DATA_FILE.exists():
        return jsonify({"error": "Data already built. Set force=true to rebuild"}), 400

    try:
        if generation:
            pokemon_ids = get_generation_pokemon(generation)
        else:
            # otherwise rebuild the full set of pokémon ids
            pokemon_ids = list(range(1, 1026))  # all pokemon up to gen 9

        data = build_similarity_matrix(pokemon_ids)
        save_similarity_data(data, DATA_FILE)

        # reload into memory so the next request sees the fresh matrix
        global similarity_data
        similarity_data = data

        return jsonify({
            "success": True,
            "pokemon_count": len(data["pokemon_info"]),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(
        debug=os.getenv("FLASK_DEBUG") == "1",
        host="0.0.0.0",
        port=port,
        use_reloader=False,
    )
