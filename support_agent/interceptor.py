from __future__ import annotations

import json
from pathlib import Path

from .config import ALLOWED_TICKET_STATES
from .models import now_iso


class InterceptorError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class TicketInterceptor:
    """A local, resettable stand-in for the GitHub ticket.

    Nothing here touches a real repository. It just keeps the visible ticket
    fields in a JSON file so a run can be inspected and reset.
    """

    def __init__(self, path, seed: str = "streamlit/streamlit") -> None:
        self.path = Path(path)
        self.seed = seed
        if not self.path.exists():
            self._write({"seed": seed, "updated_at": now_iso(), "tickets": {}})

    def _read(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def ensure(self, number: str, title: str = "", state: str = "open") -> dict:
        data = self._read()
        tickets = data.setdefault("tickets", {})
        if number not in tickets:
            tickets[number] = {
                "number": number,
                "title": title,
                "state": state,
                "labels": [],
                "comments": [],
                "updated_at": now_iso(),
            }
            self._write(data)
        return tickets[number]

    def get(self, number: str) -> dict:
        data = self._read()
        if number not in data.get("tickets", {}):
            raise InterceptorError("ticket_not_found", f"no intercepted ticket {number!r}")
        return data["tickets"][number]

    def snapshot(self) -> dict:
        return self._read()

    def add_comment(self, number: str, body: str, author: str = "support-agent") -> dict:
        data = self._read()
        ticket = data["tickets"][number]
        comment = {"author": author, "body": body, "created_at": now_iso()}
        ticket["comments"].append(comment)
        ticket["updated_at"] = now_iso()
        self._write(data)
        return comment

    def add_labels(self, number: str, labels: list[str]) -> list[str]:
        data = self._read()
        ticket = data["tickets"][number]
        for label in labels:
            if label not in ticket["labels"]:
                ticket["labels"].append(label)
        ticket["updated_at"] = now_iso()
        self._write(data)
        return list(ticket["labels"])

    def set_state(self, number: str, state: str) -> str:
        if state not in ALLOWED_TICKET_STATES:
            raise InterceptorError("bad_state", f"state must be one of {ALLOWED_TICKET_STATES}")
        data = self._read()
        ticket = data["tickets"][number]
        ticket["state"] = state
        ticket["updated_at"] = now_iso()
        self._write(data)
        return state

    def reset(self) -> None:
        self._write({"seed": self.seed, "updated_at": now_iso(), "tickets": {}})
