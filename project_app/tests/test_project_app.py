from __future__ import annotations

import json
from pathlib import Path

import pytest

from problem1_part1.evidence_synthesis.evidence_core import SourceDocument
from problem2_parts1_2.storage import Storage
from project_app import PendingProposalError, ProjectPipeline


def documents() -> list[SourceDocument]:
    return [
        SourceDocument(
            id="doc-loading",
            source_type="documentation",
            title="Remote loading troubleshooting",
            content=(
                "A remotely deployed app that remains on the loading screen may have a WebSocket "
                "connection blocked by its reverse proxy. Check WebSocket upgrade forwarding."
            ),
            url_or_path="https://docs.example.test/remote-loading",
        ),
        SourceDocument(
            id="issue-loading",
            source_type="past_report",
            title="Loading screen behind nginx",
            content=(
                "A user reports that the app works locally but stays on the loading screen behind nginx. "
                "The maintainer requested the server version and browser network result."
            ),
            url_or_path="https://issues.example.test/42",
        ),
    ]


def case(version: str = "1.30.0") -> dict:
    return {
        "case_id": "case-42",
        "title": "App stays on the loading screen behind nginx",
        "body": f"It works locally. The server uses Streamlit {version} on Linux behind nginx.",
        "comments": [],
    }


def pipeline(tmp_path: Path) -> ProjectPipeline:
    return ProjectPipeline(
        documents=documents(),
        runs_dir=tmp_path / "runs",
        db_path=tmp_path / "state.sqlite3",
        tracker_path=tmp_path / "tracker.json",
        top_k=2,
    )


def test_offline_run_persists_contracts_and_pending_proposal(tmp_path: Path):
    app = pipeline(tmp_path)
    result = app.run(case())

    expected = {
        "input_case.json",
        "problem1_part1_synthesis.json",
        "analysis_input.json",
        "next_step_report.json",
        "part3_response.json",
        "maintainer_summary.md",
        "problem2_import.json",
        "manifest.json",
    }
    assert {path.name for path in result.artifact_dir.iterdir()} == expected
    assert result.proposal_status == "pending"
    assert result.import_mode == "created"

    synthesis = json.loads((result.artifact_dir / "problem1_part1_synthesis.json").read_text())
    assert {item["url"] for item in synthesis["evidence_used"]} <= {
        "https://docs.example.test/remote-loading",
        "https://issues.example.test/42",
    }
    manifest = json.loads((result.artifact_dir / "manifest.json").read_text())
    assert manifest["status"] == "waiting_for_human_approval"

    storage = Storage(tmp_path / "state.sqlite3")
    try:
        state = storage.load_case("case-42")
        assert state is not None
        assert [proposal.proposal_id for proposal in state.pending_proposals()] == [result.proposal_id]
    finally:
        storage.close()


def test_exact_retry_reuses_proposal_and_preserves_original_manifest(tmp_path: Path):
    app = pipeline(tmp_path)
    first = app.run(case())
    manifest_before = (first.artifact_dir / "manifest.json").read_bytes()

    second = app.run(case())

    assert second.response_id == first.response_id
    assert second.proposal_id == first.proposal_id
    assert second.import_mode == "reused"
    assert (first.artifact_dir / "manifest.json").read_bytes() == manifest_before

    storage = Storage(tmp_path / "state.sqlite3")
    try:
        state = storage.load_case("case-42")
        assert state is not None
        assert len(state.proposals) == 1
    finally:
        storage.close()


def test_new_revision_waits_for_existing_human_decision(tmp_path: Path):
    app = pipeline(tmp_path)
    first = app.run(case("1.30.0"))

    with pytest.raises(PendingProposalError):
        app.run(case("1.31.0"))

    assert first.artifact_dir.exists()
    assert not list(first.artifact_dir.parent.glob(".*"))
