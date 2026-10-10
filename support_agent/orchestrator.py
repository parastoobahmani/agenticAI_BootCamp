from __future__ import annotations

import re
from dataclasses import dataclass, field

from .evidence import EvidenceStore
from .approval import ApprovalError, HumanApprovalManager
from .interceptor import InterceptorError, TicketInterceptor
from .memory import CaseMemory, CaseNotFoundError, MemoryError_
from .models import CaseState
from .storage import Storage
from .tools import ToolError, validate_args

VERSION_PATTERNS = {
    "streamlit_version": r"streamlit[\s=<>]*([0-9]+\.[0-9]+(?:\.[0-9]+)?)",
    "python_version": r"python[\s=<>]*([0-9]+\.[0-9]+(?:\.[0-9]+)?)",
}

OS_HINTS = {
    "windows": ("windows", "win32", "win64"),
    "linux": ("linux", "ubuntu", "debian", "centos", "wsl"),
    "macos": ("macos", "mac os", "darwin", "osx"),
}

DEPLOYMENT_HINTS = {
    "local": ("locally", "local machine", "my laptop", "my computer", "localhost", "on my system"),
    "streamlit cloud": ("streamlit cloud", "share.streamlit.io"),
    "docker": ("docker", "container", "image"),
    "kubernetes": ("kubernetes", "k8s", "helm"),
    "reverse proxy": ("nginx", "apache", "traefik", "reverse proxy"),
}

REQUIRED_FACTS = ("streamlit_version", "python_version", "os", "deployment")
ASK_FACTS = ("streamlit_version", "deployment")


class BudgetExceeded(RuntimeError):
    def __init__(self, limit: str, ceiling: int) -> None:
        super().__init__(f"{limit} limit of {ceiling} exceeded")
        self.limit = limit
        self.ceiling = ceiling


@dataclass
class Decision:
    kind: str
    message: str
    proposal_id: str = ""
    sources: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "message": self.message,
            "proposal_id": self.proposal_id,
            "sources": self.sources,
        }


