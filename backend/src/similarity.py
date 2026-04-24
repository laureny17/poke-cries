"""
Compute similarity scores between Pokémon cries using cosine similarity.
"""

import numpy as np
from typing import Dict, List, Tuple

try:
    from sklearn.manifold import SpectralEmbedding
    from sklearn.cluster import SpectralClustering
    from sklearn.decomposition import PCA
except ImportError:
    SpectralEmbedding = None
    SpectralClustering = None
    PCA = None


def _pca_embedding(matrix: np.ndarray, n_components: int = 2) -> np.ndarray:
    """Return a small PCA embedding using numpy-only SVD."""
    if matrix.ndim != 2:
        raise ValueError("Expected a 2D matrix for PCA embedding")

    centered = matrix - np.mean(matrix, axis=0, keepdims=True)
    if centered.shape[0] == 0:
        return np.zeros((0, n_components), dtype=float)

    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    components = vt[:n_components].T
    embedding = centered @ components

    if embedding.shape[1] < n_components:
        padding = np.zeros((embedding.shape[0], n_components - embedding.shape[1]))
        embedding = np.hstack([embedding, padding])

    return embedding


def _kmeans_labels(matrix: np.ndarray, cluster_count: int, iterations: int = 24) -> np.ndarray:
    """Cluster rows with a deterministic numpy-only k-means fallback."""
    n = matrix.shape[0]
    if n == 0:
        return np.zeros(0, dtype=int)

    cluster_count = max(1, min(cluster_count, n))
    squared_norms = np.sum(matrix * matrix, axis=1)
    centers = [int(np.argmax(squared_norms))]

    while len(centers) < cluster_count:
        chosen = matrix[np.array(centers)]
        distances = np.min(
            np.sum((matrix[:, np.newaxis, :] - chosen[np.newaxis, :, :]) ** 2, axis=2),
            axis=1,
        )
        centers.append(int(np.argmax(distances)))

    centroids = matrix[np.array(centers)].copy()
    labels = np.zeros(n, dtype=int)

    for _ in range(iterations):
        distances = np.sum(
            (matrix[:, np.newaxis, :] - centroids[np.newaxis, :, :]) ** 2,
            axis=2,
        )
        new_labels = np.argmin(distances, axis=1)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels

        for cluster_index in range(cluster_count):
            members = matrix[labels == cluster_index]
            if len(members) == 0:
                farthest = int(np.argmax(np.min(distances, axis=1)))
                centroids[cluster_index] = matrix[farthest]
            else:
                centroids[cluster_index] = np.mean(members, axis=0)

    return labels


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
    v1 = np.asarray(vector1, dtype=float).ravel()
    v2 = np.asarray(vector2, dtype=float).ravel()
    denominator = np.linalg.norm(v1) * np.linalg.norm(v2)
    if denominator <= 1e-12:
        return 0.0
    return float(np.dot(v1, v2) / denominator)


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
    neighbors_per_node: int = 14,
) -> Dict[int, Dict[str, float]]:
    """
    Compute a 2D overview layout from the normalized similarity graph.

    The overview is intentionally clustered: first detect cry communities from
    the nearest-neighbor affinity graph, then place each community as a distinct
    island and arrange its members by local similarity inside that island.
    """
    if not pokemon_ids:
        return {}

    sorted_ids = sorted(pokemon_ids)
    index_by_id = {pid: index for index, pid in enumerate(sorted_ids)}
    n = len(sorted_ids)

    affinity = np.zeros((n, n), dtype=float)
    local_scales = np.zeros(n, dtype=float)

    for i, pid1 in enumerate(sorted_ids):
        affinity[i, i] = 1.0
        row_scores = []
        for pid2 in sorted_ids:
            if pid1 == pid2:
                continue
            score = float(similarities.get((pid1, pid2), 0.0))
            row_scores.append((pid2, max(0.0, min(1.0, score))))

        row_scores.sort(key=lambda item: item[1], reverse=True)
        if row_scores:
            scale_index = min(len(row_scores) - 1, max(4, neighbors_per_node // 2))
            local_scales[i] = max(row_scores[scale_index][1], 1e-6)

        for pid2, score in row_scores[:neighbors_per_node]:
            j = index_by_id[pid2]
            # Adaptive local scaling preserves real neighborhoods while avoiding
            # the "everything falls into 2-3 blobs" failure mode.
            scaled = max(
                0.0,
                (score - local_scales[i]) / max(1.0 - local_scales[i], 1e-6),
            )
            affinity[i, j] = max(affinity[i, j], scaled ** 2.4)

    affinity = np.maximum(affinity, affinity.T)
    np.fill_diagonal(affinity, 1.0)

    if n == 1:
        return {sorted_ids[0]: {"x": 0.0, "y": 0.0}}

    if n < 8:
        cluster_labels = np.zeros(n, dtype=int)
    else:
        cluster_count = int(np.clip(round(np.sqrt(n) * 0.72), 4, 24))
        cluster_count = min(cluster_count, n)
        if SpectralClustering is not None:
            try:
                cluster_labels = SpectralClustering(
                    n_clusters=cluster_count,
                    affinity="precomputed",
                    assign_labels="kmeans",
                    random_state=42,
                ).fit_predict(affinity)
            except Exception:
                cluster_labels = _kmeans_labels(affinity, cluster_count)
        else:
            cluster_labels = _kmeans_labels(affinity, cluster_count)

    clusters = []
    for label in sorted(set(int(label) for label in cluster_labels)):
        indices = np.where(cluster_labels == label)[0]
        if indices.size:
            clusters.append(indices)

    clusters.sort(key=lambda indices: (-len(indices), int(np.min(indices))))

    local_positions = np.zeros((n, 2), dtype=float)
    cluster_radii = []

    for cluster_index, indices in enumerate(clusters):
        size = len(indices)
        if size == 1:
            local_positions[indices[0]] = [0.0, 0.0]
        elif size == 2:
            local_positions[indices[0]] = [-0.35, 0.0]
            local_positions[indices[1]] = [0.35, 0.0]
        else:
            cluster_affinity = affinity[np.ix_(indices, indices)]
            if SpectralEmbedding is not None:
                try:
                    local_embedding = SpectralEmbedding(
                        n_components=2,
                        affinity="precomputed",
                        random_state=42,
                    ).fit_transform(cluster_affinity)
                except Exception:
                    local_embedding = _pca_embedding(cluster_affinity)
            else:
                local_embedding = _pca_embedding(cluster_affinity)

            local_embedding = local_embedding - np.mean(local_embedding, axis=0)
            span = np.ptp(local_embedding, axis=0)
            max_span = max(float(np.max(span)), 1e-6)
            local_positions[indices] = local_embedding / max_span

        cluster_radii.append(0.34 + np.sqrt(size) * 0.055)

    cluster_centers = np.zeros((len(clusters), 2), dtype=float)
    golden_angle = np.pi * (3.0 - np.sqrt(5.0))

    for cluster_index, indices in enumerate(clusters):
        angle = cluster_index * golden_angle - np.pi / 2.0
        ring = np.sqrt(cluster_index + 1)
        radius = 1.15 + ring * 0.62
        center = np.array([np.cos(angle) * radius, np.sin(angle) * radius])

        # Push new islands away from earlier islands until their padded radii
        # no longer overlap. This makes the overview read as neighborhoods
        # instead of a single dense manifold.
        for _ in range(80):
            moved = False
            for other_index in range(cluster_index):
                delta = center - cluster_centers[other_index]
                distance = float(np.linalg.norm(delta))
                min_distance = (
                    cluster_radii[cluster_index]
                    + cluster_radii[other_index]
                    + 0.72
                )
                if distance >= min_distance:
                    continue

                if distance < 1e-6:
                    delta = np.array([np.cos(angle), np.sin(angle)])
                    distance = 1.0

                center = center + (delta / distance) * (min_distance - distance)
                moved = True

            if not moved:
                break

        cluster_centers[cluster_index] = center
        local_scale = cluster_radii[cluster_index]
        local_positions[indices] = center + local_positions[indices] * local_scale

    embedding = local_positions

    if len(clusters) <= 1:
        if SpectralEmbedding is not None:
            try:
                embedding = SpectralEmbedding(
                    n_components=2,
                    affinity="precomputed",
                    random_state=42,
                ).fit_transform(affinity)
            except Exception:
                embedding = _pca_embedding(affinity)
        else:
            embedding = _pca_embedding(affinity)

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
