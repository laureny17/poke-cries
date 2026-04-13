"""
Data pipeline for processing Pokémon cries and computing similarities.
"""

import json
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from .pokeapi_client import (
    get_pokemon_data,
    get_pokemon_species,
    get_cry_url,
    get_sprite_url,
    download_cry,
    get_pokemon_by_generation,
)
from .audio_processor import extract_audio_features
from .similarity import (
    compute_pairwise_similarities,
    get_similar_pokemon,
    normalize_similarity,
    compute_distance,
)


DATA_DIR = Path(__file__).parent.parent / "data"
CRIES_DIR = DATA_DIR / "cries"
VECTORS_DIR = DATA_DIR / "vectors"
CACHE_DIR = DATA_DIR / "cache"


def ensure_dirs():
    """Create necessary directories."""
    CRIES_DIR.mkdir(parents=True, exist_ok=True)
    VECTORS_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_cry_local_path(pokemon_id: int) -> Path:
    """Get local path for a cry file."""
    return CRIES_DIR / f"{pokemon_id}.ogg"


def get_vector_local_path(pokemon_id: int) -> Path:
    """Get local path for a cached feature vector."""
    return VECTORS_DIR / f"{pokemon_id}.npy"


def download_and_process_cry(pokemon_id: int) -> Optional[np.ndarray]:
    """
    Download a Pokémon cry and extract MFCC vector.
    
    Args:
        pokemon_id: The Pokémon ID
        
    Returns:
        MFCC vector array or None if download/processing failed
    """
    ensure_dirs()
    
    cry_local_path = get_cry_local_path(pokemon_id)
    vector_path = get_vector_local_path(pokemon_id)
    
    # Check if vector already exists
    if vector_path.exists():
        try:
            return np.load(vector_path)
        except Exception as e:
            print(f"Error loading cached vector for {pokemon_id}: {e}")
    
    # Download cry if not cached
    if not cry_local_path.exists():
        cry_url = get_cry_url(pokemon_id, use_latest=True)
        if not cry_url:
            print(f"No cry URL found for Pokémon {pokemon_id}")
            return None
        
        if not download_cry(cry_url, cry_local_path):
            print(f"Failed to download cry for Pokémon {pokemon_id}")
            return None
    
    # Extract combined perceptual feature vector (MFCC + chroma + spectral)
    try:
        mfcc_vector = extract_audio_features(cry_local_path)

        if mfcc_vector is not None:
            # Cache the vector
            np.save(vector_path, mfcc_vector)

        return mfcc_vector
        
    except Exception as e:
        print(f"Error extracting MFCC for {pokemon_id}: {e}")
        return None


def get_pokemon_info(pokemon_id: int) -> Optional[Dict]:
    """
    Get comprehensive Pokémon information.
    
    Args:
        pokemon_id: The Pokémon ID
        
    Returns:
        Dictionary with pokemon info
    """
    try:
        pokemon_data = get_pokemon_data(pokemon_id)
        species_data = get_pokemon_species(pokemon_id)
        
        if not pokemon_data or not species_data:
            return None
        
        return {
            "id": pokemon_id,
            "name": pokemon_data.get("name", ""),
            "height": pokemon_data.get("height", 0),
            "weight": pokemon_data.get("weight", 0),
            "sprite_url": get_sprite_url(pokemon_id),
            "generation": species_data.get("generation", {}).get("name", ""),
            "types": [t["type"]["name"] for t in pokemon_data.get("types", [])],
        }
    except Exception as e:
        print(f"Error getting info for Pokémon {pokemon_id}: {e}")
        return None


def build_similarity_matrix(pokemon_ids: List[int]) -> Dict:
    """
    Build complete similarity matrix for given Pokémon.
    
    Args:
        pokemon_ids: List of Pokémon IDs to process
        
    Returns:
        Dictionary with vectors and similarities
    """
    ensure_dirs()
    
    mfcc_vectors = {}
    pokemon_info = {}
    
    print(f"Processing {len(pokemon_ids)} Pokémon...")
    
    for i, pid in enumerate(pokemon_ids):
        if i % 50 == 0:
            print(f"  Progress: {i}/{len(pokemon_ids)}")
        
        # Get MFCC vector
        vector = download_and_process_cry(pid)
        if vector is not None:
            mfcc_vectors[pid] = vector
        
        # Get Pokémon info
        info = get_pokemon_info(pid)
        if info:
            pokemon_info[pid] = info
    
    print(f"Successfully processed {len(mfcc_vectors)} Pokémon")
    
    # Compute pairwise similarities
    print("Computing similarity matrix...")
    raw_similarities = compute_pairwise_similarities(mfcc_vectors)
    
    # Normalize similarities to [0, 1]
    normalized_similarities = {
        k: normalize_similarity(v) for k, v in raw_similarities.items()
    }
    
    return {
        "vectors": mfcc_vectors,
        "similarities": normalized_similarities,
        "pokemon_info": pokemon_info,
    }


def save_similarity_data(data: Dict, output_file: Path):
    """
    Save similarity data to file (with numpy vectors serialized).
    
    Args:
        data: Dictionary with vectors and similarities
        output_file: Path to save to
    """
    ensure_dirs()
    
    # Convert numpy arrays to lists for JSON serialization
    vectors_list = {}
    for pid, vector in data["vectors"].items():
        vectors_list[str(pid)] = vector.tolist()
    
    # Normalize similarity keys to strings
    similarities = {}
    for (pid1, pid2), score in data["similarities"].items():
        key = f"{min(pid1, pid2)},{max(pid1, pid2)}"
        similarities[key] = score
    
    output_data = {
        "vectors": vectors_list,
        "similarities": similarities,
        "pokemon_info": data["pokemon_info"],
    }
    
    with open(output_file, 'w') as f:
        json.dump(output_data, f)
    
    print(f"Saved similarity data to {output_file}")


def load_similarity_data(input_file: Path) -> Optional[Dict]:
    """
    Load similarity data from file.
    
    Args:
        input_file: Path to load from
        
    Returns:
        Dictionary with vectors and similarities
    """
    try:
        with open(input_file, 'r') as f:
            data = json.load(f)
        
        # Convert vectors back to numpy arrays
        vectors = {}
        for pid_str, vector_list in data["vectors"].items():
            vectors[int(pid_str)] = np.array(vector_list)
        
        # Denormalize similarity keys
        similarities = {}
        for key_str, score in data["similarities"].items():
            pid1, pid2 = map(int, key_str.split(','))
            similarities[(pid1, pid2)] = score
            similarities[(pid2, pid1)] = score
        
        pokemon_info_raw = data.get("pokemon_info", {})
        pokemon_info = {int(pid): info for pid, info in pokemon_info_raw.items()}

        return {
            "vectors": vectors,
            "similarities": similarities,
            "pokemon_info": pokemon_info,
        }
    except Exception as e:
        print(f"Error loading similarity data from {input_file}: {e}")
        return None


def get_generation_pokemon(generation: int) -> List[int]:
    """
    Get all Pokémon IDs from a generation.
    
    Args:
        generation: Generation number (1-9)
        
    Returns:
        List of Pokémon IDs
    """
    try:
        pokemon_species = get_pokemon_by_generation(generation)
        pokemon_ids = []
        
        for species in pokemon_species:
            # Extract ID from URL
            url = species.get("url", "")
            if url:
                pid = int(url.rstrip('/').split('/')[-1])
                pokemon_ids.append(pid)
        
        return sorted(pokemon_ids)
    except Exception as e:
        print(f"Error getting generation {generation} Pokémon: {e}")
        return []
