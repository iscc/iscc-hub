"""
Tests for Tiered Semantic Ranking (iscc_hub/rerank.py).

Pure-function tests over hand-computed inputs — no I/O, no mocks. Each tier and
scoring branch is exercised with the smallest input that uniquely reaches it.
"""

import pytest

from iscc_hub.rerank import (
    TAU_SOFT,
    aggregate_maintypes,
    classify_tier,
    rerank_matches,
    sort_key,
    tier_score,
    weighted_score,
)

# T7 isolated cap; the value the single-signal tiers clamp to (0.7 * 0.9).
T7_CAP = TAU_SOFT * 0.9


def test_aggregate_maintypes_takes_max_and_ignores_unknown():
    # type: () -> None
    """Per-MainType maxima collapse SubTypes; unrecognised MainTypes are dropped."""
    types = {"CONTENT_TEXT_V0": 0.5, "CONTENT_IMAGE_V0": 0.9, "META_NONE_V0": 0.8, "FOO_BAR_V0": 0.99}
    assert aggregate_maintypes(types) == {"CONTENT": 0.9, "META": 0.8}


def test_aggregate_maintypes_empty():
    # type: () -> None
    """No recognised unit keys yields an empty aggregation."""
    assert aggregate_maintypes({}) == {}


def test_classify_tier_all_tiers():
    # type: () -> None
    """Each smallest input maps to its intended tier, including the no-tier (None) case."""
    cases = [
        ({"INSTANCE": 0.9, "DATA": 0.5}, "T0"),  # instance match contradicted by weak DATA
        ({"INSTANCE": 0.9, "CONTENT": 0.5}, "T0"),  # ... or by weak CONTENT
        ({"INSTANCE": 0.9}, "T1"),  # instance match, nothing contradicting it
        ({"INSTANCE": 0.9, "DATA": 0.9}, "T1"),  # intrinsic signals agree -> still exact
        ({"DATA": 0.9}, "T2"),  # data-high, content absent
        ({"DATA": 0.9, "CONTENT": 0.9}, "T2"),  # data-high, content also high
        ({"DATA": 0.9, "CONTENT": 0.5}, "T7"),  # data-high but content contradicts -> falls through
        ({"CONTENT": 0.9, "SEMANTIC": 0.75}, "T3"),  # content-high corroborated by a soft second
        ({"SEMANTIC": 0.9, "CONTENT": 0.72}, "T4"),  # semantic-high corroborated by a soft second
        ({"SEMANTIC": 0.9}, "T7"),  # semantic-high alone is isolated, not an adaptation
        ({"CONTENT": 0.72, "DATA": 0.65}, "T5"),  # one soft + a distinct weak corroborator
        ({"META": 0.9}, "T6"),  # title-only: meta-high, nothing else
        ({"CONTENT": 0.8}, "T7"),  # single soft signal, isolated
        ({"CONTENT": 0.5}, None),  # everything below the soft floor -> no tier
    ]
    for agg, expected in cases:
        assert classify_tier(agg) == expected, agg


def test_weighted_score_presence_aware_mean():
    # type: () -> None
    """Weighted mean over present MainTypes, no coherence bonus for mixed evidence."""
    # (0.8*0.9 + 0.3*0.5) / (0.8 + 0.3)
    assert weighted_score({"CONTENT": 0.9, "DATA": 0.5}) == pytest.approx((0.72 + 0.15) / 1.1)


def test_weighted_score_coherence_bonus_all_high():
    # type: () -> None
    """Two-plus intrinsic signals all high earn the +5% coherence bonus."""
    assert weighted_score({"CONTENT": 0.9, "DATA": 0.9}) == pytest.approx(0.9 * 1.05)


def test_weighted_score_coherence_bonus_all_low():
    # type: () -> None
    """Two-plus intrinsic signals all low also earn the bonus (unanimous agreement)."""
    expected = ((0.8 * 0.5 + 0.3 * 0.4) / 1.1) * 1.05
    assert weighted_score({"CONTENT": 0.5, "DATA": 0.4}) == pytest.approx(expected)


def test_weighted_score_bonus_capped_at_one():
    # type: () -> None
    """The coherence bonus never pushes the score above 1.0."""
    assert weighted_score({"CONTENT": 1.0, "DATA": 1.0}) == 1.0


def test_weighted_score_single_signal_no_bonus():
    # type: () -> None
    """Fewer than two intrinsic signals: no bonus, plain weighted value."""
    assert weighted_score({"META": 0.9}) == pytest.approx(0.9)


def test_weighted_score_empty():
    # type: () -> None
    """An empty aggregation scores zero (no division by zero)."""
    assert weighted_score({}) == 0.0


