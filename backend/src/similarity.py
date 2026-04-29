"""
Compute similarity scores between Pokémon cries using cosine similarity.
"""

import numpy as np
from typing import Dict, List, Optional, Tuple

from .audio_processor import AXIS_FEATURES, _feature_slices, project_melodic_complexity_axes

OVERVIEW_LAYOUT_VERSION = 10

try:
    from sklearn.manifold import SpectralEmbedding
    from sklearn.cluster import AgglomerativeClustering, SpectralClustering
    from sklearn.decomposition import PCA
except ImportError:
    AgglomerativeClustering = None
    SpectralEmbedding = None
    SpectralClustering = None
    PCA = None


MUST_LINK_GROUPS = [
    # User-identified squeaky/chirpy family; these are very close by ear and
    # should not be split just because one descriptor drifts.
    (10, 12, 27, 33, 36, 116),
]


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


def _embed_from_precomputed_similarity(similarity_matrix: np.ndarray) -> np.ndarray:
    """Embed a precomputed similarity matrix into 2D."""
    if similarity_matrix.shape[0] == 0:
        return np.zeros((0, 2), dtype=float)
    if similarity_matrix.shape[0] == 1:
        return np.zeros((1, 2), dtype=float)

    matrix = np.maximum(similarity_matrix, 0.0)
    np.fill_diagonal(matrix, 1.0)

    if SpectralEmbedding is not None:
        try:
            return SpectralEmbedding(
                n_components=2,
                affinity="precomputed",
                random_state=42,
            ).fit_transform(matrix)
        except Exception:
            return _pca_embedding(matrix)

    return _pca_embedding(matrix)


def _zscore_columns(values: np.ndarray) -> np.ndarray:
    """Column-wise z-score normalization with zero-variance protection."""
    mean = np.mean(values, axis=0, keepdims=True)
    std = np.std(values, axis=0, keepdims=True)
    std = np.where(std < 1e-8, 1.0, std)
    return (values - mean) / std


def _rank_columns(values: np.ndarray) -> np.ndarray:
    """Map each descriptor column to roughly [-1, 1] by percentile rank."""
    ranked = np.zeros_like(values, dtype=float)
    for col_index in range(values.shape[1]):
        column = values[:, col_index]
        finite_mask = np.isfinite(column)
        if int(np.sum(finite_mask)) <= 1:
            continue

        valid_values = column[finite_mask]
        order = np.argsort(valid_values, kind="mergesort")
        ranks = np.empty(valid_values.size, dtype=float)
        ranks[order] = np.arange(valid_values.size, dtype=float)
        percentiles = ranks / max(valid_values.size - 1, 1)
        ranked[finite_mask, col_index] = percentiles * 2.0 - 1.0

    return ranked


def _axis_scores_from_descriptors(axis_values: np.ndarray) -> np.ndarray:
    """Compute visible graph axes from ranked acoustic descriptors."""
    ranked = _rank_columns(axis_values)
    feature_index = {name: index for index, name in enumerate(AXIS_FEATURES)}

    def col(name: str) -> np.ndarray:
        return ranked[:, feature_index[name]]

    buzz_to_chirp = (
        0.32 * col("pitch_height")
        + 0.24 * col("pitch_stability")
        + 0.20 * col("tonality")
        + 0.18 * col("brightness")
        + 0.10 * col("attack")
        - 0.34 * col("noisiness")
        - 0.12 * col("sustain")
    )
    sustained_to_punchy = (
        0.44 * col("attack")
        + 0.16 * col("pitch_height")
        + 0.10 * col("brightness")
        - 0.44 * col("sustain")
        - 0.18 * col("duration")
    )
    # Layout y increases downward in SVG, so positive values should mean
    # sustained/bottom and negative values should mean punchy/top.
    axis_scores = np.column_stack([buzz_to_chirp, -sustained_to_punchy])

    for col_index in range(axis_scores.shape[1]):
        extent = float(np.percentile(np.abs(axis_scores[:, col_index]), 98))
        if extent > 1e-8:
            axis_scores[:, col_index] = axis_scores[:, col_index] / extent

    return np.clip(axis_scores, -1.35, 1.35)


