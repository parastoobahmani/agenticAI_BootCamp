from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Fact:
    name: str
    value: str
    source: str = "user"
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Unknown:
    name: str
    reason: str = ""
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Check:
    name: str
    status: str = "pending"
    result: str = ""
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Source:
    kind: str
    ref: str
    title: str = ""
    snippet: str = ""
    score: float = 0.0
    retrieved_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Proposal:
    proposal_id: str
    action: str
    payload: dict
    rationale: str = ""
    status: str = "pending"
    decided_by: str = ""
    created_at: str = field(default_factory=now_iso)
    decided_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ActionRecord:
    action_id: str
    tool: str
    args: dict
    ok: bool
    result: dict
    at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CaseState:
    case_id: str
    title: str = ""
    body: str = ""
    status: str = "open"
    known: list[Fact] = field(default_factory=list)
    unknown: list[Unknown] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    proposals: list[Proposal] = field(default_factory=list)
    actions: list[ActionRecord] = field(default_factory=list)
    turn: int = 0
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CaseState":
        return cls(
            case_id=data["case_id"],
            title=data.get("title", ""),
            body=data.get("body", ""),
            status=data.get("status", "open"),
            known=[Fact(**row) for row in data.get("known", [])],
            unknown=[Unknown(**row) for row in data.get("unknown", [])],
            checks=[Check(**row) for row in data.get("checks", [])],
            sources=[Source(**row) for row in data.get("sources", [])],
            proposals=[Proposal(**row) for row in data.get("proposals", [])],
            actions=[ActionRecord(**row) for row in data.get("actions", [])],
            turn=data.get("turn", 0),
            created_at=data.get("created_at", now_iso()),
            updated_at=data.get("updated_at", now_iso()),
        )

    def pending_proposals(self) -> list[Proposal]:
        return [proposal for proposal in self.proposals if proposal.status == "pending"]

    def proposal(self, proposal_id: str) -> Proposal | None:
        for proposal in self.proposals:
            if proposal.proposal_id == proposal_id:
                return proposal
        return None
