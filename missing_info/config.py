"""Tunable thresholds of the analyzer, kept in one place so they can be swept."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnalyzerConfig:
    # Probability that an observation contradicts a hypothesis that is actually true
    # (noise in user reports, imprecise expectations).
    observation_noise: float = 0.15

    # Hypotheses from part 1 are never exhaustive. This much prior mass is reserved
    # for "a cause none of the listed hypotheses describes", so that facts
    # contradicting every listed hypothesis lower our confidence instead of
    # silently promoting the least-bad one.
    unlisted_cause_prior: float = 0.20

    # A hypothesis must reach this posterior to be proposed as the answer.
    answer_threshold: float = 0.70
    # ...and lead the runner-up by at least this much.
    answer_margin: float = 0.25

    # Probes whose expected information gain (bits) per unit of cost is below this
    # value are not worth asking.
    min_information_gain: float = 0.05

    # Upper bound on how many questions/checks we return at once. Asking more than a
    # couple of things at a time lowers the chance the user answers any of them.
    max_probes: int = 2

    # Hypotheses supported only by similar issues (no docs, release notes or
    # maintainer statements) cannot be proposed as the answer without a check.
    require_strong_evidence_for_answer: bool = True

    def __post_init__(self) -> None:
        if not 0.0 < self.observation_noise < 0.5:
            raise ValueError("observation_noise must be in (0, 0.5)")
        if not 0.0 < self.unlisted_cause_prior < 1.0:
            raise ValueError("unlisted_cause_prior must be in (0, 1)")
        if not 0.0 < self.answer_threshold <= 1.0:
            raise ValueError("answer_threshold must be in (0, 1]")
        if self.max_probes < 1:
            raise ValueError("max_probes must be >= 1")
