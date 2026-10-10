"""Application service used by the web server.

The service coordinates existing public boundaries. It owns no retrieval,
analysis, response-composition, or approval policy.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re
import threading
import uuid
from typing import Any

from problem1_part2.implementation import Case
from problem1_part3.configuration import GatewayConfig
from problem1_part3.provider import Gateway
from problem2_parts1_2.interceptor import TicketInterceptor
from problem2_parts1_2.orchestrator import Orchestrator
from problem2_parts1_2.storage import Storage

from .pipeline import IntegrationError, ProjectPipeline, RunResult
from .web_store import WebStore


CASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$")
RESPONSE_MARKER = re.compile(r"\bresponse_id=([^;\s]+);")


class WebFlowError(IntegrationError):
    pass


class ProjectWebService:
    def __init__(
        self,
        pipeline: ProjectPipeline,
        web_store: WebStore,
        *,
        gateway_config: GatewayConfig | None = None,
    ) -> None:
        self.pipeline = pipeline
        self.web_store = web_store
        self.gateway_config = gateway_config
        self._lock = threading.RLock()

    def submit_case(self, case_id: str, title: str, body: str) -> RunResult:
        case_id, title, body = self._validate_submission(case_id, title, body)
        with self._lock:
            storage = Storage(self.pipeline.db_path)
            try:
                if storage.load_case(case_id) is not None:
                    raise WebFlowError(f"case {case_id!r} already exists")
            finally:
                storage.close()
            case = Case(case_id=case_id, title=title, body=body, comments=[]).model_dump(mode="json")
            result = self._run(case)
            self._save(case, result)
            self.web_store.event(case_id, "user", "case_submitted", {"response_id": result.response_id})
            return result

    def add_user_message(self, case_id: str, body: str) -> RunResult:
        body = body.strip()
        if not body or len(body) > 12_000:
            raise WebFlowError("message must contain between 1 and 12,000 characters")
        with self._lock:
            case = deepcopy(self.case_input(case_id))
            state_before = self._state(case_id)
            superseded = [item.proposal_id for item in state_before.pending_proposals()] if state_before else []
            comments = case.setdefault("comments", [])
            comments.append({
                "id": f"web-{uuid.uuid4().hex}",
                "body": body,
                "author": "user",
                "author_association": "NONE",
            })
            result = self._run(
                case,
                supersede_pending=True,
                force_new_proposal=True,
            )
            self._save(case, result)
            if superseded:
                self.web_store.event(case_id, "system", "draft_superseded", {
                    "proposal_ids": superseded,
                    "reason": "new_user_information",
                })
            self.web_store.event(case_id, "user", "message_added", {
                "comment_id": comments[-1]["id"],
                "response_id": result.response_id,
            })
            return result

    def approve_and_publish(self, case_id: str, proposal_id: str, body: str) -> dict[str, Any]:
        body = body.strip()
        if not body or len(body) > 12_000:
            raise WebFlowError("approved reply must contain between 1 and 12,000 characters")
        with self._lock:
            orchestrator = self._orchestrator()
            try:
                state = orchestrator.memory.require_case(case_id)
                proposal = state.proposal(proposal_id)
                if proposal is None or proposal.status != "pending":
                    raise WebFlowError("the proposal is no longer pending")
                current_body = str(proposal.payload.get("body", ""))
                if body == current_body:
                    approval = orchestrator.approve(case_id, proposal_id, "web-maintainer")
                else:
                    approval = orchestrator.edit(
                        case_id, proposal_id, "comment", {"body": body}, "web-maintainer"
                    )
                if not approval.get("ok"):
                    raise WebFlowError(approval.get("message", "approval failed"))
                execution = orchestrator.execute(case_id, proposal_id, approval["approval_token"])
                if not execution.get("ok"):
                    raise WebFlowError(execution.get("message", "execution failed"))
                self.web_store.event(case_id, "maintainer", "reply_published", {
                    "proposal_id": proposal_id,
                    "edited": body != current_body,
                })
                return execution
            finally:
                orchestrator.storage.close()

    def reject(self, case_id: str, proposal_id: str, note: str = "") -> dict[str, Any]:
        if len(note) > 2_000:
            raise WebFlowError("review note exceeds 2,000 characters")
        with self._lock:
            orchestrator = self._orchestrator()
            try:
                result = orchestrator.reject(case_id, proposal_id, "web-maintainer")
                if not result.get("ok"):
                    raise WebFlowError(result.get("message", "rejection failed"))
                self.web_store.event(case_id, "maintainer", "proposal_rejected", {
                    "proposal_id": proposal_id,
                    "note": note.strip(),
                })
                return result
            finally:
                orchestrator.storage.close()

    def case_input(self, case_id: str) -> dict[str, Any]:
        record = self.web_store.get_case(case_id)
        if record is not None:
            return record["case"]
        state = self._state(case_id)
        if state is None:
            raise WebFlowError(f"unknown case {case_id!r}")
        for proposal in reversed(state.proposals):
            match = RESPONSE_MARKER.search(proposal.rationale)
            if match:
                artifact = self.pipeline._artifact_dir(case_id, match.group(1)) / "input_case.json"
                if artifact.exists():
                    return json.loads(artifact.read_text(encoding="utf-8"))
        return {
            "case_id": state.case_id,
            "title": state.title,
            "body": state.body,
            "comments": [],
        }

    def list_cases(self) -> list[dict[str, Any]]:
        records = {row["case"]["case_id"]: row for row in self.web_store.list_cases()}
        storage = Storage(self.pipeline.db_path)
        try:
            for case_id in storage.list_cases():
                state = storage.load_case(case_id)
                if state is None:
                    continue
                record = records.setdefault(case_id, {
                    "case": {"case_id": case_id, "title": state.title, "body": state.body, "comments": []},
                    "latest_response_id": "",
                    "latest_proposal_id": "",
                    "artifact_dir": "",
                    "updated_at": state.updated_at,
                })
                record["case_status"] = state.status
                record["pending_count"] = len(state.pending_proposals())
                record["proposal_count"] = len(state.proposals)
                if state.proposals:
                    record["latest_proposal_id"] = state.proposals[-1].proposal_id
            return sorted(records.values(), key=lambda row: row.get("updated_at", ""), reverse=True)
        finally:
            storage.close()

    def case_detail(self, case_id: str) -> dict[str, Any]:
        storage = Storage(self.pipeline.db_path)
        try:
            state = storage.load_case(case_id)
            if state is None:
                raise WebFlowError(f"unknown case {case_id!r}")
            pending = state.pending_proposals()
            proposal = pending[0] if pending else (state.proposals[-1] if state.proposals else None)
            response_id = ""
            if proposal:
                match = RESPONSE_MARKER.search(proposal.rationale)
                response_id = match.group(1) if match else ""
            record = self.web_store.get_case(case_id)
            artifact_dir = Path(record["artifact_dir"]) if record and record.get("artifact_dir") else None
            if response_id:
                expected = self.pipeline._artifact_dir(case_id, response_id)
                if (artifact_dir is None or not artifact_dir.exists()) and expected.exists():
                    artifact_dir = expected
            artifacts = self._read_artifacts(artifact_dir)
            ticket = TicketInterceptor(self.pipeline.tracker_path).ensure(case_id, title=state.title)
            return {
                "state": state.to_dict(),
                "proposal": proposal.to_dict() if proposal else None,
                "pending_count": len(pending),
                "case": self.case_input(case_id),
                "ticket": ticket,
                "events": self.web_store.events(case_id),
                "artifact_dir": str(artifact_dir) if artifact_dir else "",
                **artifacts,
            }
        finally:
            storage.close()

    def _run(self, case: dict[str, Any], **options) -> RunResult:
        gateway = Gateway(self.gateway_config) if self.gateway_config else None
        return self.pipeline.run(
            case,
            compose=gateway.complete if gateway else None,
            provider_metadata=self.gateway_config.public() if self.gateway_config else None,
            provider_usage=(lambda: gateway.last_usage) if gateway else None,
            **options,
        )

    def _save(self, case: dict[str, Any], result: RunResult) -> None:
        self.web_store.save_case(
            case,
            response_id=result.response_id,
            proposal_id=result.proposal_id,
            artifact_dir=str(result.artifact_dir),
        )

    def _orchestrator(self) -> Orchestrator:
        storage = Storage(self.pipeline.db_path)
        interceptor = TicketInterceptor(self.pipeline.tracker_path)
        return Orchestrator(storage, interceptor)

    def _state(self, case_id: str):
        storage = Storage(self.pipeline.db_path)
        try:
            return storage.load_case(case_id)
        finally:
            storage.close()

    @staticmethod
    def _read_artifacts(directory: Path | None) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if directory is None:
            return result
        for key, name in (
            ("response", "part3_response.json"),
            ("report", "next_step_report.json"),
            ("synthesis", "problem1_part1_synthesis.json"),
            ("manifest", "manifest.json"),
        ):
            path = directory / name
            if path.exists():
                result[key] = json.loads(path.read_text(encoding="utf-8"))
        return result

    @staticmethod
    def _validate_submission(case_id: str, title: str, body: str) -> tuple[str, str, str]:
        case_id, title, body = case_id.strip(), title.strip(), body.strip()
        if not CASE_ID.fullmatch(case_id):
            raise WebFlowError("case ID must be 1-100 letters, numbers, dots, colons, underscores, or hyphens")
        if not title or len(title) > 500:
            raise WebFlowError("title must contain between 1 and 500 characters")
        if not body or len(body) > 50_000:
            raise WebFlowError("report must contain between 1 and 50,000 characters")
        return case_id, title, body
