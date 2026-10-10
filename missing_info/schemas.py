"""Data contracts of this module.

Input  = the support case + the evidence bundle produced by part 1 (finding and
         combining evidence).
Output = ``NextStepReport``, consumed by part 3 (drafting the reply / case summary).

All models are pydantic so other parts of the project can validate payloads and
export JSON Schemas (``missing-info schema``).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from enum import Enum
from typing import Any

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "1.0"

MAINTAINER_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --------------------------------------------------------------------------- input


class Comment(_Model):
    """One message of the case conversation, in chronological order."""

    id: str
    body: str
    created_at: datetime | None = None
    author: str | None = None
    # GitHub author_association (OWNER, MEMBER, COLLABORATOR, CONTRIBUTOR, NONE, ...).
    author_association: str = "NONE"

    @field_validator("id", mode="before")
    @classmethod
    def _id_as_str(cls, value: Any) -> str:
        return str(value)

    @property
    def is_from_maintainer(self) -> bool:
        return self.author_association.upper() in MAINTAINER_ASSOCIATIONS


class Case(_Model):
    """The visible part of a support case at the time of analysis."""

    case_id: str
    title: str
    body: str = ""
    url: str | None = None
    author: str | None = None
    created_at: datetime | None = None
    comments: list[Comment] = Field(default_factory=list)

    @field_validator("case_id", mode="before")
    @classmethod
    def _case_id_as_str(cls, value: Any) -> str:
        return str(value)

    @classmethod
    def from_github(cls, issue: dict[str, Any], comments: Iterable[dict[str, Any]] = ()) -> Case:
        """Build a case from GitHub issue + comment records.

        Accepts both the raw REST API shape (``user.login``) and the flattened
        snapshot shape of part 1's ``issues.jsonl`` / ``comments.jsonl``
        (``user_login``). Bot comments are automatic replies and are dropped.
        """
        if "pull_request" in issue:
            raise ValueError(f"#{issue.get('number')} is a pull request, not an issue")
        human_comments = [comment for comment in comments if not _is_bot(_login(comment))]
        return cls(
            case_id=str(issue["number"]),
            title=issue["title"],
            body=issue.get("body") or "",
            url=issue.get("html_url"),
            author=_login(issue),
            created_at=issue.get("created_at"),
            comments=[
                Comment(
                    id=comment["id"],
                    body=comment.get("body") or "",
                    created_at=comment.get("created_at"),
                    author=_login(comment),
                    author_association=comment.get("author_association") or "NONE",
                )
                for comment in sorted(human_comments, key=lambda comment: comment.get("created_at") or "")
            ],
        )


def _login(record: dict[str, Any]) -> str | None:
    return (record.get("user") or {}).get("login") or record.get("user_login")


def _is_bot(login: str | None) -> bool:
    return bool(login) and login.endswith("[bot]")


class SourceType(str, Enum):
    DOC = "doc"
    ISSUE = "issue"
    RELEASE_NOTE = "release_note"


class ClaimKind(str, Enum):
    """Epistemic status of a piece of evidence (required by part 1)."""

    REPORTED_FACT = "reported_fact"  # something a user observed
    DOCUMENTED = "documented"  # stated by official docs / release notes / maintainers
    HYPOTHESIS = "hypothesis"  # the assistant's own inference


class Evidence(_Model):
    """One retrieved source chunk, as produced by part 1."""

    evidence_id: str
    source_type: SourceType
    title: str
    url: str
    section: str | None = None
    snippet: str
    # Docs commit SHA, release version or issue snapshot date.
    source_version: str | None = None
    relevance: float = Field(ge=0.0, le=1.0)
    # Human-readable link between this source and the case (from part 1).
    relation: str | None = None
    claim_kind: ClaimKind = ClaimKind.DOCUMENTED
    # Streamlit version that fixed the problem described by this source, if any.
    fixed_in_version: str | None = None
    # For issue/comment evidence: GitHub author_association of the statement's author.
    author_association: str | None = None

    @property
    def is_authoritative(self) -> bool:
        """True when the source can back a claim on its own (not just "a similar report")."""
        if self.claim_kind is ClaimKind.HYPOTHESIS:
            return False
        if self.source_type in (SourceType.DOC, SourceType.RELEASE_NOTE):
            return True
        return (self.author_association or "").upper() in MAINTAINER_ASSOCIATIONS


class Expectation(_Model):
    """What a hypothesis predicts about one facet: a set of values OR a version range."""

    values: list[str] | None = None
    version_spec: str | None = None

    @model_validator(mode="after")
    def _exactly_one_form(self) -> Expectation:
        if (self.values is None) == (self.version_spec is None):
            raise ValueError("an expectation needs exactly one of 'values' or 'version_spec'")
        if self.values is not None and not self.values:
            raise ValueError("'values' must not be empty")
        if self.version_spec is not None:
            try:
                SpecifierSet(self.version_spec)
            except InvalidSpecifier as exc:
                raise ValueError(f"invalid version_spec {self.version_spec!r}") from exc
        return self

    @field_validator("values")
    @classmethod
    def _normalise_values(cls, values: list[str] | None) -> list[str] | None:
        return None if values is None else [value.strip().lower() for value in values]


class Hypothesis(_Model):
    """A candidate explanation proposed by part 1."""

    hypothesis_id: str
    statement: str
    # Plausibility score from part 1 in [0, 1]; normalised into a prior here.
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)
    # Optional: facet id -> what the hypothesis predicts. Inferred when omitted.
    expectations: dict[str, Expectation] | None = None


class EvidenceBundle(_Model):
    evidence: list[Evidence] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    # Caveats reported by part 1 (e.g. conflicting sources), passed on as limitations.
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_references(self) -> EvidenceBundle:
        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence_id values must be unique")
        hypothesis_ids = [item.hypothesis_id for item in self.hypotheses]
        if len(hypothesis_ids) != len(set(hypothesis_ids)):
            raise ValueError("hypothesis_id values must be unique")
        known = set(evidence_ids)
        for hypothesis in self.hypotheses:
            missing = [ref for ref in hypothesis.evidence_ids if ref not in known]
            if missing:
                raise ValueError(
                    f"hypothesis {hypothesis.hypothesis_id!r} references unknown evidence {missing}"
                )
        return self

    def evidence_for(self, hypothesis: Hypothesis) -> list[Evidence]:
        by_id = {item.evidence_id: item for item in self.evidence}
        return [by_id[ref] for ref in hypothesis.evidence_ids]


class AnalysisInput(_Model):
    case: Case
    evidence_bundle: EvidenceBundle = Field(default_factory=EvidenceBundle)


# -------------------------------------------------------------------------- output


class FactStatus(str, Enum):
    OBSERVED = "observed"  # the value is stated in the case
    PERFORMED_OUTCOME_UNKNOWN = "performed_outcome_unknown"  # check done, result not given


class FactOrigin(_Model):
    location: str  # "title", "body" or "comment:<id>"
    quote: str


class FactObservation(_Model):
    facet: str
    value: str | None
    status: FactStatus
    origin: FactOrigin


class KnownFact(_Model):
    facet: str
    value: str | None
    status: FactStatus
    origin: FactOrigin
    # Earlier, contradicting statements (e.g. the user corrected themselves).
    superseded: list[FactObservation] = Field(default_factory=list)


class EvidenceStrength(str, Enum):
    STRONG = "strong"  # docs, release notes or maintainer statements
    WEAK = "weak"  # only similar user reports
    NONE = "none"


class RankedHypothesis(_Model):
    hypothesis_id: str
    statement: str
    prior: float
    posterior: float
    evidence_strength: EvidenceStrength
    evidence_ids: list[str]
    expectations: dict[str, Expectation]
    expectation_source: str  # "bundle", "rules", "llm", "none" or a "+"-joined mix
    consistent_facts: list[str]
    conflicting_facts: list[str]


class ProbeKind(str, Enum):
    QUESTION = "question"  # the user already knows the answer
    CHECK = "check"  # the user has to run something
    FOLLOW_UP = "follow_up"  # the user did the check but did not report the result


class ProbeBasis(str, Enum):
    INFORMATION_GAIN = "information_gain"  # separates the current hypotheses
    FALLBACK = "fallback"  # generally useful missing info when nothing separates them


class Probe(_Model):
    facet: str
    kind: ProbeKind
    basis: ProbeBasis
    text: str
    rationale: str
    distinguishes: list[str]
    expected_information_gain: float
    cost: int
    score: float


class MissingFacet(_Model):
    facet: str
    description: str
    relevant_hypotheses: list[str]
    expected_information_gain: float


class SkippedProbe(_Model):
    facet: str
    reason: str


class DecisionType(str, Enum):
    PROPOSE_ANSWER = "propose_answer"
    REQUEST_INFORMATION = "request_information"
    ESCALATE = "escalate"


class Decision(_Model):
    type: DecisionType
    rationale: str
    hypothesis_id: str | None = None


class NextStepReport(_Model):
    schema_version: str = SCHEMA_VERSION
    case_id: str
    decision: Decision
    known_facts: list[KnownFact]
    missing_information: list[MissingFacet]
    hypotheses: list[RankedHypothesis]
    next_steps: list[Probe]
    skipped_probes: list[SkippedProbe]
    limitations: list[str]