class Orchestrator:
    def __init__(self, storage: Storage, interceptor: TicketInterceptor,
                 evidence: EvidenceStore | None = None, secret: str = "support-agent",
                 max_steps: int = 12, max_tool_calls: int = 8) -> None:
        self.storage = storage
        self.interceptor = interceptor
        self.evidence = evidence or EvidenceStore()
        self.memory = CaseMemory(storage)
        self.approval = HumanApprovalManager(self.memory, secret=secret)
        self.max_steps = max_steps
        self.max_tool_calls = max_tool_calls
        self.tool_calls = 0
        self.steps = 0

    # -- step and tool accounting -------------------------------------------
    def _step(self, action: str) -> None:
        self.steps += 1
        if self.steps > self.max_steps:
            raise BudgetExceeded("step", self.max_steps)
        self.storage.log(None, "step", {"index": self.steps, "action": action})

    def _count_tool(self, name: str) -> None:
        self.tool_calls += 1
        if self.tool_calls > self.max_tool_calls:
            raise BudgetExceeded("tool_call", self.max_tool_calls)
        self.storage.log(None, "tool_counted", {"tool": name, "total": self.tool_calls})

    def budget(self) -> dict:
        return {
            "steps": self.steps,
            "max_steps": self.max_steps,
            "tool_calls": self.tool_calls,
            "max_tool_calls": self.max_tool_calls,
        }

    # -- tool registry -------------------------------------------------------
    def call_tool(self, name: str, args: dict) -> dict:
        self._count_tool(name)
        try:
            validated = validate_args(name, args)
        except ToolError as error:
            return {"ok": False, "error": error.code, "message": str(error)}
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return {"ok": False, "error": "unknown_tool", "message": f"no tool named {name!r}"}
        try:
            result = handler(**validated)
        except (InterceptorError, ToolError, MemoryError_, CaseNotFoundError) as error:
            code = getattr(error, "code", "tool_error")
            self.storage.log(args.get("case_id"), "tool_error", {"tool": name, "error": code})
            return {"ok": False, "error": code, "message": str(error)}
        except Exception as error:
            # Tool boundaries return a stable category and keep exception text
            # out of user-visible output and audit logs.
            self.storage.log(args.get("case_id"), "tool_error", {
                "tool": name, "error": "tool_execution_failed",
                "error_type": type(error).__name__,
            })
            return {"ok": False, "error": "tool_execution_failed",
                    "message": "the tool failed before returning a result"}
        return {"ok": True, "result": result}

    def _tool_read_ticket(self, case_id: str) -> dict:
        state = self.memory.require_case(case_id)
        return self.memory.summary(case_id) | {"title": state.title, "body": state.body}

    def _tool_search_evidence(self, query: str, top_k: int = 5) -> dict:
        results = self.evidence.search(query, top_k=top_k)
        return {"query": query, "count": len(results), "results": results}

    def _tool_propose_action(self, case_id: str, action: str, payload: dict,
                             rationale: str = "") -> dict:
        state = self.memory.create_proposal(case_id, action, payload, rationale)
        proposal = state.proposals[-1]
        return {"proposal_id": proposal.proposal_id, "status": proposal.status}

    def _tool_apply_action(self, case_id: str, proposal_id: str, approval_token: str) -> dict:
        try:
            return self.approval.execute(case_id, proposal_id, approval_token, self._dispatch_action)
        except ApprovalError as error:
            raise ToolError(error.code, str(error)) from error

    def _dispatch_action(self, case_id: str, proposal) -> dict:
        operation_key = f"{case_id}:{proposal.proposal_id}:{proposal.action_hash}"
        return self.interceptor.apply(
            case_id, operation_key, proposal.action, proposal.payload
        )

    # -- case lifecycle ------------------------------------------------------
    def open_case(self, case_id: str, title: str = "", body: str = "") -> CaseState:
        state = self.memory.open_case(case_id, title=title, body=body)
        self.interceptor.ensure(case_id, title=title)
        self.storage.meta_set(f"last_case:{case_id}", "opened")
        return state

    def handle_user_message(self, case_id: str, text: str) -> Decision:
        self._step("handle_user_message")
        state = self.memory.add_user_turn(case_id, text)
        self._extract_facts(case_id, text)
        self._search_evidence(case_id, text)
        return self.decide(case_id)

    def _extract_facts(self, case_id: str, text: str) -> None:
        known = {fact.name: fact.value for fact in self.memory.require_case(case_id).known}
        for name, pattern in VERSION_PATTERNS.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                self.memory.add_fact(case_id, name, match.group(1), source="user")
                known[name] = match.group(1)
        lowered = text.lower()
        for name, hints in OS_HINTS.items():
            if any(hint in lowered for hint in hints):
                self.memory.add_fact(case_id, "os", name, source="user")
                known["os"] = name
        for name, hints in DEPLOYMENT_HINTS.items():
            if any(hint in lowered for hint in hints):
                self.memory.add_fact(case_id, "deployment", name, source="user")
                known["deployment"] = name
        for name in REQUIRED_FACTS:
            if name not in known:
                self.memory.add_unknown(case_id, name, reason="not stated in the report")

    def _search_evidence(self, case_id: str, text: str) -> None:
        state = self.memory.require_case(case_id)
        query = " ".join([state.title, text]).strip()
        response = self.call_tool("search_evidence", {"query": query, "top_k": 5})
        if not response["ok"]:
            return
        for item in response["result"]["results"]:
            self.memory.add_evidence_item(case_id, item)

    # -- the decision --------------------------------------------------------
    def decide(self, case_id: str) -> Decision:
        self._step("decide")
        state = self.memory.require_case(case_id)
        pending = state.pending_proposals()
        if pending:
            return Decision(
                kind="WAIT_FOR_APPROVAL",
                message=f"{len(pending)} proposal(s) are waiting for the maintainer.",
                proposal_id=pending[0].proposal_id,
            )
        known = {fact.name: fact.value for fact in state.known}
        missing = [name for name in ASK_FACTS if name not in known]
        if not state.sources:
            target = "the exact error text"
            return Decision(
                kind="ASK",
                message=f"I could not find matching evidence yet. Could you share {target}?",
            )
        if missing:
            return Decision(
                kind="ASK",
                message=f"Could you tell me the {missing[0].replace('_', ' ')}? That decides which fix applies.",
            )
        return self._propose(case_id)

    def _propose(self, case_id: str) -> Decision:
        state = self.memory.require_case(case_id)
        known = {fact.name: fact.value for fact in state.known}
        top = state.sources[0] if state.sources else None
        body = (
            f"Thanks for the report. Based on the evidence we found ({top.kind} {top.ref}), "
            f"this looks related to a known limitation. "
            f"You are on Streamlit {known.get('streamlit_version', 'unknown')} "
            f"({known.get('deployment', 'unknown')})."
        )
        response = self.call_tool(
            "propose_action",
            {
                "case_id": case_id,
                "action": "comment",
                "payload": {"body": body, "streamlit_version": known.get("streamlit_version", "")},
                "rationale": f"evidence from {top.ref if top else 'no source'}",
            },
        )
        if not response["ok"]:
            return Decision(kind="BLOCKED", message=response["message"])
        proposal_id = response["result"]["proposal_id"]
        return Decision(
            kind="PROPOSE",
            message="A suggested reply is ready for maintainer approval.",
            proposal_id=proposal_id,
            sources=[{"kind": row.kind, "ref": row.ref} for row in state.sources],
        )
    # -- human review --------------------------------------------------------
    def approve(self, case_id: str, proposal_id: str, decided_by: str = "maintainer") -> dict:
        self._step("approve")
        try:
            return self.approval.approve(case_id, proposal_id, decided_by)
        except ApprovalError as error:
            return {"ok": False, "error": error.code, "message": str(error)}

    def edit(self, case_id: str, proposal_id: str, action: str, payload: dict,
             decided_by: str = "maintainer") -> dict:
        self._step("edit")
        try:
            return self.approval.edit(case_id, proposal_id, action, payload, decided_by)
        except ApprovalError as error:
            return {"ok": False, "error": error.code, "message": str(error)}
        except MemoryError_ as error:
            return {"ok": False, "error": "edit_failed", "message": str(error)}

    def reject(self, case_id: str, proposal_id: str, decided_by: str = "maintainer") -> dict:
        self._step("reject")
        try:
            return self.approval.reject(case_id, proposal_id, decided_by)
        except ApprovalError as error:
            return {"ok": False, "error": error.code, "message": str(error)}
        except MemoryError_ as error:
            return {"ok": False, "error": "rejection_failed", "message": str(error)}

    def execute(self, case_id: str, proposal_id: str, approval_token: str) -> dict:
        self._step("execute")
        return self.call_tool(
            "apply_action",
            {"case_id": case_id, "proposal_id": proposal_id, "approval_token": approval_token},
        )
