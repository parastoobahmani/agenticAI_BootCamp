"""Pure, deterministic adapters for the team branches.

The adapters preserve stage ownership: evidence synthesis is not asked to emit
Part 2 classes, and Problem 2 is not coupled to Part 3 implementation details.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


class ContractError(ValueError):
    """Raised when two stage artifacts cannot be joined safely."""


def _stable_id(prefix: str, value: Any, length: int = 12) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{prefix}_{hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:length]}"


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def evidence_synthesis_to_analysis_input(case: dict, synthesis: dict) -> dict:
    """Convert `finding_synthesizing_evidence` output to Ali's AnalysisInput.

    Retrieval similarity is deliberately not converted into hypothesis
    confidence. Synthesized hypotheses receive confidence 0.0 because the
    upstream artifact provides no calibrated confidence value.
    """
    if not isinstance(case, dict) or not _text(case.get("case_id")).strip():
        raise ContractError("case.case_id is required")
    if not _text(case.get("title")).strip():
        raise ContractError("case.title is required")
    if not isinstance(synthesis, dict):
        raise ContractError("synthesis must be an object")

    source_type = {
        "documentation": "doc",
        "past_report": "issue",
        "release_note": "release_note",
        "doc": "doc",
        "issue": "issue",
    }
    claim_kind = {
        "documented_explanation": "documented",
        "hypothesis": "hypothesis",
        # An extracted source claim is not a fact reported by this case.
        "fact": "documented",
    }

    evidence = []
    citation_to_ids: dict[str, list[str]] = {}
    for item in synthesis.get("evidence_used", []):
        if not isinstance(item, dict):
            continue
        raw_kind = _text(item.get("source_type"))
        kind = source_type.get(raw_kind)
        if kind is None:
            continue
        evidence_id = _stable_id("evidence", {
            "source_id": item.get("source_id"),
            "citation": item.get("citation"),
            "claim": item.get("extracted_claim"),
        })
        citation = _text(item.get("citation"))
        citation_to_ids.setdefault(citation, []).append(evidence_id)
        score = item.get("score", 0.0)
        try:
            score = min(1.0, max(0.0, float(score)))
        except (TypeError, ValueError):
            score = 0.0
        evidence.append({
            "evidence_id": evidence_id,
            "source_type": kind,
            "title": _text(item.get("source_id") or item.get("url") or citation),
            "url": _text(item.get("url")),
            "section": None,
            "snippet": _text(item.get("extracted_claim")),
            "source_version": None,
            "relevance": score,
            "relation": _text(item.get("relevance_reason")) or None,
            "claim_kind": claim_kind.get(_text(item.get("claim_type")), "documented"),
            "fixed_in_version": None,
            "author_association": None,
        })

    hypotheses = []
    for item in synthesis.get("hypotheses", []):
        if not isinstance(item, dict) or not _text(item.get("claim")).strip():
            continue
        citation = _text(item.get("citation") or item.get("citation_or_none"))
        statement = _text(item.get("claim")).strip()
        hypotheses.append({
            "hypothesis_id": _stable_id("hypothesis", {"statement": statement, "citation": citation}),
            "statement": statement,
            "confidence": 0.0,
            "evidence_ids": citation_to_ids.get(citation, []),
            "expectations": None,
        })

    comments = []
    for comment in case.get("comments", []):
        if not isinstance(comment, dict):
            continue
        comments.append({key: comment[key] for key in (
            "id", "body", "created_at", "author", "author_association"
        ) if key in comment})

    normalized_case = {
        "case_id": _text(case["case_id"]),
        "title": _text(case["title"]),
        "body": _text(case.get("body")),
        "comments": comments,
    }
    for name in ("url", "author", "created_at"):
        if name in case:
            normalized_case[name] = case[name]
    return {
        "case": normalized_case,
        "evidence_bundle": {"evidence": evidence, "hypotheses": hypotheses},
    }


def part3_response_to_memory_seed(response: dict, analysis_input: dict | None = None) -> dict:
    """Create a `feat/memory_tools` CaseState-compatible dictionary.

    `analysis_input` is optional but recommended because Part 3 intentionally
    does not receive the original title/body or resolved evidence content.
    """
    if not isinstance(response, dict) or not _text(response.get("case_id")).strip():
        raise ContractError("Part3Response.case_id is required")
    summary = response.get("technical_summary")
    if not isinstance(summary, dict):
        raise ContractError("Part3Response.technical_summary is required")

    case_id = _text(response["case_id"])
    case: dict = {}
    evidence_rows: list[dict] = []
    if analysis_input is not None:
        if not isinstance(analysis_input, dict):
            raise ContractError("analysis_input must be an object")
        case = analysis_input.get("case", {})
        if _text(case.get("case_id")) != case_id:
            raise ContractError("case_id differs between AnalysisInput and Part3Response")
        evidence_rows = analysis_input.get("evidence_bundle", {}).get("evidence", [])

    known = []
    checks = []
    for fact in summary.get("known_facts", []):
        if not isinstance(fact, dict) or not _text(fact.get("facet")).strip():
            continue
        facet = _text(fact["facet"])
        origin = fact.get("origin") if isinstance(fact.get("origin"), dict) else {}
        value = fact.get("value")
        known.append({
            "name": facet,
            "value": "outcome unknown" if value is None else _text(value),
            "source": _text(origin.get("location")) or "problem1",
        })
        if fact.get("status") == "performed_outcome_unknown":
            checks.append({"name": facet, "status": "performed_outcome_unknown", "result": ""})

    for step in summary.get("next_steps", []):
        if isinstance(step, dict) and step.get("kind") == "check":
            checks.append({"name": _text(step.get("facet")), "status": "pending", "result": ""})

    unknown = [
        {"name": _text(item.get("facet")), "reason": _text(item.get("description"))}
        for item in summary.get("missing_information", [])
        if isinstance(item, dict) and _text(item.get("facet")).strip()
    ]

    sources = []
    seen = set()
    for item in evidence_rows:
        if not isinstance(item, dict):
            continue
        ref = _text(item.get("evidence_id"))
        if not ref or ref in seen:
            continue
        seen.add(ref)
        sources.append({
            "kind": _text(item.get("source_type")) or "document",
            "ref": ref,
            "title": _text(item.get("title")),
            "snippet": _text(item.get("snippet")),
            "score": float(item.get("relevance", 0.0)),
        })
    for ref in summary.get("unresolved_evidence_ids", []):
        ref = _text(ref)
        if ref and ref not in seen:
            sources.append({"kind": "unresolved", "ref": ref, "title": "", "snippet": "", "score": 0.0})
            seen.add(ref)

    reply = _text(response.get("user_response")).strip()
    proposals = []
    if reply:
        request = part3_response_to_action_request(response)
        proposals.append({
            "proposal_id": _stable_id("PRP", {"case_id": case_id, "response_id": response.get("id"), "body": reply}, 8),
            "action": request["action"],
            "payload": request["payload"],
            "rationale": request["rationale"],
            "status": "pending",
            "decided_by": "",
            "decided_at": "",
        })

    return {
        "case_id": case_id,
        "title": _text(case.get("title")),
        "body": _text(case.get("body")),
        "status": "open",
        "known": known,
        "unknown": unknown,
        "checks": checks,
        "sources": sources,
        "proposals": proposals,
        "actions": [],
        "turn": len(case.get("comments", [])) if isinstance(case.get("comments", []), list) else 0,
    }


def part3_response_to_action_request(response: dict) -> dict:
    """Convert any immutable Part 3 revision to v2 `propose_action` arguments.

    Use this for subsequent responses after a Problem 2 CaseState already exists.
    Problem 2 assigns the current case version and action hash when it creates the
    proposal; Part 3 never guesses the mutable version.
    """
    if not isinstance(response, dict) or not _text(response.get("case_id")).strip():
        raise ContractError("Part3Response.case_id is required")
    reply = _text(response.get("user_response")).strip()
    if not reply:
        raise ContractError("Part3Response.user_response is required")
    summary = response.get("technical_summary")
    if not isinstance(summary, dict):
        raise ContractError("Part3Response.technical_summary is required")
    provenance = (
        f"Part3 response_id={_text(response.get('id'))}; "
        f"input_fingerprint={_text(response.get('input_fingerprint'))}."
    )
    decision_rationale = _text(summary.get("decision", {}).get("rationale")).strip()
    return {
        "case_id": _text(response["case_id"]),
        "action": "comment",
        "payload": {"body": reply},
        "rationale": provenance + (f" {decision_rationale}" if decision_rationale else ""),
    }


def part3_response_to_human_approval_v2_seed(
    response: dict, analysis_input: dict | None = None
) -> dict:
    """Create a `human_approval_v2` versioned CaseState dictionary.

    Version 1 represents the imported Problem 1 state. The pending proposal is
    bound to that same version and to the exact canonical comment action.
    """
    seed = part3_response_to_memory_seed(response, analysis_input)
    version = 1
    seed["version"] = version
    seed["approvals"] = []
    for proposal in seed["proposals"]:
        proposal["case_version"] = version
        canonical = json.dumps(
            {"action": proposal["action"], "payload": proposal["payload"]},
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )
        proposal["action_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        proposal["decision"] = ""
    return seed
