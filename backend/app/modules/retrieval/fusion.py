"""Reciprocal Rank Fusion: pure, so it is unit-tested against hand-computed cases."""

from collections.abc import Hashable, Mapping, Sequence
from typing import TypeVar

K = TypeVar("K", bound=Hashable)


def rrf(rankings: Mapping[str, Sequence[K]], k: int = 60) -> list[tuple[K, float]]:
    """Fuse ranked lists: score(item) = sum over lists of 1 / (k + rank), ranks starting at 1.

    An item missing from a list simply gets no contribution from it. Ties are broken by the item's
    best rank in any list, then by the order of first appearance, so the result is deterministic.
    """
    scores: dict[K, float] = {}
    best: dict[K, int] = {}
    first_seen: dict[K, int] = {}
    for ranking in rankings.values():
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
            best[item] = min(best.get(item, rank), rank)
            first_seen.setdefault(item, len(first_seen))
    return sorted(scores.items(), key=lambda kv: (-kv[1], best[kv[0]], first_seen[kv[0]]))
