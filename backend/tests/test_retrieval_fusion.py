"""Reciprocal Rank Fusion against hand-computed cases."""

import pytest

from app.modules.retrieval.fusion import rrf


def test_scores_are_the_sum_of_reciprocal_ranks() -> None:
    fused = dict(rrf({"vector": ["a", "b", "c"], "fts": ["b", "a", "d"]}, k=60))
    assert fused["a"] == pytest.approx(1 / 61 + 1 / 62)
    assert fused["b"] == pytest.approx(1 / 62 + 1 / 61)
    assert fused["c"] == pytest.approx(1 / 63)
    assert fused["d"] == pytest.approx(1 / 63)


def test_an_item_found_by_both_legs_beats_one_found_by_a_single_leg() -> None:
    order = [item for item, _ in rrf({"vector": ["only_v", "both"], "fts": ["both", "only_f"]})]
    assert order[0] == "both"


def test_a_leg_with_no_results_leaves_the_other_ordering_intact() -> None:
    assert [i for i, _ in rrf({"vector": [], "fts": ["x", "y", "z"]})] == ["x", "y", "z"]
    assert rrf({"vector": [], "fts": []}) == []


def test_ties_are_broken_by_best_rank_then_first_appearance() -> None:
    # "p" and "q" have equal fused scores (1/61 + 1/63 vs 1/62 + 1/62 is NOT equal), so build a true tie:
    fused = rrf({"a": ["p", "q"], "b": ["q", "p"]})
    assert [i for i, _ in fused] == ["p", "q"]  # equal score, equal best rank: first seen wins


def test_k_flattens_the_difference_between_ranks() -> None:
    small = dict(rrf({"a": ["x", "y"]}, k=1))
    large = dict(rrf({"a": ["x", "y"]}, k=1000))
    assert small["x"] / small["y"] > large["x"] / large["y"]


def test_duplicates_within_one_list_are_counted_per_occurrence_not_silently_merged() -> None:
    # Callers pass de-duplicated lists; this documents what happens otherwise.
    assert dict(rrf({"a": ["x", "x"]}))["x"] == pytest.approx(1 / 61 + 1 / 62)
