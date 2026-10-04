"""
Lightweight persistence helpers for cached similarity data.

This module intentionally avoids importing the audio/similarity build stack so
the web server can start without pulling in the heavy ML dependencies.

similarity_data.json is the source of truth written by the build tools, but
parsing it into Python dicts costs ~280 MB of RAM (one tuple key + float object
per pair, in both directions). The web server instead loads a compact runtime
file (similarity_runtime.npz) that holds the same numbers as dense float64
numpy arrays (~15 MB in memory). The runtime file is regenerated whenever the
JSON changes.
"""

import hashlib
import json
from pathlib import Path
from typing import Dict, Optional

import numpy as np


DATA_DIR = Path(__file__).parent.parent / "data"
DATA_FILE = DATA_DIR / "similarity_data.json"
RUNTIME_FILE = DATA_DIR / "similarity_runtime.npz"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def save_similarity_data(data: Dict, output_file: Path = DATA_FILE) -> None:
    ensure_dirs()

    vectors_list = {}
    for pid, vector in data["vectors"].items():
        vectors_list[str(pid)] = vector.tolist()

    similarities = {}
    for (pid1, pid2), score in data["similarities"].items():
        key = f"{min(pid1, pid2)},{max(pid1, pid2)}"
        similarities[key] = score

    output_data = {
        "feature_version": data.get("feature_version"),
        "embedding_model": data.get("embedding_model"),
        "vectors": vectors_list,
        "similarities": similarities,
        "pokemon_info": data["pokemon_info"],
        "overview_layout": {
            str(pid): position
            for pid, position in data.get("overview_layout", {}).items()
        },
    }

    with open(output_file, "w") as file_handle:
        json.dump(output_data, file_handle)

    write_runtime_file(output_file)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _runtime_path_for(json_file: Path) -> Path:
    if json_file == DATA_FILE:
        return RUNTIME_FILE
    return json_file.with_name(f"{json_file.stem}_runtime.npz")


def _normalize_overview_layout(overview_layout_raw: Dict) -> Dict[int, Dict]:
    overview_layout = {}
    for pid, position in overview_layout_raw.items():
        layout_position = {
            "x": float(position.get("x", 0.0)),
            "y": float(position.get("y", 0.0)),
        }
        if "representativeness" in position:
            layout_position["representativeness"] = float(
                position.get("representativeness", 0.5),
            )
        for key in ("cluster_id", "cluster_size", "cluster_representative_id"):
            if key in position:
                layout_position[key] = int(position[key])
        if "layout_version" in position:
            layout_position["layout_version"] = int(position["layout_version"])
        overview_layout[int(pid)] = layout_position
    return overview_layout


def write_runtime_file(input_file: Path = DATA_FILE) -> Optional[Path]:
    """Convert similarity_data.json into the compact runtime .npz file."""
    with open(input_file, "r") as file_handle:
        data = json.load(file_handle)

    pokemon_info_raw = data.get("pokemon_info", {})
    ids = sorted(
        {int(pid) for pid in pokemon_info_raw}
        | {int(pid) for pid in data.get("vectors", {})}
        | {int(pid) for key in data.get("similarities", {}) for pid in key.split(",")}
    )
    index_by_id = {pid: index for index, pid in enumerate(ids)}
    n = len(ids)

    # NaN marks pairs that were never computed so they can be skipped later,
    # exactly like a missing key in the old dict.
    similarity = np.full((n, n), np.nan, dtype=np.float64)
    for key_str, score in data.get("similarities", {}).items():
        pid1, pid2 = map(int, key_str.split(","))
        i, j = index_by_id[pid1], index_by_id[pid2]
        similarity[i, j] = score
        similarity[j, i] = score

    vector_ids = sorted(int(pid) for pid in data.get("vectors", {}))
    vectors = np.array(
        [data["vectors"][str(pid)] for pid in vector_ids],
        dtype=np.float64,
    )

    meta = {
        "source_sha256": _file_sha256(input_file),
        "feature_version": int(data.get("feature_version") or 0),
        "embedding_model": data.get("embedding_model"),
        # keep the json key order so endpoints iterate pokemon in the same order
        "pokemon_info": [[int(pid), info] for pid, info in pokemon_info_raw.items()],
        "overview_layout": {
            str(pid): position
            for pid, position in _normalize_overview_layout(
                data.get("overview_layout", {}),
            ).items()
        },
    }
    del data

    output_file = _runtime_path_for(input_file)
    tmp_file = output_file.with_name(output_file.name + ".tmp.npz")
    np.savez_compressed(
        tmp_file,
        ids=np.asarray(ids, dtype=np.int64),
        similarity_upper=similarity[np.triu_indices(n)],
        vector_ids=np.asarray(vector_ids, dtype=np.int64),
        vectors=vectors,
        meta=np.array(json.dumps(meta)),
    )
    tmp_file.replace(output_file)
    return output_file


