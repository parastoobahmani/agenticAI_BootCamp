"""Build candidate next steps (questions, checks, follow-ups) and rank them."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from problem1_part2.implementation.facets import FACETS, Facet, FacetKind, ValueType
from problem1_part2.implementation.schemas import (
    FactStatus,
    KnownFact,
    MissingFacet,
    Probe,
    ProbeBasis,
    ProbeKind,
    SkippedProbe,
)
from problem1_part2.implementation.scoring import UNLISTED_CAUSE, Belief, BeliefModel

# An answer "favours" a hypothesis when it raises its probability by this factor.
_FAVOUR_RATIO = 1.15
_FOLLOW_UP_COST = 1
_PRECISION = 4


@dataclass(frozen=True)
class ProbeCandidates:
    ranked: list[Probe]  # positive information gain, best first
    fallback: list[Probe]  # generally useful missing details, highest priority first
    skipped: list[SkippedProbe]
    missing: list[MissingFacet]


def build_probes(model: BeliefModel, belief: Belief, facts: Mapping[str, KnownFact]) -> ProbeCandidates:
    ranked: list[Probe] = []
    skipped: list[SkippedProbe] = []
    missing: list[MissingFacet] = []

    for facet in FACETS:
        if facet.value_type is ValueType.TEXT:
            continue
        relevant = [key for key in belief if model.expectation(key, facet.id) is not None]
        fact = facts.get(facet.id)

        if fact is not None and fact.status is FactStatus.OBSERVED:
            if relevant or facet.kind is FacetKind.CHECK:
                skipped.append(_already_known(facet, fact))
            continue

        gain = model.information_gain(belief, facet)
        if relevant:
            missing.append(
                MissingFacet(
                    facet=facet.id,
                    description=facet.description,
                    relevant_hypotheses=relevant,
                    expected_information_gain=round(gain, _PRECISION),
                )
            )
        if gain > 0:
            ranked.append(_probe(facet, fact, gain, relevant, _rationale(model, belief, facet)))

    ranked.sort(key=lambda probe: probe.score, reverse=True)
    missing.sort(key=lambda item: item.expected_information_gain, reverse=True)
    return ProbeCandidates(ranked=ranked, fallback=_fallback(facts), skipped=skipped, missing=missing)


def _probe(facet: Facet, fact: KnownFact | None, gain: float, relevant: list[str], rationale: str) -> Probe:
    if fact is not None and fact.status is FactStatus.PERFORMED_OUTCOME_UNKNOWN:
        kind, cost = ProbeKind.FOLLOW_UP, _FOLLOW_UP_COST
        text = f'You mentioned: "{fact.origin.quote}". What was the result? {facet.prompt}'
    else:
        kind = ProbeKind.QUESTION if facet.kind is FacetKind.ATTRIBUTE else ProbeKind.CHECK
        cost, text = facet.cost, facet.prompt
    return Probe(
        facet=facet.id,
        kind=kind,
        basis=ProbeBasis.INFORMATION_GAIN,
        text=text,
        rationale=rationale,
        distinguishes=relevant,
        expected_information_gain=round(gain, _PRECISION),
        cost=cost,
        score=round(gain / cost, _PRECISION),
    )


def _fallback(facts: Mapping[str, KnownFact]) -> list[Probe]:
    """Details worth having when no question separates the hypotheses (never already-known ones)."""
    wanted = sorted(
        (facet for facet in FACETS if facet.fallback_priority > 0 and facet.id not in facts),
        key=lambda facet: facet.fallback_priority,
        reverse=True,
    )
    return [
        Probe(
            facet=facet.id,
            kind=ProbeKind.QUESTION if facet.kind is FacetKind.ATTRIBUTE else ProbeKind.CHECK,
            basis=ProbeBasis.FALLBACK,
            text=facet.prompt,
            rationale=f"Not stated in the case; needed to continue the investigation ({facet.description.lower()}).",
            distinguishes=[],
            expected_information_gain=0.0,
            cost=facet.cost,
            score=0.0,
        )
        for facet in wanted
    ]


def _already_known(facet: Facet, fact: KnownFact) -> SkippedProbe:
    verb = "already performed" if facet.kind is FacetKind.CHECK else "already stated"
    return SkippedProbe(
        facet=facet.id,
        reason=f'{verb} ({fact.origin.location}: "{fact.origin.quote}") -> {facet.id}={fact.value}',
    )


def _label(hypothesis_id: str) -> str:
    return "an unlisted cause" if hypothesis_id == UNLISTED_CAUSE else hypothesis_id


def _rationale(model: BeliefModel, belief: Belief, facet: Facet) -> str:
    if facet.value_type is ValueType.VERSION:
        ranges = [
            f"{_label(key)} applies to {facet.id.replace('_', ' ')} {expectation.version_spec}"
            for key in belief
            if (expectation := model.expectation(key, facet.id)) is not None
        ]
        return "; ".join(ranges)

    parts = []
    for value, _, after in model.outcomes(belief, facet):
        favoured = [
            _label(key) for key, p in after.items() if belief[key] > 0 and p >= belief[key] * _FAVOUR_RATIO
        ]
        if favoured:
            parts.append(f"'{value}' favours {', '.join(favoured)}")
    return "; ".join(parts)