def _descriptor_cluster_labels(
    sorted_ids: List[int],
    vectors: Optional[Dict[int, np.ndarray]],
    fallback_matrix: np.ndarray,
) -> Optional[np.ndarray]:
    """Cluster by ranked acoustic descriptor profiles when available."""
    if not vectors or AgglomerativeClustering is None:
        return None

    slices = _feature_slices()
    axis_values = []
    valid_indices = []
    for index, pid in enumerate(sorted_ids):
        vector = vectors.get(pid)
        if vector is None:
            continue
        values = np.asarray(vector, dtype=float).ravel()
        if values.size < slices["shape"].stop:
            continue
        axis_values.append(values[slices["axis"]])
        valid_indices.append(index)

    if len(valid_indices) != len(sorted_ids) or len(axis_values) < 8:
        return None

    ranked = _rank_columns(np.asarray(axis_values, dtype=float))
    weights = np.array(
        [1.15, 1.0, 1.0, 1.2, 0.75, 0.65, 0.85, 0.7, 0.9, 0.35],
        dtype=float,
    )
    descriptor_features = ranked * weights

    # Include a low-weight local-neighborhood signature so clusters keep some
    # cry-shape context while still being primarily organized by audible vibe.
    neighbor_signature = _embed_from_precomputed_similarity(fallback_matrix)
    neighbor_signature = _zscore_columns(neighbor_signature) * 0.28
    features = np.hstack([descriptor_features, neighbor_signature])

    cluster_count = int(np.clip(round(len(sorted_ids) / 12), 8, 90))
    cluster_count = min(cluster_count, len(sorted_ids))
    try:
        return AgglomerativeClustering(
            n_clusters=cluster_count,
            linkage="ward",
        ).fit_predict(features)
    except Exception:
        return _kmeans_labels(features, cluster_count)


def _apply_must_link_groups(
    clusters: List[np.ndarray],
    sorted_ids: List[int],
    raw_similarity: np.ndarray,
) -> List[np.ndarray]:
    """Pull known ear-matched examples into explicit cohesive clusters."""
    index_by_id = {pid: index for index, pid in enumerate(sorted_ids)}
    protected_indices = set()
    seed_clusters = []

    for group in MUST_LINK_GROUPS:
        indices = [index_by_id[pid] for pid in group if pid in index_by_id]
        if len(indices) < 2:
            continue

        pair_scores = []
        for i, source in enumerate(indices):
            for target in indices[i + 1:]:
                pair_scores.append(float(raw_similarity[source, target]))

        if pair_scores and min(pair_scores) >= 0.92:
            protected_indices.update(indices)
            seed_clusters.append(np.array(sorted(indices), dtype=int))

    if not seed_clusters:
        return clusters

    next_clusters = []
    for cluster in clusters:
        remaining = [index for index in cluster if index not in protected_indices]
        if remaining:
            next_clusters.append(np.array(remaining, dtype=int))

    next_clusters.extend(seed_clusters)
    return next_clusters


