"""
Reciprocal Rank Fusion (RRF) — merges dense and sparse result lists.

RRF score = sum over each list of 1 / (k + rank)
where k=60 is the standard constant that dampens high-rank outliers.

After fusion, the merged list is passed to the cross-encoder reranker.
"""
from collections import defaultdict

from app.config import settings


def reciprocal_rank_fusion(
    dense_results: list[dict],
    sparse_results: list[dict],
) -> list[dict]:
    """
    Merge dense and sparse result lists using RRF.

    Both input lists must have an 'id' key.
    Returns a single list sorted by RRF score descending, with
    'rrf_score', 'dense_rank', and 'sparse_rank' fields added.
    """
    scores: dict[int, float] = defaultdict(float)
    dense_rank: dict[int, int] = {}
    sparse_rank: dict[int, int] = {}

    # Dense contributions
    for rank, item in enumerate(dense_results, start=1):
        doc_id = item["id"]
        scores[doc_id] += 1.0 / (settings.RRF_K + rank)
        dense_rank[doc_id] = rank

    # Sparse contributions
    for rank, item in enumerate(sparse_results, start=1):
        doc_id = item["id"]
        scores[doc_id] += 1.0 / (settings.RRF_K + rank)
        sparse_rank[doc_id] = rank

    # Build a unified id → metadata map
    meta_map: dict[int, dict] = {}
    for item in dense_results + sparse_results:
        meta_map[item["id"]] = item

    # Sort by RRF score
    sorted_ids = sorted(scores.keys(), key=lambda doc_id: scores[doc_id], reverse=True)

    fused = []
    for doc_id in sorted_ids:
        entry = {**meta_map[doc_id]}
        entry["rrf_score"] = scores[doc_id]
        entry["dense_rank"] = dense_rank.get(doc_id)
        entry["sparse_rank"] = sparse_rank.get(doc_id)
        fused.append(entry)

    return fused
