import json
from pathlib import Path

import pytest

from problem1_part2.implementation import AnalysisInput, Case, analyze
from problem1_part2.implementation.part1_adapter import SourceIndex, bundle_from_synthesis, case_from_snapshot
from problem1_part2.implementation.schemas import ClaimKind, DecisionType, SourceType

PART1 = Path(__file__).resolve().parent.parent / "examples" / "part1"


def _item(**overrides):
    item = {
        "score": 0.8,
        "claim_type": "hypothesis",
        "extracted_claim": "The value is reset on rerun.",
        "citation": "[documentation] Add statefulness to apps – (chunk aaa111)",
        "relevance_reason": "Matches symptoms (score=0.800).",
        "source_id": "doc-content-develop-concepts-architecture-session-state.md",
        "source_type": "documentation",
        "url": "Add statefulness to apps",
    }
    item.update(overrides)
    return item


@pytest.fixture
def snapshot(tmp_path: Path) -> Path:
    rows = {
        "documentation.jsonl": [
            {
                "id": "doc-content-develop-concepts-architecture-session-state.md",
                "url_or_path": "https://docs.streamlit.io/develop/concepts/architecture/session-state",
                "section": "content/develop/concepts/architecture/session-state.md",
                "commit": "d97e7bb",
                "version": None,
            }
        ],
        "release_notes.jsonl": [
            {"id": "release-1.65.0", "url_or_path": "https://github.com/streamlit/streamlit/releases/tag/1.65.0", "version": "1.65.0"}
        ],
        "issues.jsonl": [
            {"number": 42, "title": "Lost state", "body": "Streamlit version: 1.64.0", "html_url": "https://github.com/streamlit/streamlit/issues/42"}
        ],
        "comments.jsonl": [
            {"issue_number": 42, "id": 1, "body": "react please", "created_at": "2026-10-01T00:00:00Z", "user_login": "github-actions[bot]", "author_association": "CONTRIBUTOR"},
            {"issue_number": 7, "id": 2, "body": "other issue", "created_at": "2026-10-01T00:00:00Z", "user_login": "x", "author_association": "NONE"},
        ],
    }
    for name, records in rows.items():
        (tmp_path / name).write_text("\n".join(json.dumps(record) for record in records) + "\n")
    return tmp_path


def test_real_part1_output_converts_and_validates():
    result = json.loads((PART1 / "evidence_synthesis_result.json").read_text())
    bundle = bundle_from_synthesis(result)

    assert len(bundle.evidence) == len(result["evidence_used"])
    assert len({item.evidence_id for item in bundle.evidence}) == len(bundle.evidence)
    assert all(hypothesis.evidence_ids for hypothesis in bundle.hypotheses)
    assert any(item.url.startswith("https://github.com/streamlit/streamlit/issues/") for item in bundle.evidence)


def test_evidence_fields_are_mapped():
    [evidence] = bundle_from_synthesis({"evidence_used": [_item()]}).evidence

    assert evidence.evidence_id == "aaa111"
    assert evidence.source_type is SourceType.DOC
    assert evidence.claim_kind is ClaimKind.HYPOTHESIS
    assert evidence.title == "Add statefulness to apps"
    assert evidence.relevance == 0.8


def test_snapshot_index_restores_url_section_and_version(snapshot):
    [evidence] = bundle_from_synthesis({"evidence_used": [_item()]}, SourceIndex.from_snapshot(snapshot)).evidence

    assert evidence.url == "https://docs.streamlit.io/develop/concepts/architecture/session-state"
    assert evidence.section == "content/develop/concepts/architecture/session-state.md"
    assert evidence.source_version == "d97e7bb"


def test_release_note_about_a_fix_carries_fixed_in_version(snapshot):
    item = _item(
        source_id="release-1.65.0",
        source_type="release_note",
        claim_type="fact",
        extracted_claim="Fixed session state being reset after callbacks.",
        citation="[release_note] 1.65.0 – v1.65.0 – (chunk bbb222)",
    )
    [evidence] = bundle_from_synthesis({"evidence_used": [item]}, SourceIndex.from_snapshot(snapshot)).evidence

    assert evidence.claim_kind is ClaimKind.DOCUMENTED
    assert evidence.fixed_in_version == "1.65.0"


def test_duplicate_chunks_and_claims_are_disambiguated():
    bundle = bundle_from_synthesis({"evidence_used": [_item(), _item(score=0.5)]})

    assert [item.evidence_id for item in bundle.evidence] == ["aaa111", "aaa111#1"]
    assert len(bundle.hypotheses) == 1


def test_scores_are_clamped_to_unit_interval():
    [evidence] = bundle_from_synthesis({"evidence_used": [_item(score=1.7)]}).evidence
    assert evidence.relevance == 1.0


def test_conflicts_and_source_gaps_become_notes_but_user_gaps_do_not():
    bundle = bundle_from_synthesis(
        {
            "conflicting_sources": [{"description": "Docs and release note disagree."}],
            "remaining_gaps": [
                "No matching release note found – version that introduced/fixed the issue is unknown.",
                "User did not specify the exact product version or environment.",
            ],
        }
    )
    assert bundle.notes == [
        "Docs and release note disagree.",
        "No matching release note found – version that introduced/fixed the issue is unknown.",
    ]


def test_case_from_snapshot_drops_bots_and_other_issues(snapshot):
    case = case_from_snapshot(42, snapshot)
    assert case.case_id == "42"
    assert case.comments == []


def test_case_from_snapshot_unknown_issue(snapshot):
    with pytest.raises(LookupError):
        case_from_snapshot(999, snapshot)


def test_end_to_end_on_part1_demo_does_not_re_ask_known_details():
    result = json.loads((PART1 / "evidence_synthesis_result.json").read_text())
    case = Case.model_validate_json((PART1 / "session_state_case.json").read_text())

    report = analyze(AnalysisInput(case=case, evidence_bundle=bundle_from_synthesis(result)))

    known = {fact.facet for fact in report.known_facts}
    assert {"streamlit_version", "python_version", "browser", "code_snippet"} <= known
    assert not known & {step.facet for step in report.next_steps}
    assert report.decision.type is DecisionType.ESCALATE
    assert any(note.startswith("Part 1: ") for note in report.limitations)
