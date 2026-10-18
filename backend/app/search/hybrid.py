"""Reciprocal rank fusion (RRF): merge several ranked lists into one.

Each list votes 1 / (k + rank) for every item it contains. Items that rank well
in several lists (keyword AND meaning AND area) rise to the top. RRF needs no
score normalisation between BM25 and cosine similarity, which is why it is the
usual way to build hybrid search.
"""

from collections import defaultdict


def rrf(rankings: list[list[int]], k: int = 60, weights: list[float] | None = None) -> list[tuple[int, float]]:
    scores: dict[int, float] = defaultdict(float)
    for position, ranking in enumerate(rankings):
        weight = weights[position] if weights else 1.0
        for rank, item in enumerate(ranking, start=1):
            scores[item] += weight / (k + rank)
    return sorted(scores.items(), key=lambda pair: -pair[1])
