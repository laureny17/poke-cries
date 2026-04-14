"""
Compute similarity scores between Pokémon cries using cosine similarity.
"""

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.manifold import SpectralEmbedding
from sklearn.decomposition import PCA
from typing import Dict, List, Tuple


def compute_cosine_similarity(vector1: np.ndarray, vector2: np.ndarray) -> float:
    """
    Compute cosine similarity between two vectors.

    Returns a value between -1 and 1, where:
    - 1.0 means identical direction
    - 0.0 means orthogonal
    - -1.0 means opposite direction

    Args:
        vector1: First feature vector
        vector2: Second feature vector

    Returns:
        Cosine similarity score
    """
    # Reshape for sklearn's cosine_similarity
    v1 = vector1.reshape(1, -1)
    v2 = vector2.reshape(1, -1)

    similarity = cosine_similarity(v1, v2)[0, 0]

    # Convert to 0-1 range for easier interpretation
    # (currently ranges from -1 to 1)
    return float(similarity)


def compute_pairwise_similarities(
    mfcc_vectors: Dict[int, np.ndarray]
) -> Dict[Tuple[int, int], float]:
    """
    Compute pairwise cosine similarity between all Pokémon.

    Args:
        mfcc_vectors: Dictionary mapping Pokémon ID to MFCC vector

    Returns:
        Dictionary mapping (pokemon_id1, pokemon_id2) tuples to similarity scores
    """
    similarities = {}
    pokemon_ids = sorted(mfcc_vectors.keys())

    # Compute all pairwise similarities
    for i, pid1 in enumerate(pokemon_ids):
        for pid2 in pokemon_ids[i:]:
            if pid1 == pid2:
                similarity = 1.0  # Identity
            else:
                similarity = compute_cosine_similarity(
                    mfcc_vectors[pid1],
                    mfcc_vectors[pid2]
                )

            # Store both directions for easier lookup
            similarities[(pid1, pid2)] = similarity
            if pid1 != pid2:
                similarities[(pid2, pid1)] = similarity

    return similarities


def get_similar_pokemon(
    pokemon_id: int,
    similarities: Dict[Tuple[int, int], float],
    top_k: int = 10,
    min_similarity: float = 0.0
) -> List[Tuple[int, float]]:
    """
    Get the most similar Pokémon to a given Pokémon.

    Args:
        pokemon_id: The target Pokémon ID
        similarities: Dictionary of all pairwise similarities
        top_k: Number of similar Pokémon to return
        min_similarity: Minimum similarity threshold

    Returns:
        List of (pokemon_id, similarity_score) tuples, sorted by similarity
    """
    similar = []

    for (pid1, pid2), score in similarities.items():
        if score < min_similarity:
            continue

        if pid1 == pokemon_id and pid2 != pokemon_id:
            similar.append((pid2, score))

    # Sort by similarity score (descending)
    similar.sort(key=lambda x: x[1], reverse=True)

    return similar[:top_k]


def normalize_similarity(score: float) -> float:
    """
    Normalize similarity score from [-1, 1] to [0, 1] range.

    This makes interpretation easier:
    - 0.5 = orthogonal (no similarity)
    - 1.0 = identical
    - 0.0 = opposite

    Args:
        score: Similarity score in [-1, 1] range

    Returns:
        Normalized score in [0, 1] range
    """
    return (score + 1.0) / 2.0


def compute_distance(similarity: float) -> float:
    """
    Convert normalized similarity score to a distance metric suitable for visualization.

    Uses inverse relationship: distance = 1 / (1 + similarity)
    This ensures similar Pokémon are close together in visualization.

    Args:
        similarity: Normalized similarity score [0, 1]

    Returns:
        Distance value for visualization
    """
    # Clamp similarity to [0, 1]
    similarity = max(0.0, min(1.0, similarity))

    # Inverse: high similarity = low distance
    distance = 1.0 / (1.0 + (10.0 * similarity))

    return distance


def compute_overview_layout(
    pokemon_ids: List[int],
    similarities: Dict[Tuple[int, int], float],
    neighbors_per_node: int = 10,
) -> Dict[int, Dict[str, float]]:
    """
    Compute a 2D overview embedding from the normalized similarity graph.

    The layout is derived from a sparsified affinity matrix so local cry
    neighborhoods stay prominent while broader inter-cluster relationships
    are still preserved.
    """
    if not pokemon_ids:
        return {}

    sorted_ids = sorted(pokemon_ids)
    index_by_id = {pid: index for index, pid in enumerate(sorted_ids)}
    n = len(sorted_ids)

    affinity = np.zeros((n, n), dtype=float)
    for i, pid1 in enumerate(sorted_ids):
        affinity[i, i] = 1.0
        row_scores = []
        for pid2 in sorted_ids:
            if pid1 == pid2:
                continue
            score = float(similarities.get((pid1, pid2), 0.0))
            row_scores.append((pid2, max(0.0, min(1.0, score))))

        row_scores.sort(key=lambda item: item[1], reverse=True)
        for pid2, score in row_scores[:neighbors_per_node]:
            j = index_by_id[pid2]
            # Sharpen higher-similarity relationships so neighborhoods form cleanly.
            affinity[i, j] = max(affinity[i, j], score ** 2.2)

    affinity = np.maximum(affinity, affinity.T)
    np.fill_diagonal(affinity, 1.0)

    try:
        embedding = SpectralEmbedding(
            n_components=2,
            affinity="precomputed",
            random_state=42,
        ).fit_transform(affinity)
    except Exception:
        # Fallback: PCA over the affinity rows still preserves broad structure.
        embedding = PCA(n_components=2, random_state=42).fit_transform(affinity)

    xs = embedding[:, 0]
    ys = embedding[:, 1]
    x_min = float(np.min(xs))
    x_max = float(np.max(xs))
    y_min = float(np.min(ys))
    y_max = float(np.max(ys))
    x_span = max(x_max - x_min, 1e-6)
    y_span = max(y_max - y_min, 1e-6)

    layout = {}
    for index, pid in enumerate(sorted_ids):
        x = ((float(xs[index]) - x_min) / x_span) * 2.0 - 1.0
        y = ((float(ys[index]) - y_min) / y_span) * 2.0 - 1.0
        layout[pid] = {"x": x, "y": y}

    return layout
