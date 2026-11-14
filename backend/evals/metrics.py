"""Retrieval metrics. Pure functions over *judged* rankings, so they are unit-tested by hand.

A judged ranking is a list with one entry per retrieved chunk: the index of the gold item that
chunk satisfies (each gold item is credited once, to the highest-ranked chunk that satisfies it)
or `None`. All metrics use binary relevance.
"""

import math
from collections.abc import Sequence

Judged = Sequence[int | None]


def recall_at_k(judged: Judged, n_gold: int, k: int) -> float:
    """Fraction of gold items found in the top k."""
    if n_gold == 0:
        raise ValueError("recall is undefined without gold items")
    return len({g for g in judged[:k] if g is not None}) / n_gold


def hit_at_k(judged: Judged, k: int) -> float:
    """1.0 if any of the top k satisfies any gold item."""
    return 1.0 if any(g is not None for g in judged[:k]) else 0.0


def reciprocal_rank(judged: Judged, k: int = 10) -> float:
    for position, gold in enumerate(judged[:k], start=1):
        if gold is not None:
            return 1.0 / position
    return 0.0


def ndcg_at_k(judged: Judged, n_gold: int, k: int) -> float:
    if n_gold == 0:
        raise ValueError("nDCG is undefined without gold items")
    dcg = sum(1.0 / math.log2(i + 1) for i, g in enumerate(judged[:k], start=1) if g is not None)
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(n_gold, k) + 1))
    return dcg / ideal


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0
