import pytest
from pydantic import ValidationError

from missing_info.schemas import (
    Case,
    ClaimKind,
    Evidence,
    EvidenceBundle,
    Expectation,
    Hypothesis,
    SourceType,
)


def _evidence(evidence_id="e1", **overrides):
    fields = dict(
        evidence_id=evidence_id,
        source_type=SourceType.DOC,
        title="Deploy behind a proxy",
        url="https://docs.streamlit.io/x",
        snippet="...",
        relevance=0.8,
    )
    fields.update(overrides)
    return Evidence(**fields)


def test_case_from_github_maps_issue_and_comments():
    issue = {
        "number": 42,
        "title": "Stuck on loading",
        "body": None,
        "html_url": "https://github.com/streamlit/streamlit/issues/42",
        "user": {"login": "reporter"},
    }
    comments = [{"id": 7, "body": "same here", "author_association": "MEMBER", "user": {"login": "dev"}}]

    case = Case.from_github(issue, comments)

    assert case.case_id == "42"
    assert case.body == ""
    assert case.author == "reporter"
    assert case.comments[0].id == "7"
    assert case.comments[0].is_from_maintainer


def test_case_from_github_rejects_pull_requests():
    with pytest.raises(ValueError, match="pull request"):
        Case.from_github({"number": 1, "title": "x", "pull_request": {}})


@pytest.mark.parametrize(
    "fields",
    [{}, {"values": ["yes"], "version_spec": "<1.30"}, {"values": []}, {"version_spec": "not a spec"}],
)
def test_expectation_requires_exactly_one_valid_form(fields):
    with pytest.raises(ValidationError):
        Expectation(**fields)


def test_expectation_values_are_normalised():
    assert Expectation(values=[" Yes "]).values == ["yes"]


def test_bundle_rejects_dangling_evidence_reference():
    with pytest.raises(ValidationError, match="unknown evidence"):
        EvidenceBundle(
            evidence=[_evidence("e1")],
            hypotheses=[Hypothesis(hypothesis_id="h1", statement="s", confidence=0.5, evidence_ids=["e2"])],
        )


def test_bundle_rejects_duplicate_ids():
    with pytest.raises(ValidationError, match="unique"):
        EvidenceBundle(evidence=[_evidence("e1"), _evidence("e1")])


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"source_type": SourceType.DOC}, True),
        ({"source_type": SourceType.RELEASE_NOTE}, True),
        ({"source_type": SourceType.ISSUE, "author_association": "NONE"}, False),
        ({"source_type": SourceType.ISSUE, "author_association": "MEMBER"}, True),
        ({"source_type": SourceType.DOC, "claim_kind": ClaimKind.HYPOTHESIS}, False),
    ],
)
def test_evidence_authority(overrides, expected):
    assert _evidence(**overrides).is_authoritative is expected
