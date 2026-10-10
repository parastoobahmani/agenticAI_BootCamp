from problem1_part1.evidence_synthesis.evidence_core import SourceDocument
from systems import BaselineSystem, IntegratedSystem

CASE = {
    "case_id": "issue-1",
    "title": "Streamlit app stays on the loading screen behind nginx",
    "body": "Works locally, stays on Please wait behind nginx. Streamlit 1.30.0, Python 3.11.",
}
CORPUS = [
    SourceDocument(
        id="doc-remote", source_type="documentation", title="App is not loading when running remotely",
        content="If the app stays on Please wait, the WebSocket connection failed. Proxies must support WebSockets.",
        url_or_path="https://docs.streamlit.io/knowledge-base/deploy/remote-start",
    ),
    SourceDocument(
        id="issue-9", source_type="past_report", title="Stuck behind nginx",
        content="Title: Stuck behind nginx\n\nnginx did not forward the websocket upgrade header.",
        url_or_path="https://github.com/streamlit/streamlit/issues/9", date="2025-01-01T00:00:00Z",
    ),
]


def test_integrated_run_maps_decision_and_checks_stored_state():
    run = IntegratedSystem().run_case(CASE, CORPUS)

    assert run.error is None
    assert run.action in {"answer", "ask_clarification", "escalate"}
    assert run.next_step and run.next_step["decision"] in {"propose_answer", "request_information", "escalate"}
    assert run.operational == {
        "case_persisted": True,
        "one_pending_proposal": True,
        "nothing_executed_without_approval": True,
        "tracker_unchanged": True,
    }
    assert run.usage["api_requests"] == 0


def test_baseline_run_is_recorded():
    run = BaselineSystem().run_case(CASE, CORPUS)
    assert run.error is None
    assert run.action in {"answer", "ask_clarification", "escalate"}
    assert run.next_step is None and run.operational is None


def test_system_failure_is_recorded_not_raised():
    class Broken(IntegratedSystem):
        def run_case(self, case, corpus):
            return super().run_case({**case, "title": ""}, corpus)  # invalid case contract

    run = Broken().run_case(CASE, CORPUS)
    assert run.action is None
    assert run.error
