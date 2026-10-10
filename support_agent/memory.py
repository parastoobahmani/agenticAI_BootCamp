from __future__ import annotations

import hashlib
import json
import uuid

from . import tools
from .models import (
    ActionRecord, Approval, CaseState, Check, Fact, Proposal, Source, Unknown, now_iso,
)
from .storage import Storage


class CaseNotFoundError(RuntimeError):
    pass


class MemoryError_(RuntimeError):
    pass


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def compute_action_hash(action: str, payload: dict) -> str:
    canonical = json.dumps(
        {"action": action, "payload": payload},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class CaseMemory:
    """Persistent, per-case memory. It does not authorize side effects."""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def _save(self, state: CaseState, *, changed: bool = True) -> CaseState:
        if changed:
            state.version += 1
        return self.storage.save_case(state)

    def open_case(self, case_id: str, title: str = "", body: str = "") -> CaseState:
        existing = self.storage.load_case(case_id)
        if existing is not None:
            changed = bool((title and title != existing.title) or (body and body != existing.body))
            if title:
                existing.title = title
            if body:
                existing.body = body
            saved = self._save(existing, changed=changed)
            self.storage.log(case_id, "case_opened", {"existing": True})
            return saved
        state = CaseState(case_id=case_id, title=title, body=body)
        saved = self._save(state)
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
        return self._save(state)

    def add_user_turn(self, case_id: str, text: str) -> CaseState:
        state = self.require_case(case_id)
        state.turn += 1
        # Do not persist raw user text in the audit log; it may contain secrets or PII.
        self.storage.log(case_id, "user_turn", {"turn": state.turn})
        return self._save(state)

    def add_fact(self, case_id: str, name: str, value: str, source: str = "user") -> CaseState:
        state = self.require_case(case_id)
        changed = True
        for fact in state.known:
            if fact.name == name:
                changed = fact.value != value or fact.source != source
                fact.value, fact.source, fact.created_at = value, source, now_iso()
                break
        else:
            state.known.append(Fact(name=name, value=value, source=source))
        state.unknown = [row for row in state.unknown if row.name != name]
        if changed:
            self.storage.log(case_id, "fact_added", {"name": name, "source": source})
        return self._save(state, changed=changed)

    def add_unknown(self, case_id: str, name: str, reason: str = "") -> CaseState:
        state = self.require_case(case_id)
        for row in state.unknown:
            if row.name == name:
                if reason and row.reason != reason:
                    row.reason = reason
                    return self._save(state)
                return state
        state.unknown.append(Unknown(name=name, reason=reason))
        self.storage.log(case_id, "unknown_added", {"name": name})
        return self._save(state)

    def add_check(self, case_id: str, name: str, status: str = "pending", result: str = "") -> CaseState:
        state = self.require_case(case_id)
        for row in state.checks:
            if row.name == name:
                row.status, row.result = status, result
                return self._save(state)
        state.checks.append(Check(name=name, status=status, result=result))
        self.storage.log(case_id, "check_recorded", {"name": name, "status": status})
        return self._save(state)

    def add_source(self, case_id: str, kind: str, ref: str, title: str = "",
                   snippet: str = "", score: float = 0.0) -> CaseState:
        state = self.require_case(case_id)
        for row in state.sources:
            if row.kind == kind and row.ref == ref:
                row.title = title or row.title
                row.snippet = snippet or row.snippet
                row.score = score
                return self._save(state)
        state.sources.append(Source(kind=kind, ref=ref, title=title, snippet=snippet, score=score))
        self.storage.log(case_id, "source_added", {"kind": kind, "ref": ref})
        return self._save(state)

    def add_evidence_item(self, case_id: str, item: dict) -> CaseState:
        return self.add_source(case_id, item.get("kind", "document"),
                               item.get("ref", item.get("doc_id", "")),
                               item.get("title", ""), item.get("snippet", ""),
                               float(item.get("score", 0.0)))

    def create_proposal(self, case_id: str, action: str, payload: dict, rationale: str = "") -> CaseState:
        state = self.require_case(case_id)
        if action not in ("comment", "labels", "state"):
            raise MemoryError_(f"unsupported action {action!r}")
        proposal = Proposal(
            proposal_id=new_id("PRP"), action=action, payload=dict(payload), rationale=rationale,
            case_version=state.version + 1,
            action_hash=compute_action_hash(action, payload),
        )
        state.proposals.append(proposal)
        self.storage.log(case_id, "proposal_created", {
            "proposal_id": proposal.proposal_id, "action": action, "case_version": proposal.case_version,
        })
        return self._save(state)

    def set_proposal_decision(self, case_id: str, proposal_id: str, decision: str,
                              decided_by: str = "maintainer") -> CaseState:
        state = self.require_case(case_id)
        proposal = state.proposal(proposal_id)
        if proposal is None:
            raise MemoryError_(f"no proposal {proposal_id!r} in case {case_id!r}")
        if proposal.status != "pending":
            raise MemoryError_(f"proposal {proposal_id!r} is already {proposal.status}")
        if decision == "approve":
            proposal.status = "approved"
        elif decision == "reject":
            proposal.status = "rejected"
        else:
            raise MemoryError_(f"unsupported decision {decision!r}")
        proposal.decision, proposal.decided_by, proposal.decided_at = decision, decided_by, now_iso()
        # Approval/rejection is a decision record, not a new case version.
        self.storage.log(case_id, "proposal_decided", {
            "proposal_id": proposal_id, "decision": decision, "decided_by": decided_by,
        })
        return self.storage.save_case(state)

    def edit_proposal(self, case_id: str, proposal_id: str, action: str, payload: dict,
                      decided_by: str = "maintainer") -> CaseState:
        state = self.require_case(case_id)
        proposal = state.proposal(proposal_id)
        if proposal is None:
            raise MemoryError_(f"no proposal {proposal_id!r} in case {case_id!r}")
        if proposal.status != "pending":
            raise MemoryError_(f"proposal {proposal_id!r} is already {proposal.status}")
        if action not in ("comment", "labels", "state"):
            raise MemoryError_(f"unsupported action {action!r}")
        proposal.action = action
        proposal.payload = dict(payload)
        proposal.action_hash = compute_action_hash(action, payload)
        proposal.case_version = state.version + 1
        proposal.status = "approved"
        proposal.decision = "edit"
        proposal.decided_by = decided_by
        proposal.decided_at = now_iso()
        # The edited proposal itself becomes the exact approved version.
        self.storage.log(case_id, "proposal_edited", {
            "proposal_id": proposal_id, "action": action, "decided_by": decided_by,
        })
        return self._save(state)

    def record_approval(self, case_id: str, approval: Approval) -> CaseState:
        state = self.require_case(case_id)
        state.approvals.append(approval)
        return self.storage.save_case(state)

    def pending_proposals(self, case_id: str) -> list[Proposal]:
        return self.require_case(case_id).pending_proposals()

    def proposal(self, case_id: str, proposal_id: str) -> Proposal | None:
        return self.require_case(case_id).proposal(proposal_id)

    def record_action(self, case_id: str, tool: str, args: dict, ok: bool, result: dict) -> CaseState:
        state = self.require_case(case_id)
        state.actions.append(ActionRecord(action_id=new_id("ACT"), tool=tool,
                                          args=dict(args), ok=ok, result=result))
        self.storage.log(case_id, "action_recorded", {"tool": tool, "ok": ok})
        # A failed attempt is audit history, not a case-content revision. Keeping
        # the version stable allows an explicitly retried approved operation to
        # recover safely through the tracker's durable operation receipt.
        return self._save(state, changed=ok)

    def find_successful_action(self, case_id: str, tool: str, args: dict) -> ActionRecord | None:
        state = self.require_case(case_id)
        for record in state.actions:
            if record.tool == tool and record.args == args and record.ok:
                return record
        return None

    def has_action(self, case_id: str, tool: str, args: dict) -> bool:
        state = self.require_case(case_id)
        return any(r.tool == tool and r.args == args and r.ok for r in state.actions)

    def check_validity(self, case_id: str, proposal_id: str) -> list[str]:
        state = self.require_case(case_id)
        proposal = state.proposal(proposal_id)
        if proposal is None:
            return [f"proposal {proposal_id!r} does not exist"]
        warnings: list[str] = []
        if state.version != proposal.case_version:
            warnings.append("the case changed after this proposal was created")
        if proposal.action_hash != compute_action_hash(proposal.action, proposal.payload):
            warnings.append("proposal action hash does not match its payload")
        known = {fact.name: fact.value for fact in state.known}
        payload = proposal.payload
        if payload.get("streamlit_version") and payload["streamlit_version"] != known.get("streamlit_version"):
            warnings.append("streamlit_version in the proposal no longer matches the case")
        if proposal.action == "state" and payload.get("state") == "closed" and state.status == "closed":
            warnings.append("the case is already closed")
        if proposal.action == "comment" and not str(payload.get("body", "")).strip():
            warnings.append("the comment body is empty")
        return warnings

    def reset_cases(self) -> None:
        self.storage.clear_cases()
        self.storage.clear_events()

    def summary(self, case_id: str) -> dict:
        state = self.require_case(case_id)
        return {
            "case_id": state.case_id, "title": state.title, "status": state.status,
            "version": state.version, "turn": state.turn,
            "known": {fact.name: fact.value for fact in state.known},
            "unknown": [row.name for row in state.unknown],
            "checks": {row.name: row.status for row in state.checks},
            "sources": [{"kind": row.kind, "ref": row.ref} for row in state.sources],
            "pending": [p.proposal_id for p in state.pending_proposals()],
            "proposals": [{"id": p.proposal_id, "status": p.status, "case_version": p.case_version,
                           "action_hash": p.action_hash} for p in state.proposals],
            "actions": [{"tool": r.tool, "ok": r.ok} for r in state.actions],
        }

    def tool_catalog(self) -> list[dict]:
        return tools.describe_tools()
