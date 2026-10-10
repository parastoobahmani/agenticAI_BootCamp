"""End-to-end analysis: case + evidence bundle -> NextStepReport."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from missing_info.config import AnalyzerConfig
from missing_info.decision import decide, evidence_strength
from missing_info.expectations import matches
from missing_info.extraction import extract_facts
from missing_info.facets import FACETS_BY_ID, ValueType
from missing_info.probes import build_probes
from missing_info.profiling import ExpectationProfiler, ProfiledHypothesis, RuleBasedProfiler, profile_hypothesis
from missing_info.schemas import (
    AnalysisInput,
    EvidenceBundle,
    EvidenceStrength,
    FactStatus,
    KnownFact,
    NextStepReport,
    RankedHypothesis,
)
from missing_info.scoring import UNLISTED_CAUSE, Belief, BeliefModel, prior_belief

_PRECISION = 4
_UNLISTED_STATEMENT = "A cause that none of the retrieved evidence describes."
_UNLISTED_WARNING_THRESHOLD = 0.3


def analyze(
    data: AnalysisInput,
    config: AnalyzerConfig | None = None,
    profilers: Sequence[ExpectationProfiler] | None = None,
) -> NextStepReport:
    """Analyze one case. ``profilers`` are tried in order (default: rule-based only)."""
    config = config or AnalyzerConfig()
    profilers = profilers if profilers is not None else (RuleBasedProfiler(),)
    bundle = data.evidence_bundle

    facts = {fact.facet: fact for fact in extract_facts(data.case)}
    profiled = [profile_hypothesis(item, bundle.evidence_for(item), profilers) for item in bundle.hypotheses]

    model = BeliefModel(
        {item.hypothesis.hypothesis_id: item.expectations for item in profiled},
        config.observation_noise,
    )
    prior = prior_belief(
        {item.hypothesis_id: item.confidence for item in bundle.hypotheses},
        config.unlisted_cause_prior,
    )
    belief = _condition_on_facts(model, prior, facts.values())

    hypotheses = _rank(profiled, bundle, prior, belief, facts)
    candidates = build_probes(model, belief, facts)
    outcome = decide(hypotheses, candidates, config)

    return NextStepReport(
        case_id=data.case.case_id,
        decision=outcome.decision,
        known_facts=list(facts.values()),
        missing_information=candidates.missing,
        hypotheses=hypotheses,
        next_steps=outcome.next_steps,
        skipped_probes=candidates.skipped,
        limitations=[f"Part 1: {note}" for note in bundle.notes] + _limitations(profiled, hypotheses, facts.values()),
    )


def _condition_on_facts(model: BeliefModel, belief: Belief, facts: Iterable[KnownFact]) -> Belief:
    for fact in facts:
        facet = FACETS_BY_ID[fact.facet]
        if fact.status is FactStatus.OBSERVED and fact.value and facet.value_type is not ValueType.TEXT:
            belief = model.update(belief, facet, fact.value)
    return belief


def _rank(
    profiled: list[ProfiledHypothesis],
    bundle: EvidenceBundle,
    prior: Belief,
    belief: Belief,
    facts: dict[str, KnownFact],
) -> list[RankedHypothesis]:
    ranked = []
    for item in profiled:
        hypothesis = item.hypothesis
        consistent, conflicting = _fact_agreement(item, facts)
        ranked.append(
            RankedHypothesis(
                hypothesis_id=hypothesis.hypothesis_id,
                statement=hypothesis.statement,
                prior=round(prior[hypothesis.hypothesis_id], _PRECISION),
                posterior=round(belief[hypothesis.hypothesis_id], _PRECISION),
                evidence_strength=evidence_strength(bundle.evidence_for(hypothesis)),
                evidence_ids=hypothesis.evidence_ids,
                expectations=item.expectations,
                expectation_source=item.source,
                consistent_facts=consistent,
                conflicting_facts=conflicting,
            )
        )
    ranked.append(
        RankedHypothesis(
            hypothesis_id=UNLISTED_CAUSE,
            statement=_UNLISTED_STATEMENT,
            prior=round(prior[UNLISTED_CAUSE], _PRECISION),
            posterior=round(belief[UNLISTED_CAUSE], _PRECISION),
            evidence_strength=EvidenceStrength.NONE,
            evidence_ids=[],
            expectations={},
            expectation_source="none",
            consistent_facts=[],
            conflicting_facts=[],
        )
    )
    ranked.sort(key=lambda item: item.posterior, reverse=True)
    return ranked


def _fact_agreement(item: ProfiledHypothesis, facts: dict[str, KnownFact]) -> tuple[list[str], list[str]]:
    consistent, conflicting = [], []
    for facet_id, expectation in item.expectations.items():
        fact = facts.get(facet_id)
        if fact is None or fact.status is not FactStatus.OBSERVED or fact.value is None:
            continue
        verdict = matches(expectation, fact.value)
        if verdict is True:
            consistent.append(f"{facet_id}={fact.value}")
        elif verdict is False:
            conflicting.append(f"{facet_id}={fact.value}")
    return consistent, conflicting


def _limitations(
    profiled: list[ProfiledHypothesis],
    hypotheses: list[RankedHypothesis],
    facts: Iterable[KnownFact],
) -> list[str]:
    notes = [warning for item in profiled for warning in item.warnings]
    listed = [item for item in hypotheses if item.hypothesis_id != UNLISTED_CAUSE]

    if not listed:
        notes.append("No candidate explanation was found in the evidence base.")
    untestable = [item.hypothesis_id for item in listed if item.expectation_source == "none"]
    if untestable:
        notes.append(
            f"{', '.join(untestable)}: no testable prediction, so no question can confirm or rule "
            f"{'it' if len(untestable) == 1 else 'them'} out."
        )
    for item in listed:
        if item.conflicting_facts:
            notes.append(f"{item.hypothesis_id} conflicts with reported facts: {', '.join(item.conflicting_facts)}.")
    if listed and listed[0].evidence_strength is not EvidenceStrength.STRONG:
        notes.append(
            f"The leading explanation {listed[0].hypothesis_id} rests only on similar reports; "
            "a similar report does not prove the same root cause."
        )

    unlisted = next(item.posterior for item in hypotheses if item.hypothesis_id == UNLISTED_CAUSE)
    if listed and unlisted >= _UNLISTED_WARNING_THRESHOLD:
        notes.append(f"There is a {unlisted:.0%} chance that the cause is none of the listed explanations.")

    for fact in facts:
        for old in fact.superseded:
            notes.append(
                f"The user corrected {fact.facet}: '{old.value}' ({old.origin.location}) -> "
                f"'{fact.value}' ({fact.origin.location}); the latest statement is used."
            )
    return notes
