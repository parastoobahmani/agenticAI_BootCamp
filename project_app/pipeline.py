"""Thin orchestration layer across the independently owned assignment parts.

This module translates and persists contracts. It deliberately does not copy
retrieval, analysis, response-composition, approval, or execution logic.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Callable, Iterable

from problem1_part1.evidence_synthesis.evidence_core import (
    EvidenceRetriever,
    SourceDocument,
    SynthesisResult,
    synthesize_evidence,
)
from problem1_part1.evidence_synthesis.evidence_synthesis_streamlit import build_corpus
from problem1_part2.implementation import AnalysisInput, Case, analyze
from problem1_part3 import markdown_summary, prepare_next_step_response
from problem1_to_problem2 import (
    evidence_synthesis_to_analysis_input,
    part3_response_to_action_request,
    part3_response_to_human_approval_v2_seed,
)
from problem2_parts1_2.interceptor import TicketInterceptor
from problem2_parts1_2.memory import CaseMemory
from problem2_parts1_2.models import CaseState, Proposal
from problem2_parts1_2.storage import Storage


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RUNS_DIR = ROOT / "project_app" / "runtime" / "runs"
DEFAULT_DB_PATH = ROOT / "problem2_parts1_2" / "runtime" / "support_agent.sqlite3"
DEFAULT_TRACKER_PATH = ROOT / "problem2_parts1_2" / "runtime" / "interceptor.json"
MAX_CASE_BYTES = 200_000


class IntegrationError(RuntimeError):
    """A stage boundary could not be completed safely."""


class PendingProposalError(IntegrationError):
    """A newer draft cannot replace an unresolved human-approval proposal."""


@dataclass(frozen=True)
class RunResult:
    case_id: str
    response_id: str
    proposal_id: str
    proposal_status: str
    artifact_dir: Path
    user_response: str
    import_mode: str
    provider_usage: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "response_id": self.response_id,
            "proposal_id": self.proposal_id,
            "proposal_status": self.proposal_status,
            "artifact_dir": str(self.artifact_dir),
            "user_response": self.user_response,
            "import_mode": self.import_mode,
            "provider_usage": self.provider_usage,
        }


def load_case_file(path: str | Path) -> dict[str, Any]:
    """Read and validate a bounded case JSON file."""
    source = Path(path)
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise IntegrationError(f"unable to read case file: {source}") from exc
    if len(raw) > MAX_CASE_BYTES:
        raise IntegrationError("case file exceeds 200 KB")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IntegrationError("case file must contain valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise IntegrationError("case file must contain one JSON object")
    try:
        return Case.model_validate(payload).model_dump(mode="json")
    except Exception as exc:
        raise IntegrationError("case file does not match the Part 2 Case contract") from exc


def synthesis_to_dict(result: SynthesisResult, documents: Iterable[SourceDocument]) -> dict[str, Any]:
    """Serialize Part 1 output while restoring source URLs from the corpus."""
    sources = {document.id: document for document in documents}
    evidence = []
    for item in result.evidence_used:
        source = sources.get(item.chunk.source_id)
        evidence.append({
            "score": item.score,
            "claim_type": item.claim_type,
            "extracted_claim": item.extracted_claim,
            "citation": item.citation,
            "relevance_reason": item.relevance_reason,
            "source_id": item.chunk.source_id,
            "source_type": item.chunk.source_type,
            "url": source.url_or_path if source else "",
        })
    return {
        "report_summary": result.report_summary,
        "known_facts": result.known_facts,
        "documented_explanations": result.documented_explanations,
        "hypotheses": result.hypotheses,
        "conflicting_sources": result.conflicting_sources,
        "evidence_used": evidence,
        "remaining_gaps": result.remaining_gaps,
        "recommended_next_action": result.recommended_next_action,
        "generated_at": result.generated_at,
    }


class ProjectPipeline:
    """Run the project through the public contract of every assignment part."""

    def __init__(
        self,
        *,
        documents: Iterable[SourceDocument] | None = None,
        runs_dir: str | Path = DEFAULT_RUNS_DIR,
        db_path: str | Path = DEFAULT_DB_PATH,
        tracker_path: str | Path = DEFAULT_TRACKER_PATH,
        top_k: int = 10,
    ) -> None:
        if not 1 <= top_k <= 20:
            raise ValueError("top_k must be between 1 and 20")
        self.documents = list(build_corpus() if documents is None else documents)
        if not self.documents:
            raise IntegrationError("the evidence corpus is empty")
        self.retriever = EvidenceRetriever()
        self.retriever.add_documents(self.documents)
        self.runs_dir = Path(runs_dir)
        self.db_path = Path(db_path)
        self.tracker_path = Path(tracker_path)
        self.top_k = top_k

    def run(
        self,
        case: dict[str, Any],
        *,
        compose: Callable[[list[dict], dict], dict] | None = None,
        provider_metadata: dict[str, Any] | None = None,
        provider_usage: Callable[[], dict[str, Any]] | None = None,
    ) -> RunResult:
        normalized = self._validate_case(case)

        comments = [row["body"] for row in normalized.get("comments", []) if row.get("body")]
        query = "\n".join([normalized["title"], normalized.get("body", ""), *comments])
        retrieved = self.retriever.retrieve(query, top_k=self.top_k)
        synthesis_result = synthesize_evidence(
            normalized["title"], normalized.get("body", ""), retrieved,
            conversation_history=comments,
        )
        synthesis = synthesis_to_dict(synthesis_result, self.documents)

        analysis_payload = evidence_synthesis_to_analysis_input(normalized, synthesis)
        analysis_input = AnalysisInput.model_validate(analysis_payload)
        report = analyze(analysis_input).model_dump(mode="json")
        response = prepare_next_step_response(report, compose=compose)
        handoff = markdown_summary(response)

        response_id = response["id"]
        final_dir = self._artifact_dir(normalized["case_id"], response_id)
        artifacts = {
            "input_case.json": normalized,
            "problem1_part1_synthesis.json": synthesis,
            "analysis_input.json": analysis_payload,
            "next_step_report.json": report,
            "part3_response.json": response,
            "maintainer_summary.md": handoff,
        }
        stage_dir = self._stage_artifacts(final_dir, artifacts)
        try:
            imported = self._import_problem2(response, analysis_payload)
            usage = provider_usage() if provider_usage is not None else None
            import_record = {
                "case_id": normalized["case_id"],
                "response_id": response_id,
                **imported,
            }
            self._write_json(stage_dir / "problem2_import.json", import_record)
            manifest = {
                "schema_version": "1.0",
                "status": "waiting_for_human_approval",
                "case_id": normalized["case_id"],
                "response_id": response_id,
                "proposal_id": imported["proposal_id"],
                "proposal_status": imported["proposal_status"],
                "import_mode": imported["import_mode"],
                "top_k": self.top_k,
                "evidence_document_count": len(self.documents),
                "retrieved_chunk_count": len(retrieved),
                "composition": response["composition"],
                "provider": provider_metadata,
                "provider_usage": usage,
                "artifacts": sorted([*artifacts, "problem2_import.json", "manifest.json"]),
            }
            self._write_json(stage_dir / "manifest.json", manifest)
            self._publish(stage_dir, final_dir)
        except Exception:
            shutil.rmtree(stage_dir, ignore_errors=True)
            raise

        return RunResult(
            case_id=normalized["case_id"],
            response_id=response_id,
            proposal_id=imported["proposal_id"],
            proposal_status=imported["proposal_status"],
            artifact_dir=final_dir,
            user_response=response["user_response"],
            import_mode=imported["import_mode"],
            provider_usage=usage,
        )

    @staticmethod
    def _validate_case(case: dict[str, Any]) -> dict[str, Any]:
        try:
            encoded = json.dumps(case, ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise IntegrationError("case must contain finite JSON data") from exc
        if len(encoded) > MAX_CASE_BYTES:
            raise IntegrationError("case exceeds 200 KB")
        try:
            return Case.model_validate(case).model_dump(mode="json")
        except Exception as exc:
            raise IntegrationError("case does not match the Part 2 Case contract") from exc

    def _artifact_dir(self, case_id: str, response_id: str) -> Path:
        safe_prefix = re.sub(r"[^A-Za-z0-9._-]+", "_", case_id).strip("._")[:60] or "case"
        case_hash = hashlib.sha256(case_id.encode("utf-8")).hexdigest()[:10]
        return self.runs_dir / f"{safe_prefix}_{case_hash}" / response_id

    def _stage_artifacts(self, final_dir: Path, artifacts: dict[str, Any]) -> Path:
        final_dir.parent.mkdir(parents=True, exist_ok=True)
        if final_dir.exists():
            expected = final_dir / "part3_response.json"
            if expected.exists():
                current = json.loads(expected.read_text(encoding="utf-8"))
                if current.get("id") != final_dir.name:
                    raise IntegrationError("existing artifact directory has different content")
            else:
                raise IntegrationError("existing artifact directory is incomplete")
        stage_dir = Path(tempfile.mkdtemp(prefix=f".{final_dir.name}.", dir=final_dir.parent))
        for name, payload in artifacts.items():
            target = stage_dir / name
            if isinstance(payload, str):
                target.write_text(payload + ("" if payload.endswith("\n") else "\n"), encoding="utf-8")
            else:
                self._write_json(target, payload)
        return stage_dir

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")

    @staticmethod
    def _publish(stage_dir: Path, final_dir: Path) -> None:
        if final_dir.exists():
            # A response ID is content-addressed. Preserve the original run
            # record and verify the immutable stage artifacts on a retry.
            immutable = {
                "input_case.json",
                "analysis_input.json",
                "next_step_report.json",
                "part3_response.json",
                "maintainer_summary.md",
            }
            for name in immutable:
                if not (final_dir / name).exists() or (final_dir / name).read_bytes() != (stage_dir / name).read_bytes():
                    raise IntegrationError("response ID collision or modified immutable run artifacts")
            # Part 1 records its wall-clock generation time. Ignore only that
            # field when determining whether an exact retry is equivalent.
            old_synthesis = json.loads((final_dir / "problem1_part1_synthesis.json").read_text(encoding="utf-8"))
            new_synthesis = json.loads((stage_dir / "problem1_part1_synthesis.json").read_text(encoding="utf-8"))
            old_synthesis.pop("generated_at", None)
            new_synthesis.pop("generated_at", None)
            if old_synthesis != new_synthesis:
                raise IntegrationError("response ID collision or modified immutable run artifacts")
            shutil.rmtree(stage_dir)
            return
        stage_dir.replace(final_dir)

    def _import_problem2(self, response: dict, analysis_input: dict) -> dict[str, str]:
        case_id = response["case_id"]
        storage = Storage(self.db_path)
        try:
            memory = CaseMemory(storage)
            state = storage.load_case(case_id)
            if state is not None:
                existing = self._proposal_for_response(state, response["id"])
                if existing is not None:
                    self._ensure_ticket(case_id, state.title)
                    return self._import_result(existing, "reused")
                pending = state.pending_proposals()
                if pending:
                    raise PendingProposalError(
                        f"case {case_id!r} already has an unresolved proposal; approve or reject it before importing a new response revision"
                    )
                request = part3_response_to_action_request(response)
                state = memory.create_proposal(
                    request["case_id"], request["action"], request["payload"], request["rationale"]
                )
                proposal = state.proposals[-1]
                storage.log(case_id, "problem1_response_imported", {"response_id": response["id"]})
                self._ensure_ticket(case_id, state.title)
                return self._import_result(proposal, "new_revision")

            seed = part3_response_to_human_approval_v2_seed(response, analysis_input)
            state = CaseState.from_dict(seed)
            if not state.proposals:
                raise IntegrationError("Part 3 response did not produce a Problem 2 proposal")
            storage.save_case(state)
            storage.log(case_id, "problem1_response_imported", {"response_id": response["id"]})
            self._ensure_ticket(case_id, state.title)
            return self._import_result(state.proposals[0], "created")
        finally:
            storage.close()

    def _ensure_ticket(self, case_id: str, title: str) -> None:
        TicketInterceptor(self.tracker_path).ensure(case_id, title=title)

    @staticmethod
    def _proposal_for_response(state: CaseState, response_id: str) -> Proposal | None:
        marker = f"response_id={response_id};"
        return next((proposal for proposal in state.proposals if marker in proposal.rationale), None)

    @staticmethod
    def _import_result(proposal: Proposal, mode: str) -> dict[str, str]:
        return {
            "proposal_id": proposal.proposal_id,
            "proposal_status": proposal.status,
            "import_mode": mode,
        }
