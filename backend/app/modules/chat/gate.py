"""The retrieval gate: refuse WITHOUT calling the model when the evidence is too weak.

The threshold is not a guess: it is calibrated on a calibration split of answerable versus
unanswerable questions and verified on a held-out test split (docs/eval/stage8-answers.md).
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.core.config import Settings


@dataclass(frozen=True)
class Evidence:
    """One retrieved chunk as the answer pipeline sees it."""

    chunk_id: str
    similarity: float | None  # cosine to the question; None when it was not in the vector leg
    fts_score: float | None


@dataclass(frozen=True)
class GateDecision:
    passed: bool
    mode: str  # "vector" | "lexical" | "none"
    best: float | None


def decide(evidence: Sequence[Evidence], settings: Settings) -> GateDecision:
    """Vector evidence when the embedder produced any, otherwise lexical evidence (degraded)."""
    similarities = [e.similarity for e in evidence if e.similarity is not None]
    if similarities:
        best = max(similarities)
        return GateDecision(best >= settings.gate_min_similarity, "vector", best)
    scores = [e.fts_score for e in evidence if e.fts_score is not None]
    if scores:
        best_fts = max(scores)
        return GateDecision(best_fts >= settings.gate_min_fts_score, "lexical", best_fts)
    return GateDecision(False, "none", None)
