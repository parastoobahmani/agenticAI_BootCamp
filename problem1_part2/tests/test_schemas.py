import pytest
from pydantic import ValidationError

from problem1_part2.implementation.schemas import (
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


def test_case_from_part1_snapshot_records():
    issue = {"number": 17265, "title": "connection error", "body": "x", "html_url": "https://github.com/streamlit/streamlit/issues/17265"}
    comments = [
        {"issue_number": 17265, "id": 3, "body": "later", "created_at": "2026-10-05T13:00:00Z", "user_login": "reporter", "author_association": "NONE"},
        {"issue_number": 17265, "id": 1, "body": "please react", "created_at": "2026-10-05T12:37:26Z", "user_login": "github-actions[bot]", "author_association": "CONTRIBUTOR"},
        {"issue_number": 17265, "id": 2, "body": "earlier", "created_at": "2026-10-05T12:50:00Z", "user_login": "dev", "author_association": "COLLABORATOR"},
    ]

    case = Case.from_github(issue, comments)

    assert case.author is None
    assert [comment.id for comment in case.comments] == ["2", "3"]  # bot dropped, chronological
    assert case.comments[1].author == "reporter"