def _read_runtime_file(runtime_file: Path) -> Dict:
    with np.load(runtime_file, allow_pickle=False) as archive:
        ids = archive["ids"]
        upper = archive["similarity_upper"]
        vector_ids = archive["vector_ids"]
        vectors = archive["vectors"]
        meta = json.loads(str(archive["meta"]))

    n = len(ids)
    similarity = np.empty((n, n), dtype=np.float64)
    rows, cols = np.triu_indices(n)
    similarity[rows, cols] = upper
    similarity[cols, rows] = upper
    del upper, rows, cols

    ids_list = [int(pid) for pid in ids]
    return {
        "source_sha256": meta.get("source_sha256"),
        "feature_version": int(meta.get("feature_version") or 0),
        "embedding_model": meta.get("embedding_model"),
        "ids": ids_list,
        "index_by_id": {pid: index for index, pid in enumerate(ids_list)},
        "similarity_matrix": similarity,
        "vector_ids": [int(pid) for pid in vector_ids],
        "vector_matrix": vectors,
        "pokemon_info": {int(pid): info for pid, info in meta["pokemon_info"]},
        "overview_layout": {
            int(pid): position for pid, position in meta["overview_layout"].items()
        },
    }


def _rebuild_runtime_file_in_subprocess(input_file: Path) -> None:
    # Parsing the JSON spikes memory by a few hundred MB, and CPython rarely
    # hands that back to the OS. Doing it in a short-lived child process keeps
    # the long-running server process small.
    import subprocess
    import sys

    try:
        subprocess.run(
            [sys.executable, "-m", "src.data_store", str(input_file)],
            cwd=Path(__file__).parent.parent,
            check=True,
        )
    except Exception as error:
        print(f"Subprocess rebuild failed ({error}), rebuilding in-process")
        write_runtime_file(input_file)


def load_similarity_data(input_file: Path = DATA_FILE) -> Optional[Dict]:
    """
    Load similarity data for the web server.

    Returns a dict with:
    - ids / index_by_id: sorted pokemon ids and their row index in the matrix
    - similarity_matrix: dense (n, n) float64 array, NaN where no score exists
    - vector_ids / vector_matrix: feature vectors as one (m, d) array
    - pokemon_info / overview_layout: keyed by int pokemon id
    """
    try:
        runtime_file = _runtime_path_for(input_file)
        source_sha256 = _file_sha256(input_file) if input_file.exists() else None

        if runtime_file.exists():
            data = _read_runtime_file(runtime_file)
            if source_sha256 is None or data["source_sha256"] == source_sha256:
                return data
            print(f"{runtime_file.name} is stale, rebuilding from {input_file.name}")

        if source_sha256 is None:
            return None

        _rebuild_runtime_file_in_subprocess(input_file)
        return _read_runtime_file(runtime_file)
    except Exception as error:
        print(f"Error loading similarity data from {input_file}: {error}")
        return None


if __name__ == "__main__":
    import sys

    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA_FILE
    print(f"Wrote {write_runtime_file(target)}")
