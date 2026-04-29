#!/usr/bin/env python3
"""
Utility script to build and manage the similarity matrix.
"""

import argparse
import shutil
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))

from src.data_pipeline import (
    build_similarity_matrix,
    save_similarity_data,
    get_generation_pokemon,
    DATA_DIR,
    VECTORS_DIR,
)
from src.neural_audio import CLAP_MODEL_NAME, build_clap_similarity_matrix


def build_matrix(generation=None, force=False):
    """Build similarity matrix."""
    output_file = DATA_DIR / "similarity_data.json"

    if output_file.exists() and not force:
        print(f"✓ Similarity data already exists at {output_file}")
        print("  Use --force to rebuild")
        return

    # Wipe cached feature vectors so we always recompute with the current
    # feature extraction code. Audio files in data/cries/ are kept.
    if VECTORS_DIR.exists():
        shutil.rmtree(VECTORS_DIR)
        VECTORS_DIR.mkdir()
        print(f"🧹 Cleared stale vectors in {VECTORS_DIR}")

    print(f"🔨 Building similarity matrix...")

    if generation:
        pokemon_ids = get_generation_pokemon(generation)
        print(f"📊 Processing Generation {generation} ({len(pokemon_ids)} Pokémon)")
    else:
        pokemon_ids = list(range(1, 1026))
        print(f"📊 Processing all Pokémon ({len(pokemon_ids)} total)")

    try:
        data = build_similarity_matrix(pokemon_ids)
        save_similarity_data(data, output_file)
        print(f"\n✅ Successfully built similarity matrix!")
        print(f"💾 Saved to: {output_file}")
        print(f"📈 Pokémon processed: {len(data['pokemon_info'])}")

    except Exception as e:
        print(f"❌ Error building similarity matrix: {e}")
        sys.exit(1)


def build_clap_matrix(generation=None, force=False, model_name=CLAP_MODEL_NAME, device=None):
    """Build similarity matrix from CLAP neural audio embeddings."""
    output_file = DATA_DIR / "similarity_data.json"

    if output_file.exists() and not force:
        print(f"✓ Similarity data already exists at {output_file}")
        print("  Use --force to rebuild")
        return

    print("🔊 Building CLAP embedding similarity matrix...")
    if generation:
        pokemon_ids = get_generation_pokemon(generation)
        print(f"📊 Processing Generation {generation} ({len(pokemon_ids)} Pokémon)")
    else:
        pokemon_ids = list(range(1, 1026))
        print(f"📊 Processing all Pokémon ({len(pokemon_ids)} total)")

    try:
        data = build_clap_similarity_matrix(
            pokemon_ids,
            model_name=model_name,
            device=device,
        )
        save_similarity_data(data, output_file)
        print("\n✅ Successfully built CLAP similarity matrix!")
        print(f"💾 Saved to: {output_file}")
        print(f"📈 Pokémon processed: {len(data['pokemon_info'])}")
    except Exception as e:
        print(f"❌ Error building CLAP similarity matrix: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Pokémon Cry Similarity - Data Management Tool"
    )

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Build command
    build_parser = subparsers.add_parser(
        'build',
        help='Build the similarity matrix',
    )
    build_parser.add_argument(
        '--generation',
        type=int,
        help='Build matrix for specific generation (1-9)',
    )
    build_parser.add_argument(
        '--force',
        action='store_true',
        help='Force rebuild even if data exists',
    )

    clap_parser = subparsers.add_parser(
        'build-clap',
        help='Build the similarity matrix with CLAP neural audio embeddings',
    )
    clap_parser.add_argument(
        '--generation',
        type=int,
        help='Build matrix for specific generation (1-9)',
    )
    clap_parser.add_argument(
        '--force',
        action='store_true',
        help='Force rebuild even if data exists',
    )
    clap_parser.add_argument(
        '--model',
        default=CLAP_MODEL_NAME,
        help='HuggingFace CLAP model name',
    )
    clap_parser.add_argument(
        '--device',
        default=None,
        help='Torch device override: cpu, cuda, or mps',
    )

    args = parser.parse_args()

    if args.command == 'build':
        build_matrix(generation=args.generation, force=args.force)
    elif args.command == 'build-clap':
        build_clap_matrix(
            generation=args.generation,
            force=args.force,
            model_name=args.model,
            device=args.device,
        )
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
