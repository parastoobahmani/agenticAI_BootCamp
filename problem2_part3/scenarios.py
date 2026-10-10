"""Problem 2 Part 3: ten deterministic, inspectable multi-turn scenarios.

The scenarios exercise the real ``problem2_parts1_2`` memory, approval, execution,
and local tracker boundaries from Parts 1 and 2. Designed follow-up messages and
faults are labelled as test inputs; no API or real GitHub mutation is performed.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
from typing import Callable

from problem2_parts1_2.config import VAR_DIR
from problem2_parts1_2.evidence import EvidenceStore
from problem2_parts1_2.interceptor import TicketInterceptor
from problem2_parts1_2.orchestrator import Orchestrator
from problem2_parts1_2.storage import Storage


class FaultOnceInterceptor(TicketInterceptor):
    """Test double around the real durable-receipt tracker boundary."""

    def __init__(self, path: Path, failure: str) -> None:
        super().__init__(path)
        if failure not in {"before_commit", "after_commit"}:
            raise ValueError("unsupported injected failure")
        self.failure = failure

    def apply(self, number: str, operation_key: str, action: str, payload: dict) -> dict:
        failure, self.failure = self.failure, ""
        if failure == "before_commit":
            raise RuntimeError("injected failure before tracker commit")
        result = super().apply(number, operation_key, action, payload)
        if failure == "after_commit":
            raise RuntimeError("injected lost response after tracker commit")
        return result


def _build(root: Path, interceptor: TicketInterceptor | None = None) -> Orchestrator:
    return Orchestrator(
        Storage(root / "cases.sqlite3"),
        interceptor or TicketInterceptor(root / "ticket.json"),
        EvidenceStore(),
        secret="scenario-secret",
        max_steps=30,
        max_tool_calls=20,
    )


def _propose(app: Orchestrator, case_id: str, title: str = "Loading problem"):
    app.open_case(case_id, title=title)
    decision = app.handle_user_message(
        case_id,
        "Streamlit 1.30.0 on Python 3.11 behind nginx on our server; the app stays on the loading screen.",
    )
    assert decision.kind == "PROPOSE", decision.to_dict()
    return decision


def _approve_execute(app: Orchestrator, case_id: str, proposal_id: str) -> dict:
    approval = app.approve(case_id, proposal_id)
    assert approval["ok"], approval
    result = app.execute(case_id, proposal_id, approval["approval_token"])
    assert result["ok"], result
    return result


def _normal_multiturn(root: Path) -> dict:
    app = _build(root)
    app.open_case("p2-s01", title="Loading problem")
    first = app.handle_user_message("p2-s01", "The app stays on the loading screen.")
    assert first.kind == "ASK"
    second = app.handle_user_message(
        "p2-s01", "It is Streamlit 1.30.0 behind nginx on our server."
    )
    assert second.kind == "PROPOSE"
    result = _approve_execute(app, "p2-s01", second.proposal_id)
    ticket = app.interceptor.get("p2-s01")
    assert len(ticket["comments"]) == 1 and ticket["state"] == "open"
    app.storage.close()
    return {"first_decision": first.kind, "second_decision": second.kind,
            "executed": result["result"]["executed"], "comment_count": 1}


def _user_correction(root: Path) -> dict:
    app = _build(root)
    first = _propose(app, "p2-s02")
    old = app.approve("p2-s02", first.proposal_id)
    assert old["ok"]
    app.memory.add_fact("p2-s02", "streamlit_version", "1.35.0", "user-correction")
    stale = app.execute("p2-s02", first.proposal_id, old["approval_token"])
    assert not stale["ok"] and stale["error"] == "stale_approval"
    revised = app.handle_user_message(
        "p2-s02", "Correction: the failing version is Streamlit 1.35.0 and it is still behind nginx."
    )
    assert revised.kind == "PROPOSE"
    _approve_execute(app, "p2-s02", revised.proposal_id)
    comments = app.interceptor.get("p2-s02")["comments"]
    assert len(comments) == 1 and "1.35.0" in comments[0]["body"]
    app.storage.close()
    return {"old_execution": stale["error"], "new_proposal": revised.proposal_id,
            "comment_count": len(comments)}


def _rejection(root: Path) -> dict:
    app = _build(root)
    decision = _propose(app, "p2-s03")
    rejected = app.reject("p2-s03", decision.proposal_id)
    assert rejected["ok"]
    execution = app.execute("p2-s03", decision.proposal_id, "not-an-approval")
    assert not execution["ok"]
    assert app.interceptor.get("p2-s03")["comments"] == []
    app.storage.close()
    return {"proposal_status": "rejected", "comment_count": 0,
            "execution_error": execution["error"]}


def _maintainer_edit(root: Path) -> dict:
    app = _build(root)
    decision = _propose(app, "p2-s04")
    edited_body = "Maintainer-edited response: please provide the websocket handshake result."
    edited = app.edit("p2-s04", decision.proposal_id, "comment", {"body": edited_body})
    assert edited["ok"]
    result = app.execute("p2-s04", decision.proposal_id, edited["approval_token"])
    assert result["ok"]
    comments = app.interceptor.get("p2-s04")["comments"]
    assert [row["body"] for row in comments] == [edited_body]
    app.storage.close()
    return {"status": edited["status"], "published_exact_edit": True}


def _restart_while_waiting(root: Path) -> dict:
    app = _build(root)
    decision = _propose(app, "p2-s05")
    waiting = app.decide("p2-s05")
    assert waiting.kind == "WAIT_FOR_APPROVAL"
    before = app.memory.summary("p2-s05")
    app.storage.close()
    restarted = _build(root)
    after = restarted.memory.summary("p2-s05")
    assert after["pending"] == before["pending"] == [decision.proposal_id]
    assert restarted.interceptor.get("p2-s05")["comments"] == []
    _approve_execute(restarted, "p2-s05", decision.proposal_id)
    restarted.storage.close()
    return {"restored_proposal": decision.proposal_id, "auto_executed": False,
            "comment_count_after_approval": 1}


def _duplicate_execution(root: Path) -> dict:
    app = _build(root)
    decision = _propose(app, "p2-s06")
    approval = app.approve("p2-s06", decision.proposal_id)
    first = app.execute("p2-s06", decision.proposal_id, approval["approval_token"])
    second = app.execute("p2-s06", decision.proposal_id, approval["approval_token"])
    assert first["ok"] and second["ok"]
    assert first["result"]["executed"] and second["result"]["duplicate"]
    comments = app.interceptor.get("p2-s06")["comments"]
    assert len(comments) == 1
    app.storage.close()
    return {"first_executed": True, "second_duplicate": True, "comment_count": 1}


def _case_change_before_execution(root: Path) -> dict:
    app = _build(root)
    decision = _propose(app, "p2-s07")
    approval = app.approve("p2-s07", decision.proposal_id)
    app.memory.add_fact("p2-s07", "deployment", "local", "user-correction")
    result = app.execute("p2-s07", decision.proposal_id, approval["approval_token"])
    assert not result["ok"] and result["error"] == "stale_approval"
    assert app.interceptor.get("p2-s07")["comments"] == []
    app.storage.close()
    return {"execution_error": result["error"], "comment_count": 0}


def _failure_before_commit(root: Path) -> dict:
    interceptor = FaultOnceInterceptor(root / "ticket.json", "before_commit")
    app = _build(root, interceptor)
    decision = _propose(app, "p2-s08")
    approval = app.approve("p2-s08", decision.proposal_id)
    first = app.execute("p2-s08", decision.proposal_id, approval["approval_token"])
    assert not first["ok"] and first["error"] == "tool_execution_failed"
    assert app.interceptor.get("p2-s08")["comments"] == []
    retry = app.execute("p2-s08", decision.proposal_id, approval["approval_token"])
    assert retry["ok"] and len(app.interceptor.get("p2-s08")["comments"]) == 1
    app.storage.close()
    return {"first_error": first["error"], "retry_executed": True, "comment_count": 1}


def _two_case_isolation(root: Path) -> dict:
    app = _build(root)
    a = _propose(app, "p2-s09-a", "Case A")
    b = _propose(app, "p2-s09-b", "Case B")
    token_a = app.approve("p2-s09-a", a.proposal_id)["approval_token"]
    approval_b = app.approve("p2-s09-b", b.proposal_id)
    assert approval_b["ok"]
    wrong = app.execute("p2-s09-b", b.proposal_id, token_a)
    assert not wrong["ok"] and wrong["error"] == "invalid_approval"
    executed_a = app.execute("p2-s09-a", a.proposal_id, token_a)
    assert executed_a["ok"]
    assert len(app.interceptor.get("p2-s09-a")["comments"]) == 1
    assert app.interceptor.get("p2-s09-b")["comments"] == []
    app.storage.close()
    return {"cross_case_error": wrong["error"], "case_a_comments": 1,
            "case_b_comments": 0}


def _response_lost_after_commit(root: Path) -> dict:
    interceptor = FaultOnceInterceptor(root / "ticket.json", "after_commit")
    app = _build(root, interceptor)
    decision = _propose(app, "p2-s10")
    approval = app.approve("p2-s10", decision.proposal_id)
    first = app.execute("p2-s10", decision.proposal_id, approval["approval_token"])
    assert not first["ok"] and first["error"] == "tool_execution_failed"
    assert len(app.interceptor.get("p2-s10")["comments"]) == 1
    retry = app.execute("p2-s10", decision.proposal_id, approval["approval_token"])
    assert retry["ok"]
    tracker_result = retry["result"]["result"]
    assert tracker_result["tracker_duplicate"] is True
    assert len(app.interceptor.get("p2-s10")["comments"]) == 1
    app.storage.close()
    return {"first_error": first["error"], "receipt_recovered": True,
            "comment_count": 1}


SCENARIOS: tuple[tuple[str, str, str, Callable[[Path], dict]], ...] = (
    ("S01", "normal multi-turn path", "dev", _normal_multiturn),
    ("S02", "user correction invalidates old approval", "dev", _user_correction),
    ("S03", "maintainer rejection", "dev", _rejection),
    ("S04", "maintainer edit binds exact action", "dev", _maintainer_edit),
    ("S05", "restart while waiting for approval", "dev", _restart_while_waiting),
    ("S06", "duplicate execution is idempotent", "test", _duplicate_execution),
    ("S07", "case changes before execution", "test", _case_change_before_execution),
    ("S08", "tool fails before tracker commit", "test", _failure_before_commit),
    ("S09", "two cases remain isolated", "test", _two_case_isolation),
    ("S10", "response is lost after tracker commit", "test", _response_lost_after_commit),
)


def run_all() -> dict:
    results = []
    for scenario_id, name, split, scenario in SCENARIOS:
        with tempfile.TemporaryDirectory(prefix=f"{scenario_id.lower()}-") as directory:
            detail = scenario(Path(directory))
        results.append({"scenario_id": scenario_id, "name": name, "split": split,
                        "passed": True, "designed_followups": True, "detail": detail})
    return {
        "schema_version": "1.0", "mode": "offline_local_tracker",
        "api_calls": 0, "dev_count": 5, "test_count": 5,
        "passed": sum(row["passed"] for row in results),
        "total": len(results), "results": results,
    }


def main(output: str | Path | None = None) -> dict:
    report = run_all()
    path = Path(output) if output else VAR_DIR / "problem2_part3_scenarios.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Scenarios passed: {report['passed']}/{report['total']} "
          f"(dev={report['dev_count']}, test={report['test_count']}, API calls=0)")
    print(f"Report: {path}")
    return report


def cli() -> int:
    """Console-script adapter; keep ``main`` reusable for tests and callers."""
    main()
    return 0


if __name__ == "__main__":
    main()
