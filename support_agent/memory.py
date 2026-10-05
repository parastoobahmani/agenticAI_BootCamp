from __future__ import annotations

import hashlib
import uuid

from . import tools
from .models import (
    ActionRecord,
    CaseState,
    Check,
    Fact,
    Proposal,
    Source,
    Unknown,
    now_iso,
)
from .storage import Storage


class CaseNotFoundError(RuntimeError):
    pass


class MemoryError_(RuntimeError):
    pass


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class CaseMemory:

    def __init__(self, storage: Storage, secret: str = "support-agent") -> None:
        self.storage = storage
        self.secret = secret

    def open_case(self, case_id: str, title: str = "", body: str = "") -> CaseState:
        existing = self.storage.load_case(case_id)
        if existing is not None:
            if title:
                existing.title = title
            if body:
                existing.body = body
            saved = self.storage.save_case(existing)
            self.storage.log(case_id, "case_opened", {"existing": True})
            return saved
        state = CaseState(case_id=case_id, title=title, body=body)
        saved = self.storage.save_case(state)
        self.storage.log(case_id, "case_opened", {"existing": False})
        return saved

    def require_case(self, case_id: str) -> CaseState:
        state = self.storage.load_case(case_id)
        if state is None:
            raise CaseNotFoundError(f"no case with id {case_id!r}")
        return state

    def get_case(self, case_id: str) -> CaseState | None:
        return self.storage.load_case(case_id)

    def list_cases(self) -> list[str]:
        return self.storage.list_cases()

    def save(self, state: CaseState) -> CaseState:
        return self.storage.save_case(state)

    # -- user turn -----------------------------------------------------------
    def add_user_turn(self, case_id: str, text: str) -> CaseState:
        state = self.require_case(case_id)
        state.turn += 1
        self.storage.log(case_id, "user_turn", {"turn": state.turn, "text": text})
        return self.storage.save_case(state)

    # -- evidence state ------------------------------------------------------
    def add_fact(self, case_id: str, name: str, value: str, source: str = "user") -> CaseState:
        state = self.require_case(case_id)
        for fact in state.known:
            if fact.name == name:
                fact.value = value
                fact.source = source
                fact.created_at = now_iso()
                break
        else:
            state.known.append(Fact(name=name, value=value, source=source))
        state.unknown = [row for row in state.unknown if row.name != name]
        self.storage.log(case_id, "fact_added", {"name": name, "value": value, "source": source})
        return self.storage.save_case(state)

    def add_unknown(self, case_id: str, name: str, reason: str = "") -> CaseState:
        state = self.require_case(case_id)
        for row in state.unknown:
            if row.name == name:
                row.reason = reason or row.reason
                return self.storage.save_case(state)
        state.unknown.append(Unknown(name=name, reason=reason))
        self.storage.log(case_id, "unknown_added", {"name": name, "reason": reason})
        return self.storage.save_case(state)

    def add_check(self, case_id: str, name: str, status: str = "pending", result: str = "") -> CaseState:
        state = self.require_case(case_id)
        for row in state.checks:
            if row.name == name:
                row.status = status
                row.result = result
                break
        else:
            state.checks.append(Check(name=name, status=status, result=result))
        self.storage.log(case_id, "check_recorded", {"name": name, "status": status})
        return self.storage.save_case(state)

    def add_source(self, case_id: str, kind: str, ref: str, title: str = "",
                   snippet: str = "", score: float = 0.0) -> CaseState:
        state = self.require_case(case_id)
        for row in state.sources:
            if row.kind == kind and row.ref == ref:
                row.title = title or row.title
                row.snippet = snippet or row.snippet
                row.score = score
                return self.storage.save_case(state)
        state.sources.append(Source(kind=kind, ref=ref, title=title, snippet=snippet, score=score))
        self.storage.log(case_id, "source_added", {"kind": kind, "ref": ref})
        return self.storage.save_case(state)

    def add_evidence_item(self, case_id: str, item: dict) -> CaseState:
        return self.add_source(
            case_id,
            kind=item.get("kind", "document"),
            ref=item.get("ref", item.get("doc_id", "")),
            title=item.get("title", ""),
            snippet=item.get("snippet", ""),
            score=float(item.get("score", 0.0)),
        )

    # -- proposals -----------------------------------------------------------
    def create_proposal(self, case_id: str, action: str, payload: dict,
                        rationale: str = "") -> CaseState:
        state = self.require_case(case_id)
        if action not in ("comment", "labels", "state"):
            raise MemoryError_(f"unsupported action {action!r}")
        proposal = Proposal(
            proposal_id=new_id("PRP"),
            action=action,
            payload=payload,
            rationale=rationale,
        )
        state.proposals.append(proposal)
        self.storage.log(case_id, "proposal_created",
                         {"proposal_id": proposal.proposal_id, "action": action, "payload": payload})
        return self.storage.save_case(state)

    def decide_proposal(self, case_id: str, proposal_id: str, status: str,
                        decided_by: str = "maintainer") -> CaseState:
        state = self.require_case(case_id)
        proposal = state.proposal(proposal_id)
        if proposal is None:
            raise MemoryError_(f"no proposal {proposal_id!r} in case {case_id!r}")
        if proposal.status not in ("pending", "approved"):
            raise MemoryError_(f"proposal {proposal_id!r} is already {proposal.status}")
        proposal.status = status
        proposal.decided_by = decided_by
        proposal.decided_at = now_iso()
        self.storage.log(case_id, "proposal_decided",
                         {"proposal_id": proposal_id, "status": status, "decided_by": decided_by})
        return self.storage.save_case(state)

    def pending_proposals(self, case_id: str) -> list[Proposal]:
        return self.require_case(case_id).pending_proposals()

    def proposal(self, case_id: str, proposal_id: str) -> Proposal | None:
        return self.require_case(case_id).proposal(proposal_id)

    # -- approval tokens -----------------------------------------------------
    def approval_token(self, case_id: str, proposal_id: str) -> str:
        signature = hashlib.sha256(
            f"{self.secret}|{case_id}|{proposal_id}".encode("utf-8")
        ).hexdigest()[:16]
        return f"appr:{case_id}:{proposal_id}:{signature}"

    def is_valid_token(self, case_id: str, proposal_id: str, token: str) -> bool:
        return token == self.approval_token(case_id, proposal_id)

    def validate_approval(self, case_id: str, proposal_id: str, token: str) -> Proposal:
        state = self.require_case(case_id)
        proposal = state.proposal(proposal_id)
        if proposal is None:
            raise MemoryError_(f"no proposal {proposal_id!r} in case {case_id!r}")
        if not self.is_valid_token(case_id, proposal_id, token):
            raise MemoryError_("approval token is not valid for this case and proposal")
        if proposal.status == "rejected":
            raise MemoryError_(f"proposal {proposal_id!r} was rejected")
        if proposal.status == "pending":
            raise MemoryError_(f"proposal {proposal_id!r} has not been approved")
        return proposal

    # -- executed actions ----------------------------------------------------
    def record_action(self, case_id: str, tool: str, args: dict, ok: bool,
                      result: dict) -> CaseState:
        state = self.require_case(case_id)
        state.actions.append(
            ActionRecord(action_id=new_id("ACT"), tool=tool, args=args, ok=ok, result=result)
        )
        self.storage.log(case_id, "action_recorded", {"tool": tool, "ok": ok, "result": result})
        return self.storage.save_case(state)

    def has_action(self, case_id: str, tool: str, args: dict) -> bool:
        state = self.require_case(case_id)
        for record in state.actions:
            if record.tool == tool and record.args == args and record.ok:
                return True
        return False

    # -- validity of a pending or approved proposal --------------------------
    def check_validity(self, case_id: str, proposal_id: str) -> list[str]:
        state = self.require_case(case_id)
        proposal = state.proposal(proposal_id)
        if proposal is None:
            return [f"proposal {proposal_id!r} does not exist"]
        warnings = []
        known = {fact.name: fact.value for fact in state.known}
        payload = proposal.payload
        if payload.get("streamlit_version") and payload["streamlit_version"] != known.get("streamlit_version"):
            warnings.append("streamlit_version in the proposal no longer matches the case")
        if proposal.action == "state" and payload.get("state") == "closed" and state.status == "closed":
            warnings.append("the case is already closed")
        if proposal.action == "comment" and not str(payload.get("body", "")).strip():
            warnings.append("the comment body is empty")
        if state.actions and proposal.created_at < state.actions[-1].at:
            warnings.append("the case changed after this proposal was created")
        return warnings

    # -- lifecycle -----------------------------------------------------------
    def reset_cases(self) -> None:
        self.storage.clear_cases()
        self.storage.clear_events()

    def summary(self, case_id: str) -> dict:
        state = self.require_case(case_id)
        return {
            "case_id": state.case_id,
            "title": state.title,
            "status": state.status,
            "turn": state.turn,
            "known": {fact.name: fact.value for fact in state.known},
            "unknown": [row.name for row in state.unknown],
            "checks": {row.name: row.status for row in state.checks},
            "sources": [{"kind": row.kind, "ref": row.ref} for row in state.sources],
            "pending": [proposal.proposal_id for proposal in state.pending_proposals()],
            "actions": [
                {"tool": record.tool, "ok": record.ok} for record in state.actions
            ],
        }

    def tool_catalog(self) -> list[dict]:
        return tools.describe_tools()
