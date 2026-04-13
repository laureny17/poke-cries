"""
PokéAPI client for fetching Pokémon data, cries, and sprites.
Implements local caching per fair use policy.
"""

import os
import json
import requests
from pathlib import Path
from typing import Optional, Dict, List, Any

BASE_URL = "https://pokeapi.co/api/v2"
CACHE_DIR = Path(__file__).parent.parent / "data" / "cache"


def ensure_cache_dir():
    """Ensure cache directory exists."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_cache_path(resource_type: str, identifier: str) -> Path:
    """Get the cache file path for a resource."""
    return CACHE_DIR / f"{resource_type}_{identifier}.json"


def load_from_cache(resource_type: str, identifier: str) -> Optional[Dict[str, Any]]:
    """Load a resource from local cache if available."""
    cache_path = get_cache_path(resource_type, identifier)
    if cache_path.exists():
        try:
            with open(cache_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None
    return None


def save_to_cache(resource_type: str, identifier: str, data: Dict[str, Any]):
    """Save a resource to local cache."""
    ensure_cache_dir()
    cache_path = get_cache_path(resource_type, identifier)
    try:
        with open(cache_path, 'w') as f:
            json.dump(data, f)
    except IOError:
        pass  # Silently fail if we can't write cache


def fetch_resource(endpoint: str, identifier: str,
                   retries: int = 3, timeout: int = 30) -> Optional[Dict[str, Any]]:
    """
    Fetch a resource from PokéAPI with local caching and retry logic.

    Args:
        endpoint: The API endpoint (e.g., 'pokemon', 'pokemon-species')
        identifier: The resource ID or name
        retries: Number of attempts before giving up
        timeout: Per-request timeout in seconds

    Returns:
        The resource data or None if not found
    """
    # Try cache first
    cached = load_from_cache(endpoint, identifier)
    if cached:
        return cached

    url = f"{BASE_URL}/{endpoint}/{identifier}/"
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            save_to_cache(endpoint, identifier, data)
            return data
        except requests.RequestException as e:
            if attempt < retries:
                print(f"Retrying {endpoint}/{identifier} (attempt {attempt}/{retries}): {e}")
            else:
                print(f"Failed {endpoint}/{identifier} after {retries} attempts: {e}")
    return None


def get_pokemon_data(pokemon_id: int) -> Optional[Dict[str, Any]]:
    """Get Pokémon data including cry URLs and sprite."""
    return fetch_resource("pokemon", str(pokemon_id))


def get_pokemon_species(pokemon_id: int) -> Optional[Dict[str, Any]]:
    """Get Pokémon species data (includes generation info)."""
    data = fetch_resource("pokemon-species", str(pokemon_id))
    if data:
        return data
    # Fallback to fetching by pokemon id if species id doesn't work
    pokemon_data = fetch_resource("pokemon", str(pokemon_id))
    if pokemon_data and "species" in pokemon_data:
        return fetch_resource("pokemon-species", pokemon_data["species"]["name"])
    return None


def get_generation(gen_id: int) -> Optional[Dict[str, Any]]:
    """Get generation data."""
    return fetch_resource("generation", str(gen_id))


def list_pokemon(limit: int = 1025, offset: int = 0) -> List[Dict[str, Any]]:
    """
    List all Pokémon with pagination.

    Args:
        limit: Number of Pokémon to fetch per request
        offset: Starting offset

    Returns:
        List of Pokémon resources
    """
    all_pokemon = []
    url = f"{BASE_URL}/pokemon?limit={limit}&offset={offset}"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        all_pokemon.extend(data.get("results", []))

        # Handle pagination
        while data.get("next"):
            response = requests.get(data["next"], timeout=10)
            response.raise_for_status()
            data = response.json()
            all_pokemon.extend(data.get("results", []))

    except requests.RequestException as e:
        print(f"Error listing Pokémon: {e}")

    return all_pokemon


def get_pokemon_by_generation(generation_id: int) -> List[Dict[str, Any]]:
    """
    Get all Pokémon from a specific generation.

    Args:
        generation_id: The generation number (1-9)

    Returns:
        List of Pokémon in that generation
    """
    gen_data = get_generation(generation_id)
    if not gen_data:
        return []

    return gen_data.get("pokemon_species", [])


def download_cry(url: str, output_path: Path) -> bool:
    """
    Download a Pokémon cry audio file.

    Args:
        url: URL to the audio file
        output_path: Where to save the file

    Returns:
        True if successful, False otherwise
    """
    for attempt in range(1, 4):
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'wb') as f:
                f.write(response.content)
            return True
        except requests.RequestException as e:
            if attempt < 3:
                print(f"Retrying cry download (attempt {attempt}/3): {e}")
            else:
                print(f"Error downloading cry from {url}: {e}")
    return False


def get_cry_url(pokemon_id: int, use_latest: bool = True) -> Optional[str]:
    """
    Get the cry audio URL for a Pokémon.

    Args:
        pokemon_id: The Pokémon ID
        use_latest: Whether to use latest cry or legacy

    Returns:
        URL to the cry audio file or None
    """
    pokemon_data = get_pokemon_data(pokemon_id)
    if not pokemon_data or "cries" not in pokemon_data:
        return None

    cries = pokemon_data["cries"]
    cry_key = "latest" if use_latest else "legacy"
    return cries.get(cry_key)


def get_sprite_url(pokemon_id: int) -> Optional[str]:
    """
    Get the front default sprite URL for a Pokémon.

    Args:
        pokemon_id: The Pokémon ID

    Returns:
        URL to the sprite or None
    """
    pokemon_data = get_pokemon_data(pokemon_id)
    if not pokemon_data or "sprites" not in pokemon_data:
        return None

    sprites = pokemon_data["sprites"]
    return sprites.get("front_default")
