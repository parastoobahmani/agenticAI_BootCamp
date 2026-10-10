from __future__ import annotations

import hashlib
import hmac
import json

from .memory import CaseMemory, CaseNotFoundError
from .models import Approval, Proposal


class ApprovalError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def action_hash(action: str, payload: dict) -> str:
    canonical = json.dumps(
        {"action": action, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class HumanApprovalManager:
    """Owns the human-in-the-loop authorization boundary.

    Memory stores case state; this class decides whether a proposed observable
    action is authorized to cross into the executor. The token is bound to the
    exact case, case version, proposal and action hash.
    """

    def __init__(self, memory: CaseMemory, secret: str = "support-agent") -> None:
        self.memory = memory
        self.secret = secret

    def prepare(self, case_id: str, proposal_id: str) -> Proposal:
        try:
            proposal = self.memory.proposal(case_id, proposal_id)
        except CaseNotFoundError as exc:
            raise ApprovalError("case_not_found", str(exc)) from exc
        if proposal is None:
            raise ApprovalError("proposal_not_found", f"no proposal {proposal_id!r}")
        if proposal.status != "pending":
            raise ApprovalError("proposal_not_pending", f"proposal {proposal_id!r} is already {proposal.status}")
        return proposal

    def approve(self, case_id: str, proposal_id: str, decided_by: str = "maintainer") -> dict:
        proposal = self.prepare(case_id, proposal_id)
        self._ensure_current(case_id, proposal)
        self.memory.set_proposal_decision(case_id, proposal_id, "approve", decided_by)
        approval = Approval(proposal_id, case_id, "approve", proposal.case_version, proposal.action_hash, decided_by)
        self.memory.record_approval(case_id, approval)
        token = self._token(case_id, proposal_id, approval.approved_case_version, approval.approved_action_hash)
        return self._approval_result(case_id, proposal_id, "approved", token, decided_by)

    def edit(self, case_id: str, proposal_id: str, action: str, payload: dict,
             decided_by: str = "maintainer") -> dict:
        proposal = self.prepare(case_id, proposal_id)
        self._ensure_current(case_id, proposal)
        self.memory.edit_proposal(case_id, proposal_id, action, payload, decided_by)
        proposal = self.memory.proposal(case_id, proposal_id)
        assert proposal is not None
        approval = Approval(proposal_id, case_id, "edit", proposal.case_version, proposal.action_hash, decided_by)
        self.memory.record_approval(case_id, approval)
        token = self._token(case_id, proposal_id, approval.approved_case_version, approval.approved_action_hash)
        return self._approval_result(case_id, proposal_id, "edited", token, decided_by)

    def reject(self, case_id: str, proposal_id: str, decided_by: str = "maintainer") -> dict:
        self.prepare(case_id, proposal_id)
        self.memory.set_proposal_decision(case_id, proposal_id, "reject", decided_by)
        return {"ok": True, "proposal_id": proposal_id, "status": "rejected", "decided_by": decided_by}

    def validate_before_execution(self, case_id: str, proposal_id: str, token: str) -> Proposal:
        try:
            state = self.memory.require_case(case_id)
            proposal = state.proposal(proposal_id)
        except CaseNotFoundError as exc:
            raise ApprovalError("case_not_found", str(exc)) from exc
        if proposal is None:
            raise ApprovalError("proposal_not_found", f"no proposal {proposal_id!r}")
        if proposal.status == "rejected":
            raise ApprovalError("proposal_rejected", f"proposal {proposal_id!r} was rejected")
        if proposal.status != "approved":
            raise ApprovalError("not_approved", f"proposal {proposal_id!r} has not been approved")
        approval = state.approval(proposal_id)
        if approval is None:
            raise ApprovalError("approval_missing", "approved proposal has no approval record")
        expected = self._token(case_id, proposal_id, approval.approved_case_version, approval.approved_action_hash)
        if not hmac.compare_digest(token or "", expected):
            raise ApprovalError("invalid_approval", "approval token is not valid for this case, proposal and exact action")
        if state.version != approval.approved_case_version:
            raise ApprovalError("stale_approval", "case changed after approval; approval is stale")
        if proposal.case_version != approval.approved_case_version:
            raise ApprovalError("stale_approval", "proposal version no longer matches the approved version")
        if proposal.action_hash != approval.approved_action_hash:
            raise ApprovalError("proposal_changed", "proposal action changed after approval")
        warnings = self.memory.check_validity(case_id, proposal_id)
        if warnings:
            raise ApprovalError("proposal_invalidated", "; ".join(warnings))
        return proposal

    def execute(self, case_id: str, proposal_id: str, token: str, executor) -> dict:
        # First bind the retry to the exact approved proposal. Then idempotency
        # can safely short-circuit a repeated request for the same action.
        state = self.memory.require_case(case_id)
        proposal = state.proposal(proposal_id)
        if proposal is None:
            raise ApprovalError("proposal_not_found", f"no proposal {proposal_id!r}")
        approval = state.approval(proposal_id)
        if approval is None:
            raise ApprovalError("approval_missing", "approved proposal has no approval record")
        expected = self._token(case_id, proposal_id, approval.approved_case_version, approval.approved_action_hash)
        if not hmac.compare_digest(token or "", expected):
            raise ApprovalError("invalid_approval", "approval token is not valid for this case, proposal and exact action")
        args = {"case_id": case_id, "proposal_id": proposal_id, "action_hash": proposal.action_hash}
        previous = self.memory.find_successful_action(case_id, "apply_action", args)
        if previous is not None:
            return {"executed": False, "duplicate": True, "proposal_id": proposal_id,
                    "result": previous.result}
        # Validate immediately before the side effect.
        proposal = self.validate_before_execution(case_id, proposal_id, token)
        try:
            result = executor(case_id, proposal)
        except Exception as exc:
            self.memory.record_action(case_id, "apply_action", args, False,
                                      {"error_type": type(exc).__name__})
            raise
        self.memory.record_action(case_id, "apply_action", args, True, result)
        return {"executed": True, "duplicate": False, "proposal_id": proposal_id, "result": result}

    def _ensure_current(self, case_id: str, proposal: Proposal) -> None:
        state = self.memory.require_case(case_id)
        if state.version != proposal.case_version:
            raise ApprovalError("stale_proposal", "case changed after this proposal was created")
        if proposal.action_hash != action_hash(proposal.action, proposal.payload):
            raise ApprovalError("proposal_tampered", "proposal action hash does not match its payload")

    def _token(self, case_id: str, proposal_id: str, version: int, digest: str) -> str:
        message = f"{case_id}|{proposal_id}|{version}|{digest}"
        signature = hmac.new(self.secret.encode(), message.encode(), hashlib.sha256).hexdigest()[:24]
        return f"appr:{case_id}:{proposal_id}:{version}:{signature}"

    @staticmethod
    def _approval_result(case_id: str, proposal_id: str, status: str, token: str, decided_by: str) -> dict:
        return {"ok": True, "case_id": case_id, "proposal_id": proposal_id,
                "status": status, "approval_token": token, "decided_by": decided_by}