def test_tier_score_exact_and_incoherent_are_fixed():
    # type: () -> None
    """T1 is always 1.0 and T0 always 0.0, independent of the weighted mean."""
    assert tier_score("T1", {"INSTANCE": 0.9}) == 1.0
    assert tier_score("T0", {"INSTANCE": 0.9, "DATA": 0.5}) == 0.0


def test_tier_score_cap_binds_for_weak_tiers():
    # type: () -> None
    """A T6 title-only candidate is clamped to the soft floor despite a high mean."""
    assert tier_score("T6", {"META": 0.9}) == TAU_SOFT


def test_tier_score_cap_not_binding():
    # type: () -> None
    """When the weighted mean is below the cap, the mean is kept (T4 cap is 1.0)."""
    # A reachable T4 agg (semantic-high corroborated by a soft second); the weighted mean is
    # below the 1.0 cap, so tier_score returns it unchanged.
    agg = {"SEMANTIC": 0.9, "CONTENT": 0.72}
    assert tier_score("T4", agg) == pytest.approx(weighted_score(agg))


def test_tier_score_isolated_penalty_then_cap():
    # type: () -> None
    """T7 content-only: penalty (0.8) then clamp to the isolated cap."""
    # weighted = 1.0; *0.8 penalty = 0.8; min(0.8, 0.63 cap) = 0.63
    assert tier_score("T7", {"CONTENT": 1.0}) == pytest.approx(T7_CAP)


def test_tier_score_isolated_penalty_below_cap():
    # type: () -> None
    """T7 where the penalised score lands below the cap: the penalised value is kept."""
    # weighted = 0.7; *0.8 penalty = 0.56; min(0.56, 0.63 cap) = 0.56
    assert tier_score("T7", {"CONTENT": 0.7}) == pytest.approx(0.7 * 0.8)


def test_sort_key_orders_by_tier_then_score_then_units():
    # type: () -> None
    """Lower tier rank wins; ties break on score, then per-unit strength (missing last)."""
    high_tier = sort_key("T1", 0.5, {"INSTANCE": 0.9})
    low_tier = sort_key("T6", 0.9, {"META": 0.9})
    assert high_tier < low_tier  # tier dominates score
    # Same tier and score: the candidate with the stronger higher-priority unit sorts first.
    with_data = sort_key("T7", T7_CAP, {"DATA": 0.8})
    without_data = sort_key("T7", T7_CAP, {"CONTENT": 0.8})
    assert with_data < without_data


def test_rerank_reorders_rescores_and_drops_noise():
    # type: () -> None
    """An exact match rises above a title-only one; sub-threshold and empty matches drop."""
    matches = [
        {"iscc_id": "ISCC:META", "score": 0.82, "types": {"META_NONE_V0": 0.9375}, "metadata": {"k": "v"}},
        {
            "iscc_id": "ISCC:EXACT",
            "score": 0.50,
            "types": {"INSTANCE_NONE_V0": 1.0, "DATA_NONE_V0": 1.0, "CONTENT_TEXT_V0": 1.0},
            "metadata": None,
        },
        {"iscc_id": "ISCC:NOISE", "score": 0.40, "types": {"CONTENT_TEXT_V0": 0.5}, "metadata": None},
        {"iscc_id": "ISCC:EMPTY", "score": 0.30, "types": {}, "metadata": None},
    ]
    result = rerank_matches(matches)
    assert [m["iscc_id"] for m in result] == ["ISCC:EXACT", "ISCC:META"]
    assert result[0]["score"] == 1.0  # T1 exact, rescored from 0.50
    assert result[1]["score"] == TAU_SOFT  # T6 title-only, clamped from 0.82
    assert result[1]["metadata"] == {"k": "v"}  # non-score fields preserved


def test_rerank_tiebreak_promotes_stronger_unit():
    # type: () -> None
    """Two equally-tiered, equally-scored matches order by the stronger intrinsic unit."""
    content_only = {"iscc_id": "ISCC:C", "score": 0.0, "types": {"CONTENT_TEXT_V0": 0.8}}
    data_only = {"iscc_id": "ISCC:D", "score": 0.0, "types": {"DATA_NONE_V0": 0.8}}
    result = rerank_matches([content_only, data_only])
    assert [m["iscc_id"] for m in result] == ["ISCC:D", "ISCC:C"]
    assert result[0]["score"] == pytest.approx(T7_CAP)
    assert result[1]["score"] == pytest.approx(T7_CAP)


def test_rerank_empty_input():
    # type: () -> None
    """No matches in, no matches out."""
    assert rerank_matches([]) == []
