"""Choose between proposing an answer, requesting information and escalating."""

from __future__ import annotations

from dataclasses import dataclass

from missing_info.config import AnalyzerConfig
from missing_info.probes import ProbeCandidates
from missing_info.schemas import (
    Decision,
    DecisionType,
    Evidence,
    EvidenceStrength,
    Probe,
    RankedHypothesis,
)
from missing_info.scoring import UNLISTED_CAUSE


def evidence_strength(evidence: list[Evidence]) -> EvidenceStrength:
    """Strong = docs, release notes or maintainers; weak = only similar user reports.

    A similar report alone does not prove that two problems share a cause.
    """
    if not evidence:
        return EvidenceStrength.NONE
    if any(item.is_authoritative for item in evidence):
        return EvidenceStrength.STRONG
    return EvidenceStrength.WEAK


@dataclass(frozen=True)
class Outcome:
    decision: Decision
    next_steps: list[Probe]


def decide(hypotheses: list[RankedHypothesis], probes: ProbeCandidates, config: AnalyzerConfig) -> Outcome:
    """``hypotheses`` must be sorted by posterior and include the unlisted-cause entry."""
    listed = [item for item in hypotheses if item.hypothesis_id != UNLISTED_CAUSE]
    informative = [probe for probe in probes.ranked if probe.score >= config.min_information_gain]
    informative = informative[: config.max_probes]

    if not listed:
        return Outcome(
            Decision(
                type=DecisionType.ESCALATE,
                rationale="Part 1 produced no candidate explanation, so no answer can be defended. "
                "Collect the missing basics below and refer the case for manual investigation.",
            ),
            probes.fallback[: config.max_probes],
        )

    top = hypotheses[0]
    runner_up = hypotheses[1].posterior if len(hypotheses) > 1 else 0.0
    is_leading = (
        top.hypothesis_id != UNLISTED_CAUSE
        and top.posterior >= config.answer_threshold
        and top.posterior - runner_up >= config.answer_margin
    )
    well_supported = top.evidence_strength is EvidenceStrength.STRONG or not config.require_strong_evidence_for_answer

    if is_leading and well_supported:
        return Outcome(
            Decision(
                type=DecisionType.PROPOSE_ANSWER,
                hypothesis_id=top.hypothesis_id,
                rationale=f"{top.hypothesis_id} is the leading explanation (posterior {top.posterior:.2f}, "
                f"runner-up {runner_up:.2f}) and is backed by authoritative sources. "
                "Any step listed is an optional confirmation.",
            ),
            informative[:1],
        )

    if informative:
        if is_leading:
            rationale = (
                f"{top.hypothesis_id} leads (posterior {top.posterior:.2f}) but is supported only by similar "
                "reports, which do not prove the same cause; confirm it before proposing a fix."
            )
        else:
            plausible = [item.hypothesis_id for item in hypotheses if item.posterior >= 0.1]
            rationale = (
                f"No explanation is clearly ahead ({', '.join(plausible)} remain plausible). "
                "The steps below are the ones whose answers best separate them per unit of user effort."
            )
        return Outcome(Decision(type=DecisionType.REQUEST_INFORMATION, rationale=rationale), informative)

    if is_leading:
        reason = (
            f"{top.hypothesis_id} leads (posterior {top.posterior:.2f}) but is supported only by similar "
            "reports, and no available question or check can confirm it."
        )
    else:
        reason = (
            f"No explanation is decisive (best: {top.hypothesis_id} at {top.posterior:.2f}) and no available "
            "question or check separates the remaining ones."
        )
    return Outcome(
        Decision(
            type=DecisionType.ESCALATE,
            rationale=f"{reason} Refer the case with the evidence collected so far.",
        ),
        probes.fallback[: config.max_probes],
    )
