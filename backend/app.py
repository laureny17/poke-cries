# using Flask API for pokemon cry similarity

from flask import Flask, jsonify, request
from flask_cors import CORS
import gzip
import os
import threading
import numpy as np
from src.pokeapi_client import get_pokemon_data, get_pokemon_species, load_from_cache
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
_load_lock = threading.Lock()
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
def _make_score_calibrator(all_scores: np.ndarray):
    if all_scores.size == 0:
        return lambda score: score

    mean = float(np.mean(all_scores))
    std = float(np.std(all_scores))

    # handle the degenerate case where all similarities are basically the same
    if std < 1e-8:
        return lambda score: 0.5

    def calibrate(score: float) -> float:
        z = (score - mean) / (std * 1.5)
        # sigmoid maps to (0, 1) and makes tiny gaps around the mean easier to see
        return float(1.0 / (1.0 + np.exp(-z)))

    return calibrate


def _compute_distance(similarity: float) -> float:
    # same as src.similarity.compute_distance, inlined so request handlers don't
    # import the audio/ml stack (librosa, scipy, sklearn) into the web process
    similarity = max(0.0, min(1.0, similarity))
    return 1.0 / (1.0 + (10.0 * similarity))


def _sorted_desc(scores: np.ndarray) -> np.ndarray:
    # stable descending sort; NaN (no score for that pair) sorts last
    keys = np.where(np.isnan(scores), np.inf, -scores)
    return np.argsort(keys, kind="stable", axis=-1)


def _submatrix(pids: list[int]) -> np.ndarray:
    indices = [similarity_data["index_by_id"][pid] for pid in pids]
    return similarity_data["similarity_matrix"][np.ix_(indices, indices)]


def _matches_generation(gen_name: str, generation: int) -> bool:
    expected_roman = GENERATION_ROMAN.get(generation)
    return gen_name in {f"generation-{generation}", f"generation-{expected_roman}"}


def _cry_urls_for_pokemon(pokemon_id: int) -> dict:
    base_url = "https://raw.githubusercontent.com/PokeAPI/cries/main/cries/pokemon"
    return {
        "cry_url": f"{base_url}/latest/{pokemon_id}.ogg",
        "cry_url_legacy": f"{base_url}/legacy/{pokemon_id}.ogg",
        "cry_url_latest": f"{base_url}/latest/{pokemon_id}.ogg",
    }


def _details_from_cached_info(pokemon_id: int, info: dict) -> dict:
    pokemon_cache = load_from_cache("pokemon", str(pokemon_id)) or {}
    species_cache = load_from_cache("pokemon-species", str(pokemon_id)) or {}

    habitat = species_cache.get("habitat", {}).get("name") if species_cache.get("habitat") else None
    description = ""
    for entry in species_cache.get("flavor_text_entries", []):
        if entry.get("language", {}).get("name") == "en":
            description = entry.get("flavor_text", "")
            description = description.replace("\n", " ").replace("\f", " ").strip()
            if description:
                break

    cries = pokemon_cache.get("cries", {})
    cry_urls = _cry_urls_for_pokemon(pokemon_id)
    cry_url_legacy = cries.get("legacy") or cry_urls["cry_url_legacy"]
    cry_url_latest = cries.get("latest") or cry_urls["cry_url_latest"]

    return {
        **info,
        "id": pokemon_id,
        "habitat": habitat,
        "description": description,
        "cry_url": cry_url_latest or cry_url_legacy,
        "cry_url_legacy": cry_url_legacy,
        "cry_url_latest": cry_url_latest,
    }

# load similarity data into memory
def load_data():
    global similarity_data
    if similarity_data is not None or not DATA_FILE.exists():
        return
    # gunicorn runs several threads; make sure only one of them loads the data
    with _load_lock:
        if similarity_data is None:
            similarity_data = load_similarity_data(DATA_FILE)


