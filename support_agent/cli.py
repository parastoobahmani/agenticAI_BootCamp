from __future__ import annotations

import argparse
import json
import sys

from .config import DEFAULT_DB_PATH, SEED_CASES_PATH, VAR_DIR
from .evidence import EvidenceStore
from .interceptor import TicketInterceptor
from .orchestrator import Orchestrator
from .storage import Storage


def build() -> Orchestrator:
    storage = Storage(DEFAULT_DB_PATH)
    interceptor = TicketInterceptor(VAR_DIR / "interceptor.json")
    return Orchestrator(storage, interceptor, evidence=EvidenceStore())


def show(payload: dict) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Support case assistant - state, memory and tools")
    sub = parser.add_subparsers(dest="command", required=True)

    open_cmd = sub.add_parser("open")
    open_cmd.add_argument("case_id")
    open_cmd.add_argument("--title", default="")
    open_cmd.add_argument("--body", default="")

    message_cmd = sub.add_parser("message")
    message_cmd.add_argument("case_id")
    message_cmd.add_argument("text")

    sub.add_parser("cases")

    show_cmd = sub.add_parser("show")
    show_cmd.add_argument("case_id")

    approve_cmd = sub.add_parser("approve")
    approve_cmd.add_argument("case_id")
    approve_cmd.add_argument("proposal_id")

    reject_cmd = sub.add_parser("reject")
    reject_cmd.add_argument("case_id")
    reject_cmd.add_argument("proposal_id")

    execute_cmd = sub.add_parser("execute")
    execute_cmd.add_argument("case_id")
    execute_cmd.add_argument("proposal_id")
    execute_cmd.add_argument("--token", required=True)

    events_cmd = sub.add_parser("events")
    events_cmd.add_argument("--case_id", default=None)
    events_cmd.add_argument("--limit", type=int, default=20)

    sub.add_parser("tools")
    sub.add_parser("ticket")
    sub.add_parser("seed")
    sub.add_parser("scenarios")

    reset_cmd = sub.add_parser("reset")
    reset_cmd.add_argument("--ticket", action="store_true")

    args = parser.parse_args(argv)
    app = build()

    if args.command == "open":
        state = app.open_case(args.case_id, title=args.title, body=args.body)
        show({"opened": state.case_id, "status": state.status})
    elif args.command == "message":
        decision = app.handle_user_message(args.case_id, args.text)
        show(decision.to_dict())
    elif args.command == "cases":
        show({"cases": app.memory.list_cases()})
    elif args.command == "show":
        show(app.memory.summary(args.case_id))
    elif args.command == "approve":
        show(app.approve(args.case_id, args.proposal_id))
    elif args.command == "reject":
        show(app.reject(args.case_id, args.proposal_id))
    elif args.command == "execute":
        show(app.execute(args.case_id, args.proposal_id, args.token))
    elif args.command == "events":
        show({"events": app.storage.events(args.case_id, args.limit)})
    elif args.command == "tools":
        show({"tools": app.memory.tool_catalog()})
    elif args.command == "ticket":
        show(app.interceptor.snapshot())
    elif args.command == "seed":
        rows = json.loads(SEED_CASES_PATH.read_text(encoding="utf-8"))
        proposals = []
        for row in rows:
            app.open_case(row["case_id"], title=row["title"], body=row["body"])
            app.handle_user_message(row["case_id"], row["body"])
            pending = app.memory.pending_proposals(row["case_id"])
            proposals.append({"case_id": row["case_id"],
                              "proposal_id": pending[0].proposal_id if pending else ""})
        show({"seeded": [row["case_id"] for row in rows], "proposals": proposals})
    elif args.command == "scenarios":
        from . import scenarios
        scenarios.main()
    elif args.command == "reset":
        app.memory.reset_cases()
        if args.ticket:
            app.interceptor.reset()
        show({"reset": True, "ticket_reset": args.ticket})

    app.storage.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
