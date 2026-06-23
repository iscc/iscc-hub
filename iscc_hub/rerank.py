"""
Tiered Semantic Ranking (TSR) for similarity-search results.

Reorders and rescores the per-unit similarity matches returned by an iscc-search
backend into a total order that reflects the *kind* of relationship a candidate
expresses, not just the magnitude of a single strong signal. The raw backend
score is a confidence-weighted mean over matched units, so a candidate matching
only one unit type (typically META — title/author text, weak evidence of true
content identity) can outrank a candidate with broad corroborating evidence. TSR
fixes this: each candidate is assigned a semantic tier (exact / near-duplicate /
adaptation / corroborated / title-only / isolated / incoherent) from the structure
of its per-MainType scores, then ordered by tier first and a presence-aware
weighted score second, with single-signal tiers clamped below multi-signal ones.

This is a Python port of the client-side TSR validated in iscc-covers
(frontend/app.jsx), per its cauldron/tsr-spec.md. It reads only the per-`types`
scores already present in each match: a candidate can only match unit types the
query carries, so the candidate's own `types` keys are exactly the set of
MainTypes to aggregate — no ISCC decoding is needed.

The default weights are the "adaptation" preset (SEMANTIC-emphasised); thresholds
are the spec defaults. Both are module constants — tune them here if a corpus
needs a different balance.
"""

import operator

# Match thresholds (spec defaults). High-confidence, soft-match, and weak-corroboration
# floors; TAU_WEAK is the per-unit similarity floor distinguishable from random-match noise.
TAU_HIGH = 0.85
TAU_SOFT = 0.70
TAU_WEAK = 0.60

# Per-MainType weights for the presence-aware weighted mean ("adaptation" preset).
WEIGHTS = {"META": 0.5, "SEMANTIC": 2.0, "CONTENT": 0.8, "DATA": 0.3, "INSTANCE": 0.5}

# The five ISCC MainTypes TSR reasons about, in aggregation order.
MAINTYPES = ("META", "SEMANTIC", "CONTENT", "DATA", "INSTANCE")

# Per-unit tie-break order (strongest intrinsic evidence first) for equal tier+score.
TIEBREAK_ORDER = ("INSTANCE", "DATA", "CONTENT", "SEMANTIC", "META")

# Lower rank sorts first; the tier names the relationship kind. T0 (incoherent) sorts last.
TIER_ORDER = {"T1": 1, "T2": 2, "T3": 3, "T4": 4, "T5": 5, "T6": 6, "T7": 7, "T0": 8}

# Human-readable status emitted per tier (kept for callers that surface it).
TIER_STATUS = {
    "T1": "exact",
    "T2": "near-duplicate",
    "T3": "near-duplicate",
    "T4": "similar",
    "T5": "corroborated",
    "T6": "title-match",
    "T7": "weak",
    "T0": "incoherent",
}

# Score ceilings: T6 title-only and T7 isolated are clamped because single-signal
# evidence is categorically weaker than a multi-signal or high-confidence match.
TIER_CAP = {
    "T0": 0.0,
    "T1": 1.0,
    "T2": 1.0,
    "T3": 1.0,
    "T4": 1.0,
    "T5": 1.0,
    "T6": TAU_SOFT,
    "T7": TAU_SOFT * 0.9,
}

# Reliability of a lone signal for a T7 isolated candidate, applied before the cap.
# CONTENT is penalised hardest: perceptual-hash coincidences are the most common.
ISOLATED_PENALTY = {"SEMANTIC": 1.0, "DATA": 0.95, "META": 0.9, "CONTENT": 0.8, "INSTANCE": 1.0}


def aggregate_maintypes(types):
    # type: (dict) -> dict
    """
    Reduce per-UnitKey scores to per-MainType maxima over the known MainTypes.

    A query may carry several units of one MainType (different SubTypes); the
    candidate's strongest match for that MainType represents it. Keys whose
    MainType is not recognised are ignored.

    :param types: Backend per-unit scores, keyed like ``CONTENT_TEXT_V0``.
    :return: Mapping of MainType -> best score for that MainType.
    """
    agg = {}
    for maintype in MAINTYPES:
        prefix = maintype + "_"
        scores = [score for key, score in types.items() if key.startswith(prefix)]
        if scores:
            agg[maintype] = max(scores)
    return agg


