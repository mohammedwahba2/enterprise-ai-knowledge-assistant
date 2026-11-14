"""Calibrating the retrieval gate (PLAN section 11.7): threshold from the ROC of answerable versus
unanswerable questions on a CALIBRATION split, verified on a held-out TEST split, never tuned on
the test split.

A point is one question's best retrieval evidence (the highest cosine similarity among the passages
the model would be shown). The gate refuses when that score is below the threshold.
"""

import zlib
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise


@dataclass(frozen=True)
class Point:
    case_id: str
    answerable: bool
    score: float  # best similarity; -1.0 when nothing was retrieved at all
    kind: str | None = None


@dataclass(frozen=True)
class Rates:
    threshold: float
    refusal_recall: float  # unanswerable questions refused by the gate
    false_refusal: float  # answerable questions refused by the gate
    n_answerable: int
    n_unanswerable: int


def split(points: Sequence[Point]) -> tuple[list[Point], list[Point]]:
    """Deterministic, stratified by label: within each label, ids are ordered by a stable hash and
    alternate between calibration and test, so both halves keep the label balance."""
    calibration: list[Point] = []
    test: list[Point] = []
    for label in (True, False):
        group = sorted(
            (p for p in points if p.answerable is label),
            key=lambda p: zlib.crc32(p.case_id.encode()),
        )
        for i, p in enumerate(group):
            (calibration if i % 2 == 0 else test).append(p)
    return calibration, test


def rates(points: Sequence[Point], threshold: float) -> Rates:
    answerable = [p for p in points if p.answerable]
    unanswerable = [p for p in points if not p.answerable]
    refused_un = sum(1 for p in unanswerable if p.score < threshold)
    refused_an = sum(1 for p in answerable if p.score < threshold)
    return Rates(
        threshold=threshold,
        refusal_recall=refused_un / len(unanswerable) if unanswerable else 0.0,
        false_refusal=refused_an / len(answerable) if answerable else 0.0,
        n_answerable=len(answerable),
        n_unanswerable=len(unanswerable),
    )


def auc(points: Sequence[Point]) -> float:
    """P(an answerable question scores higher than an unanswerable one); ties count half."""
    pos = [p.score for p in points if p.answerable]
    neg = [p.score for p in points if not p.answerable]
    if not pos or not neg:
        raise ValueError("AUC needs both labels")
    wins = sum(1.0 if a > b else 0.5 if a == b else 0.0 for a in pos for b in neg)
    return wins / (len(pos) * len(neg))


def candidate_thresholds(points: Sequence[Point]) -> list[float]:
    scores = sorted({p.score for p in points})
    mids = [(a + b) / 2 for a, b in pairwise(scores)]
    return [scores[0] - 1e-6, *mids, scores[-1] + 1e-6]


def roc(points: Sequence[Point]) -> list[Rates]:
    return [rates(points, t) for t in candidate_thresholds(points)]


def choose_threshold(points: Sequence[Point], max_false_refusal: float) -> Rates:
    """The most protective threshold (highest refusal recall) whose false-refusal rate on the
    calibration points stays within `max_false_refusal`."""
    feasible = [r for r in roc(points) if r.false_refusal <= max_false_refusal]
    if not feasible:
        raise ValueError("no threshold satisfies the false-refusal bound")
    return max(feasible, key=lambda r: (r.refusal_recall, r.threshold))
