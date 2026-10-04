"""Belief over hypotheses and the value of asking about a facet.

Model
-----
* Belief: a probability distribution over the hypotheses of part 1 plus one
  extra ``UNLISTED_CAUSE`` hypothesis that predicts nothing.
* Prior: part-1 confidences normalised to ``1 - unlisted_cause_prior``.
* Likelihood of an answer ``v`` to facet ``f`` under hypothesis ``h``, among the
  candidate answers ``C`` of ``f``:
    - ``h`` has no expectation on ``f``         -> uniform ``1 / |C|``
    - ``v`` satisfies ``h``'s expectation (set M) -> ``(1 - noise) / |M|``
    - otherwise                                 -> ``noise / (|C| - |M|)``
* Known facts update the belief with Bayes' rule.
* A probe's value is its expected information gain (bits): the expected drop in
  entropy of the belief once the user answers. A question every hypothesis
  answers the same way is worth 0 bits, however "standard" it is.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

from missing_info.expectations import candidate_values, matches
from missing_info.facets import Facet
from missing_info.schemas import Expectation

UNLISTED_CAUSE = "unlisted_cause"

Belief = dict[str, float]


def prior_belief(confidences: Mapping[str, float], unlisted_cause_prior: float) -> Belief:
    if not confidences:
        return {UNLISTED_CAUSE: 1.0}
    total = sum(confidences.values())
    listed_mass = 1.0 - unlisted_cause_prior
    if total > 0:
        belief = {key: listed_mass * value / total for key, value in confidences.items()}
    else:
        belief = {key: listed_mass / len(confidences) for key in confidences}
    belief[UNLISTED_CAUSE] = unlisted_cause_prior
    return belief


def entropy(belief: Belief) -> float:
    return -sum(p * math.log2(p) for p in belief.values() if p > 0)


def _normalise(weights: Mapping[str, float]) -> Belief:
    total = sum(weights.values())
    if total <= 0:
        return {key: 1.0 / len(weights) for key in weights}
    return {key: value / total for key, value in weights.items()}


class BeliefModel:
    """Likelihoods, Bayesian updates and information gain for a set of hypotheses."""

    def __init__(self, expectations: Mapping[str, Mapping[str, Expectation]], noise: float) -> None:
        # hypothesis id -> facet id -> expectation (UNLISTED_CAUSE has none)
        self._expectations = expectations
        self._noise = noise

    def expectation(self, hypothesis_id: str, facet_id: str) -> Expectation | None:
        return self._expectations.get(hypothesis_id, {}).get(facet_id)

    def candidates(self, facet: Facet, extra: str | None = None) -> list[str]:
        relevant = [
            expectation
            for per_facet in self._expectations.values()
            if (expectation := per_facet.get(facet.id)) is not None
        ]
        values = candidate_values(facet, relevant)
        if extra is not None and extra not in values:
            values.append(extra)
        return values

    def likelihood(self, hypothesis_id: str, facet: Facet, value: str, candidates: list[str]) -> float:
        uniform = 1.0 / len(candidates)
        expectation = self.expectation(hypothesis_id, facet.id)
        if expectation is None or matches(expectation, value) is None:
            return uniform
        satisfying = [candidate for candidate in candidates if matches(expectation, candidate)]
        if not satisfying or len(satisfying) == len(candidates):
            return uniform
        if matches(expectation, value):
            return (1.0 - self._noise) / len(satisfying)
        return self._noise / (len(candidates) - len(satisfying))

    def update(self, belief: Belief, facet: Facet, value: str) -> Belief:
        candidates = self.candidates(facet, extra=value)
        if not candidates:
            return belief
        return _normalise(
            {key: p * self.likelihood(key, facet, value, candidates) for key, p in belief.items()}
        )

    def outcomes(self, belief: Belief, facet: Facet) -> list[tuple[str, float, Belief]]:
        """Each possible answer with its probability and the belief it would lead to."""
        candidates = self.candidates(facet)
        results = []
        for value in candidates:
            joint = {key: p * self.likelihood(key, facet, value, candidates) for key, p in belief.items()}
            probability = sum(joint.values())
            if probability > 0:
                results.append((value, probability, _normalise(joint)))
        return results

    def information_gain(self, belief: Belief, facet: Facet) -> float:
        outcomes = self.outcomes(belief, facet)
        if not outcomes:
            return 0.0
        expected_entropy = sum(probability * entropy(after) for _, probability, after in outcomes)
        return max(0.0, entropy(belief) - expected_entropy)