def _orthogonal_align(source: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Return an orthogonal matrix that best aligns source to target."""
    cross = source.T @ target
    u, _, vt = np.linalg.svd(cross)
    rotation = u @ vt
    if np.linalg.det(rotation) < 0:
        u[:, -1] *= -1
        rotation = u @ vt
    return rotation


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


def _merge_tiny_clusters(
    clusters: List[np.ndarray],
    raw_similarity: np.ndarray,
    min_size: int,
) -> List[np.ndarray]:
    """Merge tiny visual islands into their nearest larger neighborhood."""
    if min_size <= 1 or len(clusters) <= 1:
        return clusters

    merged = [np.array(cluster, dtype=int) for cluster in clusters if len(cluster) > 0]

    changed = True
    while changed and len(merged) > 1:
        changed = False
        merged.sort(key=lambda indices: (len(indices), int(np.min(indices))))

        for source_index, source in enumerate(merged):
            if len(source) >= min_size:
                continue

            best_target_index = None
            best_score = -1.0
            for target_index, target in enumerate(merged):
                if target_index == source_index:
                    continue

                cross_similarity = raw_similarity[np.ix_(source, target)]
                if cross_similarity.size == 0:
                    continue

                # Use the strongest reliable bridge, not just the mean, so
                # small but real families do not become permanent loners.
                score = float(np.percentile(cross_similarity, 90))
                if score > best_score:
                    best_score = score
                    best_target_index = target_index

            if best_target_index is None:
                continue

            merged[best_target_index] = np.array(
                sorted(np.concatenate([merged[best_target_index], source])),
                dtype=int,
            )
            del merged[source_index]
            changed = True
            break

    return merged


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
    slices = _feature_slices()

    if v1.size >= slices["shape"].stop and v2.size >= slices["shape"].stop:
        def _block_similarity(name: str) -> float:
            block1 = v1[slices[name]]
            block2 = v2[slices[name]]
            denominator = np.linalg.norm(block1) * np.linalg.norm(block2)
            if denominator <= 1e-12:
                return 0.0
            return float(np.dot(block1, block2) / denominator)

        # Shape carries the pitch-tolerant gesture of the cry; MFCC/texture and
        # envelope keep broad timbre and attack from collapsing into one blob.
        weighted_scores = [
            (0.44, _block_similarity("shape")),
            (0.19, _block_similarity("mfcc")),
            (0.16, _block_similarity("texture")),
            (0.10, _block_similarity("pitch_contour")),
            (0.08, _block_similarity("envelope")),
            (0.03, _block_similarity("pitch")),
        ]
        return float(sum(weight * score for weight, score in weighted_scores))

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
    vectors: Optional[Dict[int, np.ndarray]] = None,
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
    raw_similarity = np.zeros((n, n), dtype=float)
    local_scales = np.zeros(n, dtype=float)

    for i, pid1 in enumerate(sorted_ids):
        affinity[i, i] = 1.0
        raw_similarity[i, i] = 1.0
        row_scores = []
        for pid2 in sorted_ids:
            if pid1 == pid2:
                continue
            score = float(similarities.get((pid1, pid2), 0.0))
            score = max(0.0, min(1.0, score))
            raw_similarity[i, index_by_id[pid2]] = score
            row_scores.append((pid2, score))

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
    raw_similarity = np.maximum(raw_similarity, raw_similarity.T)
    np.fill_diagonal(affinity, 1.0)
    np.fill_diagonal(raw_similarity, 1.0)

    axis_descriptor_targets = np.zeros((n, 2), dtype=float)
    has_axis_descriptors = False
    if vectors:
        axis_values = []
        axis_indices = []
        slices = _feature_slices()
        for index, pid in enumerate(sorted_ids):
            vector = vectors.get(pid)
            if vector is None:
                continue
            values = np.asarray(vector, dtype=float).ravel()
            if values.size >= slices["shape"].stop:
                axis_values.append(values[slices["axis"]])
                axis_indices.append(index)
            else:
                melodic, complex_score = project_melodic_complexity_axes(vector)
                axis_descriptor_targets[index] = [melodic, complex_score]

        if axis_values:
            axis_score_values = _axis_scores_from_descriptors(np.asarray(axis_values))
            for target_index, score in zip(axis_indices, axis_score_values):
                axis_descriptor_targets[target_index] = score

        descriptor_spread = np.std(axis_descriptor_targets, axis=0)
        has_axis_descriptors = bool(np.all(descriptor_spread > 1e-8))

    axis_positions = np.zeros((n, 2), dtype=float)
    use_axis_layout = bool(vectors) and has_axis_descriptors
    if use_axis_layout:
        # Axis-first layout: coordinates must visibly mean something. A small
        # local-similarity offset separates near-identical points without
        # destroying the left/right and top/bottom audio progression.
        descriptor_positions = axis_descriptor_targets.copy()
        local_similarity_positions = _embed_from_precomputed_similarity(raw_similarity)
        local_similarity_positions = local_similarity_positions - np.mean(
            local_similarity_positions,
            axis=0,
            keepdims=True,
        )
        local_similarity_positions = _zscore_columns(local_similarity_positions)
        axis_positions = descriptor_positions * 0.82 + local_similarity_positions * 0.18

        robust_extent = float(np.percentile(np.abs(axis_positions), 96))
        scale = max(robust_extent, 1e-6)
        axis_positions = np.clip(axis_positions / scale, -1.35, 1.35)

    if n == 1:
        return {sorted_ids[0]: {"x": 0.0, "y": 0.0}}

    descriptor_labels = _descriptor_cluster_labels(sorted_ids, vectors, raw_similarity)
    if descriptor_labels is not None:
        cluster_labels = descriptor_labels
    elif n < 8:
        cluster_labels = np.zeros(n, dtype=int)
    else:
        # Start with broad macro communities, then split oversized communities
        # using local similarity. This preserves good perceptual neighborhoods
        # that higher-k spectral clustering was cutting apart too early.
        cluster_count = int(np.clip(round(np.sqrt(n) * 0.48), 6, 18))
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

    # Spectral clustering can still produce one visually dominant island. Split
    # oversized islands locally so the overview remains a readable set of
    # neighborhoods without changing the underlying pairwise similarities.
    target_cluster_size = max(18, int(np.ceil(np.sqrt(n) * 1.05)))
    balanced_clusters = []
    for indices in clusters:
        if len(indices) <= target_cluster_size:
            balanced_clusters.append(indices)
            continue

        split_count = int(np.ceil(len(indices) / target_cluster_size))
        split_count = max(2, min(split_count, len(indices)))
        local_similarity = affinity[np.ix_(indices, indices)]
        average_similarity = np.mean(local_similarity, axis=1)
        seed_indices = [int(np.argmax(average_similarity))]

        while len(seed_indices) < split_count:
            best_candidate = None
            for local_index in range(len(indices)):
                if local_index in seed_indices:
                    continue
                nearest_seed_similarity = max(
                    local_similarity[local_index, seed_index]
                    for seed_index in seed_indices
                )
                candidate = (
                    -nearest_seed_similarity,
                    average_similarity[local_index],
                    local_index,
                )
                if best_candidate is None or candidate > best_candidate:
                    best_candidate = candidate

            seed_indices.append(best_candidate[2])

        group_capacity = int(np.ceil(len(indices) / split_count))
        grouped_indices = {seed_index: [] for seed_index in seed_indices}
        assignment_order = sorted(
            range(len(indices)),
            key=lambda local_index: max(
                local_similarity[local_index, seed_index]
                for seed_index in seed_indices
            ),
            reverse=True,
        )

        for local_index in assignment_order:
            seed_choices = sorted(
                seed_indices,
                key=lambda seed_index: local_similarity[local_index, seed_index],
                reverse=True,
            )
            for seed_index in seed_choices:
                if len(grouped_indices[seed_index]) < group_capacity:
                    grouped_indices[seed_index].append(indices[local_index])
                    break

        for seed_index in seed_indices:
            split_indices = np.array(sorted(grouped_indices[seed_index]))
            if split_indices.size:
                balanced_clusters.append(split_indices)

    clusters = sorted(
        balanced_clusters,
        key=lambda cluster_indices: (-len(cluster_indices), int(np.min(cluster_indices))),
    )
    clusters = _apply_must_link_groups(clusters, sorted_ids, raw_similarity)
    clusters = sorted(
        clusters,
        key=lambda cluster_indices: (-len(cluster_indices), int(np.min(cluster_indices))),
    )
    min_visual_cluster_size = 3 if n < 260 else 4
    clusters = _merge_tiny_clusters(clusters, raw_similarity, min_visual_cluster_size)
    clusters = sorted(
        clusters,
        key=lambda cluster_indices: (-len(cluster_indices), int(np.min(cluster_indices))),
    )

    # Representativeness is a cluster-relative percentile rank based on average
    # raw cry similarity to other members of that same final visual cluster.
    # This makes the tooltip answer "how central is this Pokemon in this island?"
    # instead of exposing tiny internal graph weights.
    representativeness = np.zeros(n, dtype=float)
    cluster_id_by_index = np.zeros(n, dtype=int)
    cluster_size_by_index = np.ones(n, dtype=int)
    representative_by_index = np.zeros(n, dtype=int)
    for cluster_id, indices in enumerate(clusters):
        cluster_id_by_index[indices] = cluster_id
        cluster_size_by_index[indices] = len(indices)
        if len(indices) > 1:
            raw_scores = []
            for i in indices:
                cluster_similarity_values = raw_similarity[i, indices]
                other_members = cluster_similarity_values[indices != i]
                if len(other_members) > 0:
                    raw_scores.append(float(np.mean(other_members)))
                else:
                    raw_scores.append(float(np.mean(cluster_similarity_values)))

            raw_arr = np.array(raw_scores, dtype=float)
            representative_local_index = int(np.argmax(raw_arr))
            representative_pid = sorted_ids[int(indices[representative_local_index])]
            representative_by_index[indices] = representative_pid

            if float(np.max(raw_arr) - np.min(raw_arr)) < 1e-9:
                representativeness[indices] = 1.0
            else:
                order = np.argsort(raw_arr, kind="mergesort")
                ranks = np.empty(len(raw_arr), dtype=float)
                ranks[order] = np.arange(len(raw_arr), dtype=float)
                percentile = ranks / max(len(raw_arr) - 1, 1)
                representativeness[indices] = 0.2 + percentile * 0.8
        else:
            representativeness[indices[0]] = 1.0
            representative_by_index[indices[0]] = sorted_ids[int(indices[0])]

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

        cluster_radii.append(0.58 + np.sqrt(size) * 0.09)

    cluster_count_final = len(clusters)
    cluster_similarity = np.eye(cluster_count_final, dtype=float)
    for i in range(cluster_count_final):
        for j in range(i + 1, cluster_count_final):
            cross_similarity = raw_similarity[np.ix_(clusters[i], clusters[j])]
            if cross_similarity.size:
                # A high percentile captures whether the two neighborhoods have
                # strong representative bridges without letting one accidental
                # nearest pair fully dominate cluster placement.
                score = float(np.percentile(cross_similarity, 88))
            else:
                score = 0.0
            cluster_similarity[i, j] = score
            cluster_similarity[j, i] = score

    if use_axis_layout:
        cluster_centers = np.zeros((cluster_count_final, 2), dtype=float)
        for cluster_index, indices in enumerate(clusters):
            member_positions = axis_positions[indices]
            member_weights = 0.35 + representativeness[indices] * 0.65
            weighted_center = np.average(member_positions, axis=0, weights=member_weights)

            representative_pid = int(representative_by_index[indices[0]])
            representative_index = index_by_id.get(representative_pid, int(indices[0]))
            representative_position = axis_positions[representative_index]

            # Blend representative identity and cluster mass center.
            cluster_centers[cluster_index] = representative_position * 0.55 + weighted_center * 0.45
    elif cluster_count_final == 1:
        cluster_centers = np.zeros((1, 2), dtype=float)
    elif cluster_count_final == 2:
        cluster_centers = np.array([[-1.0, 0.0], [1.0, 0.0]], dtype=float)
    else:
        placement_affinity = cluster_similarity.copy()
        placement_affinity = np.maximum(placement_affinity, 0.0)
        np.fill_diagonal(placement_affinity, 1.0)
        if SpectralEmbedding is not None:
            try:
                cluster_centers = SpectralEmbedding(
                    n_components=2,
                    affinity="precomputed",
                    random_state=42,
                ).fit_transform(placement_affinity)
            except Exception:
                cluster_centers = _pca_embedding(placement_affinity)
        else:
            cluster_centers = _pca_embedding(placement_affinity)

        cluster_centers = cluster_centers - np.mean(cluster_centers, axis=0)
        center_span = np.ptp(cluster_centers, axis=0)
        max_center_span = max(float(np.max(center_span)), 1e-6)
        cluster_centers = cluster_centers / max_center_span

    if not use_axis_layout:
        center_scale = 2.45 + np.sqrt(cluster_count_final) * 1.05
        cluster_centers = cluster_centers * center_scale

    if cluster_count_final > 1:
        anchor_centers = cluster_centers.copy()
        for _ in range(420):
            center_push = np.zeros_like(cluster_centers)
            max_overlap = 0.0

            for i in range(cluster_count_final):
                for j in range(i + 1, cluster_count_final):
                    delta = cluster_centers[j] - cluster_centers[i]
                    distance = float(np.linalg.norm(delta))
                    if distance < 1e-6:
                        angle = (i + j + 1) * np.pi * (3.0 - np.sqrt(5.0))
                        delta = np.array([np.cos(angle), np.sin(angle)])
                        distance = 1.0

                    similarity = cluster_similarity[i, j]
                    min_distance = (
                        cluster_radii[i]
                        + cluster_radii[j]
                        + 2.35
                        + (1.0 - similarity) * 2.15
                    )

                    if distance >= min_distance:
                        continue

                    overlap = min_distance - distance
                    max_overlap = max(max_overlap, overlap)
                    direction = delta / distance
                    step = direction * (overlap * 0.9)
                    center_push[i] -= step
                    center_push[j] += step

            # Keep clusters near their intended axis anchors while separating collisions.
            center_push += (anchor_centers - cluster_centers) * (
                0.02 if use_axis_layout else 0.0
            )
            cluster_centers += center_push

            if max_overlap < 1e-4:
                break

    for cluster_index, indices in enumerate(clusters):
        center = cluster_centers[cluster_index]
        local_scale = cluster_radii[cluster_index]
        local_positions[indices] = center + local_positions[indices] * local_scale

        # Resolve node overlap inside each cluster without exploding cluster size.
        for _ in range(22):
            cluster_subset = local_positions[indices].copy()
            moved = False
            # Allow a small amount of overlap inside a cluster; only prevent obvious collisions.
            min_sep = 0.014 + min(local_scale * 0.007, 0.012)

            for local_i in range(len(indices)):
                for local_j in range(local_i + 1, len(indices)):
                    dx = cluster_subset[local_j, 0] - cluster_subset[local_i, 0]
                    dy = cluster_subset[local_j, 1] - cluster_subset[local_i, 1]
                    dist = float(np.hypot(dx, dy))

                    if dist < 1e-6:
                        angle = (local_i + local_j + 1) * np.pi * (3.0 - np.sqrt(5.0))
                        norm_x = float(np.cos(angle))
                        norm_y = float(np.sin(angle))
                        push = min_sep * 0.5
                    elif dist < min_sep:
                        norm_x = dx / dist
                        norm_y = dy / dist
                        push = (min_sep - dist) * 0.5
                    else:
                        continue

                    moved = True
                    cluster_subset[local_i, 0] -= norm_x * push
                    cluster_subset[local_i, 1] -= norm_y * push
                    cluster_subset[local_j, 0] += norm_x * push
                    cluster_subset[local_j, 1] += norm_y * push

            # Gentle pull back toward the cluster center to avoid over-expansion.
            cluster_subset += (center - cluster_subset) * 0.06
            local_positions[indices] = cluster_subset

            if not moved:
                break

    if cluster_count_final > 1:
        original_centers = cluster_centers.copy()
        cluster_extent = np.zeros(cluster_count_final, dtype=float)
        for cluster_index, indices in enumerate(clusters):
            center = cluster_centers[cluster_index]
            points = local_positions[indices]
            if len(points) == 0:
                cluster_extent[cluster_index] = cluster_radii[cluster_index]
                continue

            cluster_extent[cluster_index] = (
                float(np.max(np.linalg.norm(points - center, axis=1)))
                + 0.26
            )

        for _ in range(520):
            moved = False
            for i in range(cluster_count_final):
                for j in range(i + 1, cluster_count_final):
                    delta = cluster_centers[j] - cluster_centers[i]
                    distance = float(np.linalg.norm(delta))
                    hard_min_distance = cluster_extent[i] + cluster_extent[j] + 0.85

                    if distance >= hard_min_distance:
                        continue

                    if distance < 1e-6:
                        angle = (i + j + 1) * np.pi * (3.0 - np.sqrt(5.0))
                        delta = np.array([np.cos(angle), np.sin(angle)])
                        distance = 1.0

                    direction = delta / distance
                    shift = (hard_min_distance - distance) * 0.52
                    cluster_centers[i] -= direction * shift
                    cluster_centers[j] += direction * shift
                    moved = True

            if not moved:
                break

        for cluster_index, indices in enumerate(clusters):
            # Keep the cluster shape intact while moving the whole island.
            shift = cluster_centers[cluster_index] - original_centers[cluster_index]
            local_positions[indices] += shift

    if use_axis_layout:
        cluster_embedding = local_positions - np.mean(
            local_positions,
            axis=0,
            keepdims=True,
        )
        cluster_extent = float(np.percentile(np.abs(cluster_embedding), 98))
        if cluster_extent > 1e-8:
            cluster_embedding = cluster_embedding / cluster_extent

        axis_embedding = axis_positions - np.mean(axis_positions, axis=0, keepdims=True)
        axis_extent = float(np.percentile(np.abs(axis_embedding), 98))
        if axis_extent > 1e-8:
            axis_embedding = axis_embedding / axis_extent

        # The axes are the promise of the overview. Keep cluster packing as a
        # readability offset, not as the thing that decides scale placement.
        embedding = axis_embedding * 0.82 + cluster_embedding * 0.18
    else:
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

    centered_embedding = embedding - np.mean(embedding, axis=0, keepdims=True)
    extent = float(np.max(np.abs(centered_embedding)))
    if extent < 1e-6:
        normalized_embedding = np.zeros_like(centered_embedding)
    else:
        normalized_embedding = centered_embedding / extent

    layout = {}
    for index, pid in enumerate(sorted_ids):
        x = float(np.clip(normalized_embedding[index, 0], -1.0, 1.0))
        y = float(np.clip(normalized_embedding[index, 1], -1.0, 1.0))
        layout[pid] = {
            "x": x,
            "y": y,
            "representativeness": float(representativeness[index]),
            "cluster_id": int(cluster_id_by_index[index]),
            "cluster_size": int(cluster_size_by_index[index]),
            "cluster_representative_id": int(representative_by_index[index]),
            "layout_version": OVERVIEW_LAYOUT_VERSION,
        }

    return layout
