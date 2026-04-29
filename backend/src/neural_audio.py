"""
Optional neural audio embedding pipeline for Pokemon cry "vibe" clustering.

This path uses CLAP as a feature extractor: we compare hidden audio embeddings
instead of hand-built DSP descriptors. It is intentionally optional because the
HuggingFace model and torch dependencies are large.
"""

from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import librosa

from .data_pipeline import (
    CRIES_DIR,
    DATA_DIR,
    CRY_SOURCE_VERSION,
    VECTORS_DIR,
    download_and_process_cry,
    get_cry_local_path,
    get_pokemon_info,
    load_similarity_data,
)
from .similarity import (
    compute_overview_layout,
    compute_pairwise_similarities,
    normalize_similarity,
)


CLAP_MODEL_NAME = "laion/clap-htsat-unfused"
CLAP_FEATURE_VERSION = 1008
CLAP_SAMPLE_RATE = 48_000


def get_clap_vector_path(pokemon_id: int, model_name: str = CLAP_MODEL_NAME) -> Path:
    safe_model_name = model_name.replace("/", "__").replace(":", "_")
    return VECTORS_DIR / (
        f"{pokemon_id}_clap_v{CLAP_FEATURE_VERSION}_{safe_model_name}_"
        f"{CRY_SOURCE_VERSION}.npy"
    )


def _load_clap_dependencies():
    try:
        import torch
        from transformers import ClapModel, ClapProcessor
    except ImportError as exc:
        raise RuntimeError(
            "CLAP dependencies are not installed. Run "
            "`/usr/local/bin/python3.11 -m pip install -r backend/requirements-neural.txt` "
            "first."
        ) from exc

    return torch, ClapModel, ClapProcessor


def _load_audio_for_clap(audio_path: Path) -> np.ndarray:
    y, _ = librosa.load(audio_path, sr=CLAP_SAMPLE_RATE, mono=True)
    if y.size == 0:
        return y

    y = librosa.util.normalize(y)
    # CLAP can ingest variable-length audio, but Pokemon cries are tiny. Padding
    # gives the model enough temporal context without changing the cry shape.
    min_len = int(CLAP_SAMPLE_RATE * 1.0)
    if y.size < min_len:
        y = librosa.util.fix_length(y, size=min_len)
    return y.astype(np.float32)


def extract_clap_embedding(
    audio_path: Path,
    model,
    processor,
    torch,
    device: str,
) -> Optional[np.ndarray]:
    try:
        audio = _load_audio_for_clap(audio_path)
        if audio.size == 0:
            return None

        inputs = processor(
            audio=audio,
            sampling_rate=CLAP_SAMPLE_RATE,
            return_tensors="pt",
        )
        inputs = {key: value.to(device) for key, value in inputs.items()}

        with torch.no_grad():
            embedding = model.get_audio_features(**inputs)

        if hasattr(embedding, "pooler_output"):
            embedding = embedding.pooler_output
        elif hasattr(embedding, "last_hidden_state"):
            embedding = embedding.last_hidden_state.mean(dim=1)
        elif isinstance(embedding, (tuple, list)):
            embedding = embedding[0]

        vector = embedding.detach().cpu().numpy()[0].astype(float)
        norm = np.linalg.norm(vector)
        if norm > 1e-12:
            vector = vector / norm
        return vector
    except Exception as exc:
        print(f"Error extracting CLAP embedding from {audio_path}: {exc}")
        return None


def download_and_embed_cry(
    pokemon_id: int,
    model,
    processor,
    torch,
    device: str,
    model_name: str = CLAP_MODEL_NAME,
) -> Optional[np.ndarray]:
    VECTORS_DIR.mkdir(parents=True, exist_ok=True)
    vector_path = get_clap_vector_path(pokemon_id, model_name)
    if vector_path.exists():
        try:
            return np.load(vector_path)
        except Exception as exc:
            print(f"Error loading cached CLAP vector for {pokemon_id}: {exc}")

    cry_path = get_cry_local_path(pokemon_id)
    if not cry_path.exists():
        # Reuse the existing pipeline's download behavior. We ignore the DSP
        # vector it returns; this just ensures the cry file exists locally.
        download_and_process_cry(pokemon_id)

    if not cry_path.exists():
        print(f"No local cry available for Pokemon {pokemon_id}")
        return None

    vector = extract_clap_embedding(cry_path, model, processor, torch, device)
    if vector is not None:
        np.save(vector_path, vector)
    return vector


def _load_existing_pokemon_info() -> Dict[int, dict]:
    data_file = DATA_DIR / "similarity_data.json"
    if data_file.exists():
        data = load_similarity_data(data_file)
        if data and data.get("pokemon_info"):
            return data["pokemon_info"]
    return {}


def build_clap_similarity_matrix(
    pokemon_ids: List[int],
    model_name: str = CLAP_MODEL_NAME,
    device: Optional[str] = None,
) -> Dict:
    torch, ClapModel, ClapProcessor = _load_clap_dependencies()

    if device is None:
        if torch.cuda.is_available():
            device = "cuda"
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            device = "mps"
        else:
            device = "cpu"

    print(f"Loading CLAP model: {model_name}")
    processor = ClapProcessor.from_pretrained(model_name)
    model = ClapModel.from_pretrained(model_name).to(device)
    model.eval()

    vectors = {}
    existing_info = _load_existing_pokemon_info()
    pokemon_info = {}

    print(f"Extracting CLAP embeddings for {len(pokemon_ids)} Pokemon...")
    for index, pid in enumerate(pokemon_ids):
        if index % 25 == 0:
            print(f"  Progress: {index}/{len(pokemon_ids)}")

        vector = download_and_embed_cry(
            pid,
            model=model,
            processor=processor,
            torch=torch,
            device=device,
            model_name=model_name,
        )
        if vector is not None:
            vectors[pid] = vector

        info = existing_info.get(pid) or get_pokemon_info(pid)
        if info:
            pokemon_info[pid] = info

    print(f"Successfully embedded {len(vectors)} Pokemon")
    raw_similarities = compute_pairwise_similarities(vectors)
    similarities = {key: normalize_similarity(value) for key, value in raw_similarities.items()}
    overview_layout = compute_overview_layout(
        list(vectors.keys()),
        similarities,
        vectors,
    )

    return {
        "feature_version": CLAP_FEATURE_VERSION,
        "embedding_model": model_name,
        "vectors": vectors,
        "similarities": similarities,
        "pokemon_info": pokemon_info,
        "overview_layout": overview_layout,
    }