def classify_tier(agg):
    # type: (dict) -> str|None
    """
    Assign a candidate to a semantic tier from its per-MainType scores.

    Tiers are decided by evidence structure (which signals agree, at what
    confidence), not magnitude alone. Returns None when no tier is supported
    (every unit below the soft-match floor) so the candidate is dropped as noise.

    :param agg: Per-MainType scores from aggregate_maintypes.
    :return: Tier label ``T0``..``T7``, or None when unsupported.
    """
    s_i = agg.get("INSTANCE")
    s_d = agg.get("DATA")
    s_c = agg.get("CONTENT")
    s_s = agg.get("SEMANTIC")
    s_m = agg.get("META")
    # Instance-Code match contradicted by a weak intrinsic signal -> incoherent.
    if (
        s_i is not None
        and s_i >= TAU_HIGH
        and ((s_d is not None and s_d < TAU_SOFT) or (s_c is not None and s_c < TAU_SOFT))
    ):
        return "T0"
    if s_i is not None and s_i >= TAU_HIGH:
        return "T1"
    if s_d is not None and s_d >= TAU_HIGH and (s_c is None or s_c >= TAU_HIGH):
        return "T2"
    count_soft = sum(1 for score in agg.values() if score >= TAU_SOFT)
    count_weak = sum(1 for score in agg.values() if score >= TAU_WEAK)
    # T3 requires Content-high AND a second unit at the soft floor: Content-Code alone
    # is too coincidence-prone on templated corpora to promote to near-duplicate.
    if s_c is not None and s_c >= TAU_HIGH and count_soft >= 2:
        return "T3"
    if s_s is not None and s_s >= TAU_HIGH:
        return "T4"
    # T5: one signal at the soft floor corroborated by a distinct second at the weak floor.
    if count_soft >= 1 and count_weak >= 2:
        return "T5"
    if s_m is not None and s_m >= TAU_HIGH and count_weak == 1:
        return "T6"
    if count_soft == 1:
        return "T7"
    return None


def weighted_score(agg):
    # type: (dict) -> float
    """
    Presence-aware weighted mean of per-MainType scores with a coherence bonus.

    The denominator sums weights only over present MainTypes (a unit absent from
    the candidate contributes to neither numerator nor denominator), so missing
    intrinsic units do not systematically deflate the score. A +5% bonus applies
    when two or more intrinsic signals unanimously agree (all high or all low).

    :param agg: Per-MainType scores from aggregate_maintypes.
    :return: Weighted score in 0.0..1.0.
    """
    num = sum(WEIGHTS[maintype] * score for maintype, score in agg.items())
    den = sum(WEIGHTS[maintype] for maintype in agg)
    base = num / den if den else 0.0
    intrinsic = [agg[maintype] for maintype in ("INSTANCE", "DATA", "CONTENT", "SEMANTIC") if maintype in agg]
    alpha = 1.0
    if len(intrinsic) >= 2:
        all_high = all(score >= TAU_HIGH for score in intrinsic)
        all_low = all(score < TAU_SOFT for score in intrinsic)
        if all_high or all_low:
            alpha = 1.05
    return min(1.0, base * alpha)


def tier_score(tier, agg):
    # type: (str, dict) -> float
    """
    Final score for a candidate: 1.0 for exact, 0.0 for incoherent, else the
    weighted mean scaled by any isolated-signal penalty and clamped to the tier cap.

    :param tier: Tier label from classify_tier.
    :param agg: Per-MainType scores from aggregate_maintypes.
    :return: Final TSR score in 0.0..1.0.
    """
    if tier == "T0":
        return 0.0
    if tier == "T1":
        return 1.0
    raw = weighted_score(agg)
    if tier == "T7":
        # A T7 candidate has exactly one unit at the soft floor; scale by its reliability.
        sole = next(maintype for maintype in agg if agg[maintype] >= TAU_SOFT)
        raw *= ISOLATED_PENALTY[sole]
    return min(raw, TIER_CAP[tier])


def sort_key(tier, score, agg):
    # type: (str, float, dict) -> tuple
    """
    Total-order key: tier rank ascending, score descending, then per-unit strength
    descending (a missing unit sorts after any present one).

    :param tier: Tier label from classify_tier.
    :param score: Final TSR score from tier_score.
    :param agg: Per-MainType scores from aggregate_maintypes.
    :return: Tuple sortable ascending to yield the desired ranking.
    """
    return (TIER_ORDER[tier], -score) + tuple(-agg.get(maintype, -1.0) for maintype in TIEBREAK_ORDER)


def rerank_matches(matches):
    # type: (list[dict]) -> list[dict]
    """
    Reorder and rescore backend matches by Tiered Semantic Ranking.

    Each surviving match keeps its documented fields with its ``score`` replaced
    by the TSR score; the list is returned ordered by tier, then score, then
    per-unit strength. Candidates supporting no tier (every unit below the
    soft-match floor, or no recognised unit types) are dropped as noise.

    :param matches: Projected backend matches, each with at least ``types`` and ``score``.
    :return: Reranked, rescored, noise-filtered matches.
    """
    ranked = []
    for match in matches:
        agg = aggregate_maintypes(match.get("types") or {})
        if not agg:
            continue
        tier = classify_tier(agg)
        if tier is None:
            continue
        scored = dict(match)
        scored["score"] = tier_score(tier, agg)
        ranked.append((sort_key(tier, scored["score"], agg), scored))
    ranked.sort(key=operator.itemgetter(0))
    return [scored for _, scored in ranked]
