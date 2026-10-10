from __future__ import annotations

import json
from pathlib import Path
import threading
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pytest

from problem1_part1.evidence_synthesis.evidence_core import SourceDocument
from problem2_parts1_2.storage import Storage
from project_app import PendingProposalError, ProjectPipeline
from project_app.web_server import make_server
from project_app.web_service import ProjectWebService
from project_app.web_store import WebStore


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


def web_service(tmp_path: Path) -> ProjectWebService:
    return ProjectWebService(pipeline(tmp_path), WebStore(tmp_path / "web.sqlite3"))


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


def test_user_follow_up_supersedes_pending_draft_and_resumes(tmp_path: Path):
    service = web_service(tmp_path)
    first = service.submit_case("case-42", "App stays on loading", "Streamlit 1.30.0 on Linux behind nginx.")

    second = service.add_user_message("case-42", "The browser console reports a WebSocket 403 error.")

    detail = service.case_detail("case-42")
    proposals = detail["state"]["proposals"]
    assert proposals[0]["proposal_id"] == first.proposal_id
    assert proposals[0]["status"] == "rejected"
    assert proposals[0]["decided_by"] == "system:user_update"
    assert proposals[-1]["proposal_id"] == second.proposal_id
    assert proposals[-1]["status"] == "pending"
    assert detail["case"]["comments"][-1]["body"].startswith("The browser console")
    assert first.artifact_dir != second.artifact_dir


def test_maintainer_can_edit_approve_publish_and_later_resume(tmp_path: Path):
    service = web_service(tmp_path)
    first = service.submit_case("case-42", "App stays on loading", "Streamlit 1.30.0 on Linux behind nginx.")

    execution = service.approve_and_publish(
        "case-42", first.proposal_id, "Please send the browser WebSocket status code."
    )

    assert execution["ok"] is True
    detail = service.case_detail("case-42")
    assert detail["ticket"]["comments"][-1]["body"] == "Please send the browser WebSocket status code."
    assert detail["state"]["proposals"][0]["status"] == "approved"

    resumed = service.add_user_message("case-42", "The WebSocket request returns 403.")
    assert resumed.proposal_status == "pending"
    assert service.case_detail("case-42")["pending_count"] == 1


def test_rejected_case_resumes_when_user_adds_information(tmp_path: Path):
    service = web_service(tmp_path)
    first = service.submit_case("case-42", "App stays on loading", "Streamlit 1.30.0 on Linux behind nginx.")
    service.reject("case-42", first.proposal_id, "Ask for the browser status first.")

    resumed = service.add_user_message("case-42", "The browser status is HTTP 403.")

    assert resumed.proposal_status == "pending"
    events = service.case_detail("case-42")["events"]
    assert any(event["kind"] == "proposal_rejected" for event in events)


def test_web_server_exposes_health_and_role_pages(tmp_path: Path):
    try:
        server = make_server(web_service(tmp_path), "127.0.0.1", 0)
    except PermissionError:
        pytest.skip("the test sandbox does not permit binding a localhost socket")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        with urlopen(base + "/healthz") as response:
            assert json.load(response) == {"ok": True}
        with urlopen(base + "/user") as response:
            assert b"User portal" in response.read()
        with urlopen(base + "/maintainer") as response:
            assert b"Maintainer console" in response.read()
        form = urlencode({
            "csrf": server.RequestHandlerClass.csrf_token,
            "case_id": "web-case-1",
            "title": "App stays on loading",
            "body": "Streamlit 1.30.0 on Linux behind nginx.",
        }).encode()
        request = Request(
            base + "/user/cases",
            data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urlopen(request) as response:
            page = response.read()
            assert b"App stays on loading" in page
            assert b"Maintainer review in progress" in page
        with urlopen(base + "/maintainer/cases/web-case-1") as response:
            assert b"Approve and publish" in response.read()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