@app.after_request
def _gzip_response(response):
    # the overview payload is ~1.2 MB of json; gzip shrinks it ~6x, which means
    # faster loads and less time holding the response in memory
    if (
        response.status_code != 200
        or response.direct_passthrough
        or response.mimetype != "application/json"
        or "Content-Encoding" in response.headers
        or "gzip" not in request.headers.get("Accept-Encoding", "").lower()
    ):
        return response

    payload = response.get_data()
    if len(payload) < 1024:
        return response

    response.set_data(gzip.compress(payload, compresslevel=6))
    response.headers["Content-Encoding"] = "gzip"
    response.vary.add("Accept-Encoding")
    return response


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
    if info:
        return jsonify(_details_from_cached_info(pokemon_id, info))

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

    if (
        pokemon_id not in similarity_data["pokemon_info"]
        or pokemon_id not in similarity_data["index_by_id"]
    ):
        return jsonify({"error": "Pokémon not found"}), 404

    top_k = request.args.get("top_k", type=int, default=20)
    min_similarity = request.args.get("min_similarity", type=float, default=0.5)

    ids = similarity_data["ids"]
    row_index = similarity_data["index_by_id"][pokemon_id]
    row = similarity_data["similarity_matrix"][row_index].copy()
    row[row_index] = np.nan  # never list a pokemon as its own neighbor
    has_score = ~np.isnan(row)

    # build a calibration from all available neighbors for this pokemon
    # so we can spread out the scores more evenly for visualization purposes
    calibrate = _make_score_calibrator(row[has_score])

    row[has_score & (row < 0.0)] = np.nan
    order = _sorted_desc(row)[: max(0, min(top_k, int(np.count_nonzero(row >= 0.0))))]
    similar = [(ids[index], float(row[index])) for index in order]

    result = []
    for neighbor_id, score in similar:
        calibrated_score = calibrate(score)
        if calibrated_score < min_similarity:
            continue

        if neighbor_id in similarity_data["pokemon_info"]:
            info = similarity_data["pokemon_info"][neighbor_id]
            result.append({
                "id": neighbor_id,
                "similarity": float(calibrated_score),
                "raw_similarity": float(score),
                "distance": _compute_distance(calibrated_score),
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
    - include_links: whether to include matrix edges (true/false, default true)
    """
    load_data()

    if similarity_data is None:
        return jsonify({"error": "No similarity data loaded"}), 503

    generation = request.args.get("generation", type=int)
    min_similarity = request.args.get("min_similarity", type=float, default=0.0)
    include_links = request.args.get("include_links", default="true").lower() not in {
        "0",
        "false",
        "no",
    }

    # filter pokemon by generation first
    filtered_pokemon = {}
    for pid, info in similarity_data["pokemon_info"].items():
        if generation:
            gen_name = info.get("generation", "")
            if not _matches_generation(gen_name, generation):
                continue
        filtered_pokemon[pid] = info

    # pokemon that have a row in the similarity matrix, in ascending id order
    matrix_pids = sorted(
        pid for pid in filtered_pokemon if pid in similarity_data["index_by_id"]
    )
    sub = _submatrix(matrix_pids)

    if generation:
        # heavy import (sklearn etc.), only needed for per-generation layouts
        from src.similarity import compute_overview_layout

        sub_similarities = {
            (pid1, pid2): float(sub[i, j])
            for i, pid1 in enumerate(matrix_pids)
            for j, pid2 in enumerate(matrix_pids)
            if not np.isnan(sub[i, j])
        }
        vector_matrix = similarity_data["vector_matrix"]
        vectors = {
            pid: vector_matrix[index]
            for index, pid in enumerate(similarity_data["vector_ids"])
        }
        overview_layout = compute_overview_layout(
            list(filtered_pokemon.keys()),
            sub_similarities,
            vectors,
        )
        del sub_similarities
    else:
        overview_layout = similarity_data.get("overview_layout", {})

    nearest_neighbors_by_pid = {pid: [] for pid in filtered_pokemon}
    if matrix_pids:
        neighbor_scores = sub.copy()
        np.fill_diagonal(neighbor_scores, np.nan)
        top_neighbors = _sorted_desc(neighbor_scores)[:, :16]
        for row_index, source_id in enumerate(matrix_pids):
            row = neighbor_scores[row_index]
            nearest_neighbors_by_pid[source_id] = [
                {
                    "pokemon_id": matrix_pids[col],
                    "similarity": float(row[col]),
                }
                for col in top_neighbors[row_index]
                if not np.isnan(row[col])
            ]
        del neighbor_scores, top_neighbors

    # build nodes for the frontend graph view
    nodes = []
    pid_to_idx = {}
    for idx, (pid, info) in enumerate(filtered_pokemon.items()):
        pid_to_idx[pid] = idx
        nodes.append({
            "id": idx,
            "pokemon_id": pid,
            "nearest_neighbors": nearest_neighbors_by_pid.get(pid, []),
            "overview_x": overview_layout.get(pid, {}).get("x"),
            "overview_y": overview_layout.get(pid, {}).get("y"),
            "representativeness": overview_layout.get(pid, {}).get("representativeness"),
            "cluster_id": overview_layout.get(pid, {}).get("cluster_id"),
            "cluster_size": overview_layout.get(pid, {}).get("cluster_size"),
            "cluster_representative_id": overview_layout.get(pid, {}).get("cluster_representative_id"),
            **info,
        })

    links = []
    if include_links and matrix_pids:
        # only keep edges that clear the similarity threshold; upper triangle
        # (pid1 < pid2) avoids duplicates
        rows, cols = np.triu_indices(len(matrix_pids), k=1)
        scores = sub[rows, cols]
        keep = ~np.isnan(scores) & (scores >= min_similarity)
        for i, j, score in zip(rows[keep], cols[keep], scores[keep]):
            score = float(score)
            links.append({
                "source": pid_to_idx[matrix_pids[i]],
                "target": pid_to_idx[matrix_pids[j]],
                "similarity": score,
                "distance": _compute_distance(score),
            })

    return jsonify({
        "nodes": nodes,
        "links": links,
    })


# get list of all generations along w/ counts of how many pokemon they have (for filtering UI)
@app.route("/generations", methods=["GET"])
@app.route("/api/generations", methods=["GET"])
def get_generations():
    load_data()

    if similarity_data is not None:
        # count from the loaded data instead of calling pokeapi and importing
        # the audio pipeline on every request
        def get_generation_pokemon(gen_id: int) -> list[int]:
            return [
                pid
                for pid, info in similarity_data["pokemon_info"].items()
                if _matches_generation(info.get("generation", ""), gen_id)
            ]
    else:
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
        pokemon_count = len(data["pokemon_info"])
        del data

        # reload into memory so the next request sees the fresh matrix
        global similarity_data
        with _load_lock:
            similarity_data = load_similarity_data(DATA_FILE)

        return jsonify({
            "success": True,
            "pokemon_count": pokemon_count,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# load at worker start so the first visitor doesn't wait on it
load_data()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(
        debug=os.getenv("FLASK_DEBUG") == "1",
        host="0.0.0.0",
        port=port,
        use_reloader=False,
    )
