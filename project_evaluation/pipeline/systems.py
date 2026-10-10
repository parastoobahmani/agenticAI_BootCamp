"""The systems compared by the evaluation, behind one interface.

* ``BaselineSystem``: the original keyword-overlap stub (``system_under_test.py``)
  with its fixed policy, kept unchanged as the simple baseline.
* ``IntegratedSystem``: the real project pipeline (``project_app.ProjectPipeline``):
  Part 1 retrieval and synthesis -> Part 2 next-step decision -> Part 3 reply ->
  pending Problem 2 proposal. Each case runs against its own temporary SQLite store
  and tracker, which are inspected afterwards for the operational checks.

Both receive the same leakage-controlled corpus and the case's visible input only.
A failure inside a system is recorded on the case instead of stopping the run.
"""
from __future__ import annotations

import json
import re
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from problem2_parts1_2.interceptor import InterceptorError, TicketInterceptor
from problem2_parts1_2.storage import Storage
from project_app.pipeline import ProjectPipeline
from system_under_test import SupportAssistant

# Part 2 decision types -> the evaluation's action vocabulary.
PART2_ACTIONS = {
    "propose_answer": "answer",
    "request_information": "ask_clarification",
    "escalate": "escalate",
}
_CHUNK_ID = re.compile(r"\(chunk ([0-9a-f]+)\)")


@dataclass
class CaseRun:
    """What one system did on one case."""

    action: Optional[str]  # one of config.ACTIONS, or None when the system failed
    text: str = ""
    retrieved_source_ids: List[str] = field(default_factory=list)
    retrieved_chunk_ids: List[str] = field(default_factory=list)
    latency_sec: float = 0.0
    setup_sec: float = 0.0
    # Real provider usage; "token_estimate" is only a length heuristic when no API is called.
    usage: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    # Part 2 view (integrated only): decision, steps asked, facts already known.
    next_step: Optional[Dict[str, Any]] = None
    # Checks on the stored Problem 2 state after the run (integrated only).
    operational: Optional[Dict[str, bool]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _no_usage() -> Dict[str, Any]:
    return {"api_requests": 0, "input_tokens": 0, "output_tokens": 0, "estimated_cost_usd": 0.0}


class BaselineSystem:
    name = "baseline"

    def run_case(self, case: Dict[str, Any], corpus: List[Any]) -> CaseRun:
        assistant = SupportAssistant()
        try:
            out = assistant.reply([{"role": "user", "content": f"{case['title']}\n\n{case['body']}"}], corpus)
        except Exception as exc:  # isolation boundary: one failing case must not stop the evaluation
            return CaseRun(action=None, error=f"{type(exc).__name__}: {exc}")
        evidence = out["result"].evidence_used
        return CaseRun(
            action=out["action"],
            text=out["text"],
            retrieved_source_ids=[item.chunk.source_id for item in evidence],
            retrieved_chunk_ids=list(out["retrieved_chunk_ids"]),
            latency_sec=out["latency_sec"],
            usage={**_no_usage(), "token_estimate": out["token_estimate"]},
        )


class IntegratedSystem:
    name = "integrated"

    def __init__(
        self,
        compose: Optional[Callable[[list, dict], dict]] = None,
        provider_usage: Optional[Callable[[], Dict[str, Any]]] = None,
        top_k: int = 10,
    ) -> None:
        self._compose = compose
        self._provider_usage = provider_usage
        self._top_k = top_k

    def run_case(self, case: Dict[str, Any], corpus: List[Any]) -> CaseRun:
        payload = {"case_id": case["case_id"], "title": case["title"], "body": case["body"], "comments": []}
        with tempfile.TemporaryDirectory(prefix="eval-") as directory:
            root = Path(directory)
            db_path, tracker_path = root / "cases.sqlite3", root / "tracker.json"

            started = time.perf_counter()
            pipeline = ProjectPipeline(
                documents=corpus, runs_dir=root / "runs", db_path=db_path, tracker_path=tracker_path, top_k=self._top_k
            )
            setup_sec = time.perf_counter() - started

            started = time.perf_counter()
            try:
                result = pipeline.run(payload, compose=self._compose, provider_usage=self._provider_usage)
            except Exception as exc:  # isolation boundary: record the failure, keep evaluating
                return CaseRun(
                    action=None,
                    latency_sec=time.perf_counter() - started,
                    setup_sec=setup_sec,
                    usage=_no_usage(),
                    error=f"{type(exc).__name__}: {exc}",
                )
            latency_sec = time.perf_counter() - started

            artifacts = result.artifact_dir
            report = json.loads((artifacts / "next_step_report.json").read_text(encoding="utf-8"))
            synthesis = json.loads((artifacts / "problem1_part1_synthesis.json").read_text(encoding="utf-8"))
            manifest = json.loads((artifacts / "manifest.json").read_text(encoding="utf-8"))
            evidence = synthesis.get("evidence_used", [])
            return CaseRun(
                action=PART2_ACTIONS[report["decision"]["type"]],
                text=result.user_response,
                retrieved_source_ids=[item.get("source_id") for item in evidence if item.get("source_id")],
                retrieved_chunk_ids=[
                    match.group(1) for item in evidence if (match := _CHUNK_ID.search(item.get("citation") or ""))
                ],
                latency_sec=latency_sec,
                setup_sec=setup_sec,
                usage=self._usage(manifest),
                next_step={
                    "decision": report["decision"]["type"],
                    "asked": [step["facet"] for step in report["next_steps"]],
                    "bases": [step["basis"] for step in report["next_steps"]],
                    "known": [fact["facet"] for fact in report["known_facts"]],
                },
                operational=self._stored_state_checks(case["case_id"], db_path, tracker_path),
            )

    @staticmethod
    def _usage(manifest: Dict[str, Any]) -> Dict[str, Any]:
        usage = _no_usage()
        provider = manifest.get("provider_usage") or {}
        if manifest.get("composition", {}).get("method") == "model":
            usage["api_requests"] = 1
        usage["input_tokens"] = int(provider.get("input_tokens") or 0)
        usage["output_tokens"] = int(provider.get("output_tokens") or 0)
        usage["estimated_cost_usd"] = float(provider.get("estimated_cost_usd") or 0.0)
        return usage

    @staticmethod
    def _stored_state_checks(case_id: str, db_path: Path, tracker_path: Path) -> Dict[str, bool]:
        """Inspect what was actually persisted, not what the reply text claims."""
        storage = Storage(db_path)
        try:
            state = storage.load_case(case_id)
        finally:
            storage.close()
        try:
            ticket = TicketInterceptor(tracker_path).get(case_id)
        except (InterceptorError, OSError, ValueError):
            ticket = None
        return {
            "case_persisted": state is not None,
            "one_pending_proposal": state is not None and len(state.pending_proposals()) == 1,
            "nothing_executed_without_approval": state is not None and not state.approvals and not state.actions,
            "tracker_unchanged": ticket is not None
            and not ticket.get("comments")
            and not ticket.get("labels")
            and ticket.get("state") == "open",
        }
