from __future__ import annotations

from .config import VAR_DIR
from .evidence import EvidenceStore
from .interceptor import TicketInterceptor
from .orchestrator import Orchestrator
from .storage import Storage

DB_PATH = VAR_DIR / "scenario_demo.sqlite3"
TICKET_PATH = VAR_DIR / "scenario_ticket.json"


def build() -> Orchestrator:
    app = Orchestrator(Storage(DB_PATH), TicketInterceptor(TICKET_PATH), EvidenceStore())
    app.memory.reset_cases()
    app.interceptor.reset()
    return app


def section(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def normal_path(app: Orchestrator) -> None:
    section("Scenario 1: normal path, approve then execute")
    app.open_case("30001", title="Stuck on loading screen")
    decision = app.handle_user_message(
        "30001",
        "Streamlit 1.30.0 on Python 3.11 behind nginx on our server, it stays on the loading screen",
    )
    print("decision:", decision.kind, decision.proposal_id)
    approval = app.approve("30001", decision.proposal_id)
    print("approve:", approval)
    result = app.execute("30001", decision.proposal_id, approval["approval_token"])
    print("execute:", result)
    ticket = app.interceptor.get("30001")
    print("ticket comments:", len(ticket["comments"]))


def reject_blocks(app: Orchestrator) -> None:
    section("Scenario 2: maintainer rejects, nothing is executed")
    app.open_case("30002", title="Duplicate widget id")
    decision = app.handle_user_message(
        "30002", "Streamlit 1.35.0 on Windows, running locally, DuplicateWidgetID error"
    )
    print("decision:", decision.kind, decision.proposal_id)
    print("reject:", app.reject("30002", decision.proposal_id))
    approve_after = app.approve("30002", decision.proposal_id)
    print("approve after reject:", approve_after)
    ticket = app.interceptor.get("30002")
    print("ticket comments:", len(ticket["comments"]), "labels:", ticket["labels"])


def repeat_execute(app: Orchestrator) -> None:
    section("Scenario 3: the same execute call repeated does not double the change")
    app.open_case("30003", title="Blank page on Streamlit Cloud")
    decision = app.handle_user_message(
        "30003", "Streamlit 1.35.0 on Python 3.11 on Streamlit Cloud, blank page"
    )
    approval = app.approve("30003", decision.proposal_id)
    token = approval["approval_token"]
    print("first execute:", app.execute("30003", decision.proposal_id, token))
    print("second execute:", app.execute("30003", decision.proposal_id, token))
    ticket = app.interceptor.get("30003")
    print("ticket comments:", len(ticket["comments"]))


def wait_for_approval(app: Orchestrator) -> None:
    section("Scenario 4: while a proposal waits, the agent stops instead of proposing again")
    app.open_case("30004", title="Session state resets")
    first = app.handle_user_message(
        "30004", "Streamlit 1.35.0 on Linux, running locally, my session state resets"
    )
    second = app.handle_user_message("30004", "any update?")
    print("first:", first.kind, first.proposal_id)
    print("second:", second.kind, second.proposal_id)
    print("pending proposals:", len(app.memory.pending_proposals("30004")))


def case_changed(app: Orchestrator) -> None:
    section("Scenario 5: the user corrects a fact before execution")
    app.open_case("30005", title="Crash on server")
    decision = app.handle_user_message(
        "30005", "Streamlit 1.30.0 on Python 3.11 behind nginx, it crashes on our server"
    )
    approval = app.approve("30005", decision.proposal_id)
    app.memory.add_fact("30005", "streamlit_version", "1.35.0", source="user-correction")
    print("corrected version to 1.35.0")
    print("execute:", app.execute("30005", decision.proposal_id, approval["approval_token"]))
    ticket = app.interceptor.get("30005")
    print("ticket comments:", len(ticket["comments"]))


def wrong_token(app: Orchestrator) -> None:
    section("Scenario 6: a token from a different proposal is refused")
    app.open_case("30006", title="Slow reruns")
    decision = app.handle_user_message(
        "30006", "Streamlit 1.35.0 on Linux, running locally, my reruns are slow"
    )
    other = app.memory.create_proposal("30006", "labels", {"labels": ["performance"]}, "manual")
    other_id = other.proposals[-1].proposal_id
    approval = app.approve("30006", decision.proposal_id)
    print("approved:", decision.proposal_id, approval["ok"])
    stale_token = app.memory.approval_token("30006", other_id)
    print("execute with the other proposal's token:",
          app.execute("30006", decision.proposal_id, stale_token))
    print("execute with no token:",
          app.execute("30006", decision.proposal_id, ""))
    ticket = app.interceptor.get("30006")
    print("ticket comments:", len(ticket["comments"]))


def tool_failure(app: Orchestrator) -> None:
    section("Scenario 7: a tool call on a missing case returns a structured error")
    print(app.execute("nope", "PRP_missing", "appr:nope:PRP_missing:0000"))


def two_cases(app: Orchestrator) -> None:
    section("Scenario 8: two cases do not mix their state or their actions")
    app.open_case("30008", title="Case A")
    app.open_case("30009", title="Case B")
    a = app.handle_user_message(
        "30008", "Streamlit 1.30.0 on Python 3.11 behind nginx, loading screen"
    )
    b = app.handle_user_message(
        "30009", "Streamlit 1.35.0 on Windows, running locally, duplicate widget id"
    )
    approval = app.approve("30008", a.proposal_id)
    app.execute("30008", a.proposal_id, approval["approval_token"])
    print("A pending:", app.memory.summary("30008")["pending"])
    print("B pending:", app.memory.summary("30009")["pending"])
    print("B proposal untouched:", b.proposal_id, app.memory.proposal("30009", b.proposal_id).status)
    print("A ticket comments:", len(app.interceptor.get("30008")["comments"]))
    print("B ticket comments:", len(app.interceptor.get("30009")["comments"]))


def main() -> None:
    for scenario in (
        normal_path,
        reject_blocks,
        repeat_execute,
        wait_for_approval,
        case_changed,
        wrong_token,
        tool_failure,
        two_cases,
    ):
        app = build()
        scenario(app)
        app.storage.close()


if __name__ == "__main__":
    main()
