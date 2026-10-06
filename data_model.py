from datetime import datetime
from enum import Enum
from hashlib import sha256
from typing import Optional

from pydantic import BaseModel, Field

import hashlib
import json

class ApprovalDecision(str, Enum):
    APPROVE = "approve"
    EDIT = "edit"
    REJECT = "reject"


class ProposalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    EDITED = "edited"
    REJECTED = "rejected"
    INVALIDATED = "invalidated"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


class CaseAction(BaseModel):
    action_type: str
    payload: dict


class Proposal(BaseModel):
    proposal_id: str
    case_id: str

    # Version of the case when proposal was generated
    case_version: int

    action: CaseAction

    # Human-readable representation shown to maintainer
    display_text: str

    # Hash of the exact proposed action
    proposal_hash: str

    status: ProposalStatus = ProposalStatus.PENDING

    created_at: datetime


class Approval(BaseModel):
    proposal_id: str
    case_id: str

    decision: ApprovalDecision

    # If maintainer edits the proposal
    edited_action: Optional[CaseAction] = None

    approved_case_version: int

    approved_proposal_hash: str

    decided_at: datetime


class HumanApprovalManager:

    def __init__(self, store, executor):
        self.store = store
        self.executor = executor



def hash_action(action: CaseAction) -> str:
    canonical = json.dumps(
        action.model_dump(),
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


def create_proposal(
    self,
    case_id: str,
    case_version: int,
    action: CaseAction,
    display_text: str,
):
    proposal_id = str(uuid.uuid4())

    proposal_hash = hash_action(action)

    proposal = Proposal(
        proposal_id=proposal_id,
        case_id=case_id,
        case_version=case_version,
        action=action,
        display_text=display_text,
        proposal_hash=proposal_hash,
        created_at=datetime.utcnow(),
    )

    self.store.save_proposal(proposal)

    return proposal

def decide(
    self,
    proposal_id: str,
    decision: ApprovalDecision,
    *,
    edited_action: CaseAction | None = None,
):
    proposal = self.store.get_proposal(proposal_id)

    if proposal is None:
        raise ValueError("Unknown proposal")

    if proposal.status != ProposalStatus.PENDING:
        raise ValueError("Proposal is no longer pending")

    action = edited_action or proposal.action

    approval = Approval(
        proposal_id=proposal.proposal_id,
        case_id=proposal.case_id,
        decision=decision,
        edited_action=edited_action,
        approved_case_version=proposal.case_version,
        approved_proposal_hash=hash_action(action),
        decided_at=datetime.utcnow(),
    )

    if decision == ApprovalDecision.REJECT:
        proposal.status = ProposalStatus.REJECTED

    elif decision == ApprovalDecision.APPROVE:
        proposal.status = ProposalStatus.APPROVED

    elif decision == ApprovalDecision.EDIT:
        proposal.status = ProposalStatus.EDITED

    self.store.save_approval(approval)
    self.store.save_proposal(proposal)

    return approval

def validate_before_execution(self, proposal, approval):

    current_case = self.store.get_case(proposal.case_id)

    # 1. Case must still exist
    if current_case is None:
        raise ExecutionBlocked("CASE_NOT_FOUND")

    # 2. Case version must match
    if current_case.version != approval.approved_case_version:
        proposal.status = ProposalStatus.INVALIDATED
        self.store.save_proposal(proposal)

        raise ExecutionBlocked("STALE_APPROVAL")

    # 3. The action must be exactly what was approved
    action = approval.edited_action or proposal.action

    if hash_action(action) != approval.approved_proposal_hash:
        proposal.status = ProposalStatus.INVALIDATED
        self.store.save_proposal(proposal)

        raise ExecutionBlocked("PROPOSAL_CHANGED")

    # 4. Approval must explicitly allow execution
    if approval.decision == ApprovalDecision.REJECT:
        raise ExecutionBlocked("REJECTED")

    return action
    
