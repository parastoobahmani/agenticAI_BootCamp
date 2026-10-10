from __future__ import annotations

import json
from pathlib import Path
import tempfile

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
            self._write({"seed": seed, "updated_at": now_iso(), "tickets": {}, "receipts": {}})

    def _read(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=self.path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            json.dump(data, handle, indent=2, ensure_ascii=False)
        try:
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)

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

    def apply(self, number: str, operation_key: str, action: str, payload: dict) -> dict:
        """Apply one visible mutation and persist its receipt in the same file write.

        A retry with the same operation key returns the durable receipt. This is
        the local tracker's idempotency boundary when a response is lost after
        the mutation has committed.
        """
        data = self._read()
        ticket = data.get("tickets", {}).get(number)
        if ticket is None:
            raise InterceptorError("ticket_not_found", f"no intercepted ticket {number!r}")
        receipts = data.setdefault("receipts", {})
        if operation_key in receipts:
            return {**receipts[operation_key], "tracker_duplicate": True}
        if action == "comment":
            body = payload.get("body", "")
            if not isinstance(body, str) or not body.strip():
                raise InterceptorError("bad_comment", "comment body must be non-empty")
            comment = {"author": "support-agent", "body": body, "created_at": now_iso()}
            ticket["comments"].append(comment)
            result = {"action": "comment", "comment": comment}
        elif action == "labels":
            labels = payload.get("labels", [])
            if not isinstance(labels, list) or not all(isinstance(label, str) for label in labels):
                raise InterceptorError("bad_labels", "labels must be a list of strings")
            for label in labels:
                if label not in ticket["labels"]:
                    ticket["labels"].append(label)
            result = {"action": "labels", "labels": list(ticket["labels"])}
        elif action == "state":
            state = payload.get("state", "open")
            if state not in ALLOWED_TICKET_STATES:
                raise InterceptorError("bad_state", f"state must be one of {ALLOWED_TICKET_STATES}")
            ticket["state"] = state
            result = {"action": "state", "state": state}
        else:
            raise InterceptorError("unsupported_action", f"cannot execute {action!r}")
        ticket["updated_at"] = now_iso()
        receipt = {**result, "operation_key": operation_key}
        receipts[operation_key] = receipt
        data["updated_at"] = now_iso()
        self._write(data)
        return {**receipt, "tracker_duplicate": False}

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
        self._write({"seed": self.seed, "updated_at": now_iso(), "tickets": {}, "receipts": {}})
