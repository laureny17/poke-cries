"""
Lightweight persistence helpers for cached similarity data.

This module intentionally avoids importing the audio/similarity build stack so
the web server can start without pulling in the heavy ML dependencies.
"""

import json
from pathlib import Path
from typing import Dict, Optional


DATA_DIR = Path(__file__).parent.parent / "data"
DATA_FILE = DATA_DIR / "similarity_data.json"


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


def load_similarity_data(input_file: Path = DATA_FILE) -> Optional[Dict]:
    try:
        import numpy as np

        with open(input_file, "r") as file_handle:
            data = json.load(file_handle)

        vectors = {}
        for pid_str, vector_list in data["vectors"].items():
            vectors[int(pid_str)] = np.array(vector_list)

        similarities = {}
        for key_str, score in data["similarities"].items():
            pid1, pid2 = map(int, key_str.split(","))
            similarities[(pid1, pid2)] = score
            similarities[(pid2, pid1)] = score

        pokemon_info_raw = data.get("pokemon_info", {})
        pokemon_info = {int(pid): info for pid, info in pokemon_info_raw.items()}
        overview_layout_raw = data.get("overview_layout", {})
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

        return {
            "feature_version": int(data.get("feature_version", 0)),
            "embedding_model": data.get("embedding_model"),
            "vectors": vectors,
            "similarities": similarities,
            "pokemon_info": pokemon_info,
            "overview_layout": overview_layout,
        }
    except Exception as error:
        print(f"Error loading similarity data from {input_file}: {error}")
        return None
