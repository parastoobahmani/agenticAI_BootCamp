"""Turn hypotheses into testable expectations ("if H is true, facet F should be V").

Expectations are what makes a question discriminating: a question is useful when
different hypotheses predict different answers to it.

Sources, in order of precedence:
1. ``Hypothesis.expectations`` supplied by part 1 (``"bundle"``);
2. an ordered list of pluggable ``ExpectationProfiler``s, each filling only the
   facets the previous ones left open, e.g. the LLM profiler in ``llm.py``
   (``"llm"``) followed by the rule-based profiler below (``"rules"``).

Expectations that do not fit the facet catalogue are dropped with a warning
instead of failing the whole analysis.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from packaging.version import Version

from missing_info.expectations import is_valid_for, parse_version
from missing_info.facets import FACETS_BY_ID
from missing_info.schemas import Evidence, Expectation, Hypothesis

_FLAGS = re.IGNORECASE
_VERSION = r"v?(\d+\.\d+(?:\.\d+)?)"

YES = Expectation(values=["yes"])
NO = Expectation(values=["no"])


class ExpectationProfiler(Protocol):
    name: str

    def profile(self, hypothesis: Hypothesis, evidence: list[Evidence]) -> dict[str, Expectation]:
        """Expectations for ``hypothesis``; may return facets outside the catalogue."""


@dataclass(frozen=True)
class ProfileRule:
    pattern: re.Pattern[str]
    expectations: Mapping[str, Expectation]


def _profile_rule(pattern: str, **expectations: Expectation) -> ProfileRule:
    return ProfileRule(re.compile(pattern, _FLAGS), expectations)


# Keyword -> what a hypothesis of that family predicts. The first rule that sets
# a facet wins, so more specific families come first.
PROFILE_RULES: tuple[ProfileRule, ...] = (
    _profile_rule(
        r"\bcors\b|\bxsrf\b|\bcsrf\b|enableCORS|enableXsrfProtection",
        websocket_error_in_console=YES,
        health_endpoint_ok=YES,
        reproduces_locally=NO,
    ),
    _profile_rule(
        r"baseUrlPath|\bsub-?path\b|\bpath prefix\b|\bbase url\b",
        served_under_subpath=YES,
        health_endpoint_ok=YES,
        reproduces_locally=NO,
    ),
    _profile_rule(
        r"websocket|reverse[- ]proxy|\bproxy\b|\bnginx\b|\bapache\b|traefik|load[- ]balancer|\bingress\b|"
        r"upgrade header|connection upgrade",
        reverse_proxy=YES,
        websocket_error_in_console=YES,
        health_endpoint_ok=YES,
        reproduces_locally=NO,
    ),
    _profile_rule(
        r"firewall|security group|port (?:is )?(?:not|closed|blocked)|not (?:exposed|reachable|listening)|"
        r"server\.address|server\.port|bind(?:ing)? (?:to|address)|0\.0\.0\.0|process (?:crash|exit|killed)",
        health_endpoint_ok=NO,
        reproduces_locally=NO,
    ),
    _profile_rule(
        r"browser (?:extension|cache)|ad[- ]?block|\bextensions?\b|browser[- ]specific|\bsafari\b|\bfirefox\b",
        reproduces_in_other_browser=NO,
    ),
    _profile_rule(
        r"corrupt|broken (?:install|environment|venv)|(?:dependency|package|version) (?:conflict|mismatch)|"
        r"(?:incompatible|conflicting) (?:package|dependenc)",
        reinstall_resolves=YES,
    ),
    _profile_rule(r"\bcach(?:e|ed|ing)\b|st\.cache|memoi[sz]", cache_clear_resolves=YES),
    _profile_rule(
        r"\bmemory\b|\boom\b|resource limits?|\bcpu\b|out of resources",
        reproduces_locally=NO,
    ),
    _profile_rule(r"\bwindows\b", operating_system=Expectation(values=["windows"])),
    _profile_rule(r"\bmac ?os\b|\bos ?x\b", operating_system=Expectation(values=["macos"])),
    _profile_rule(r"\blinux\b", operating_system=Expectation(values=["linux"])),
)

_FIXED_IN = re.compile(r"(?:fixed|resolved|patched) in (?:streamlit )?" + _VERSION, _FLAGS)
_INTRODUCED_IN = re.compile(r"(?:introduced|regression|started|broke\w*) in (?:streamlit )?" + _VERSION, _FLAGS)


def version_expectations(hypothesis: Hypothesis, evidence: list[Evidence]) -> dict[str, Expectation]:
    """Expectations for "known bug, introduced in X / fixed in Y" hypotheses.

    The fix version comes from the statement or, failing that, from the newest
    ``fixed_in_version`` among the supporting evidence (release notes, closed issues).
    """
    fixed = _first_version(_FIXED_IN, hypothesis.statement) or _newest(
        item.fixed_in_version for item in evidence if item.fixed_in_version
    )
    introduced = _first_version(_INTRODUCED_IN, hypothesis.statement)

    bounds = []
    if introduced:
        bounds.append(f">={introduced}")
    if fixed:
        bounds.append(f"<{fixed}")
    if not bounds:
        return {}
    expectations = {"streamlit_version": Expectation(version_spec=",".join(bounds))}
    if fixed:
        expectations["upgrade_resolves"] = YES
    return expectations


def _first_version(pattern: re.Pattern[str], text: str) -> Version | None:
    match = pattern.search(text)
    return parse_version(match.group(1)) if match else None


def _newest(values: Iterable[str]) -> Version | None:
    versions = [version for value in values if (version := parse_version(value)) is not None]
    return max(versions, default=None)


class RuleBasedProfiler:
    name = "rules"

    def __init__(self, rules: tuple[ProfileRule, ...] = PROFILE_RULES) -> None:
        self._rules = rules

    def profile(self, hypothesis: Hypothesis, evidence: list[Evidence]) -> dict[str, Expectation]:
        expectations = version_expectations(hypothesis, evidence)
        for rule in self._rules:
            if rule.pattern.search(hypothesis.statement):
                for facet_id, expectation in rule.expectations.items():
                    expectations.setdefault(facet_id, expectation)
        return expectations


@dataclass(frozen=True)
class ProfiledHypothesis:
    hypothesis: Hypothesis
    expectations: dict[str, Expectation]
    source: str
    warnings: list[str] = field(default_factory=list)


def profile_hypothesis(
    hypothesis: Hypothesis,
    evidence: list[Evidence],
    profilers: Sequence[ExpectationProfiler],
) -> ProfiledHypothesis:
    warnings: list[str] = []
    sources: list[str] = []

    expectations = _valid_only(hypothesis.expectations or {}, f"hypothesis {hypothesis.hypothesis_id}", warnings)
    if expectations:
        sources.append("bundle")

    for profiler in profilers:
        inferred = _valid_only(
            profiler.profile(hypothesis, evidence),
            f"{profiler.name} profiler for {hypothesis.hypothesis_id}",
            warnings,
        )
        added = {facet_id: item for facet_id, item in inferred.items() if facet_id not in expectations}
        if added:
            sources.append(profiler.name)
            expectations.update(added)

    return ProfiledHypothesis(
        hypothesis=hypothesis,
        expectations=expectations,
        source="+".join(sources) or "none",
        warnings=warnings,
    )


def _valid_only(expectations: Mapping[str, Expectation], origin: str, warnings: list[str]) -> dict[str, Expectation]:
    valid: dict[str, Expectation] = {}
    for facet_id, expectation in expectations.items():
        facet = FACETS_BY_ID.get(facet_id)
        if facet is None:
            warnings.append(f"{origin}: ignored expectation on unknown facet {facet_id!r}")
        elif not is_valid_for(facet, expectation):
            warnings.append(f"{origin}: ignored expectation that does not fit facet {facet_id!r}")
        else:
            valid[facet_id] = expectation
    return valid
