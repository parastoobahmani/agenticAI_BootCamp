"""Adapter for the output of part 1 (branch ``finding_synthesizing_evidence``).

Part 1 writes ``evidence_synthesis_result.json``::

    {report_summary, known_facts, documented_explanations, hypotheses,
     conflicting_sources, remaining_gaps, recommended_next_action, generated_at,
     evidence_used: [{score, claim_type, extracted_claim, citation,
                      relevance_reason, source_id, source_type, url, chunk_id?}]}

and keeps its corpus snapshot in ``problem1_part1/data`` (``issues.jsonl``,
``comments.jsonl``, ``documentation.jsonl``, ``release_notes.jsonl``).

Mapping decisions:
* Every ``evidence_used`` item becomes one ``Evidence``. Its id is the chunk id
  (from ``chunk_id`` or the "(chunk …)" part of the citation).
* Part 1 does not group evidence into explanations, so every item also becomes
  one candidate ``Hypothesis`` (statement = extracted claim, confidence = score).
* Part 1's ``url`` field holds the chunk title. The real URL, docs section and
  version are looked up in the snapshot when ``SourceIndex`` is given.
* ``conflicting_sources`` and source-coverage ``remaining_gaps`` become notes.
  Gaps about the user's environment and ``recommended_next_action`` are ignored:
  this part recomputes them from the conversation itself.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from problem1_part2.implementation.schemas import Case, ClaimKind, Evidence, EvidenceBundle, Hypothesis, SourceType

GITHUB_ISSUE_URL = "https://github.com/streamlit/streamlit/issues/{number}"

_SOURCE_TYPES = {
    "documentation": SourceType.DOC,
    "past_report": SourceType.ISSUE,
    "release_note": SourceType.RELEASE_NOTE,
}
_CHUNK_ID = re.compile(r"\(chunk ([0-9a-f]+)\)")
_CITATION_VERSION = re.compile(r" – v(\d+\.\d+(?:\.\d+)?)\b")
_ISSUE_ID = re.compile(r"^issue-(\d+)$")
_MENTIONS_FIX = re.compile(r"\bfix(?:ed|es)?\b|\bbug\b|\bresolved?\b", re.IGNORECASE)
# Part-1 gaps that describe the user's report rather than the evidence base.
_USER_GAP = re.compile(r"\buser\b", re.IGNORECASE)


@dataclass(frozen=True)
class SourceRecord:
    url: str
    section: str | None = None
    version: str | None = None


class SourceIndex:
    """Lookup of part-1 source ids (``doc-…``, ``release-…``, ``issue-…``) in the snapshot."""

    def __init__(self, records: Mapping[str, SourceRecord]) -> None:
        self._records = dict(records)

    def get(self, source_id: str) -> SourceRecord | None:
        return self._records.get(source_id)

    @classmethod
    def from_snapshot(cls, data_dir: Path) -> SourceIndex:
        records: dict[str, SourceRecord] = {}
        for row in _read_jsonl(data_dir / "documentation.jsonl"):
            records[row["id"]] = SourceRecord(
                url=row["url_or_path"], section=_clean(row.get("section")), version=_clean(row.get("commit"))
            )
        for row in _read_jsonl(data_dir / "release_notes.jsonl"):
            records[row["id"]] = SourceRecord(url=row["url_or_path"], version=_clean(row.get("version")))
        for row in _read_jsonl(data_dir / "issues.jsonl"):
            records[f"issue-{row['number']}"] = SourceRecord(url=row["html_url"])
        return cls(records)


def bundle_from_synthesis(result: Mapping[str, Any], sources: SourceIndex | None = None) -> EvidenceBundle:
    evidence: list[Evidence] = []
    hypotheses: list[Hypothesis] = []
    seen_statements: set[str] = set()

    for index, item in enumerate(result.get("evidence_used", [])):
        converted = _evidence(item, index, sources, taken={entry.evidence_id for entry in evidence})
        evidence.append(converted)

        statement = (item.get("extracted_claim") or "").strip()
        if not statement or statement in seen_statements:
            continue
        seen_statements.add(statement)
        hypotheses.append(
            Hypothesis(
                hypothesis_id=f"h{len(hypotheses) + 1}",
                statement=statement,
                confidence=converted.relevance,
                evidence_ids=[converted.evidence_id],
            )
        )

    notes = [conflict["description"] for conflict in result.get("conflicting_sources", []) if conflict.get("description")]
    notes += [gap for gap in result.get("remaining_gaps", []) if not _USER_GAP.search(gap)]
    return EvidenceBundle(evidence=evidence, hypotheses=hypotheses, notes=notes)


def case_from_snapshot(issue_number: int | str, data_dir: Path) -> Case:
    """Load one issue and its comments from part 1's ``issues.jsonl`` / ``comments.jsonl``."""
    number = str(issue_number)
    issue = next((row for row in _read_jsonl(data_dir / "issues.jsonl") if str(row["number"]) == number), None)
    if issue is None:
        raise LookupError(f"issue {number} is not in {data_dir / 'issues.jsonl'}")
    comments = [row for row in _read_jsonl(data_dir / "comments.jsonl") if str(row["issue_number"]) == number]
    return Case.from_github(issue, comments)


def _evidence(item: Mapping[str, Any], index: int, sources: SourceIndex | None, taken: set[str]) -> Evidence:
    source_id = item.get("source_id") or f"source-{index}"
    source_type = _SOURCE_TYPES.get(item.get("source_type", ""), SourceType.DOC)
    citation = item.get("citation") or ""
    record = sources.get(source_id) if sources else None

    version = (record.version if record else None) or _first_group(_CITATION_VERSION, citation)
    claim = item.get("extracted_claim") or ""
    fixed_in = version if source_type is SourceType.RELEASE_NOTE and _MENTIONS_FIX.search(claim) else None

    return Evidence(
        evidence_id=_unique_id(item.get("chunk_id") or _first_group(_CHUNK_ID, citation) or source_id, index, taken),
        source_type=source_type,
        title=item.get("url") or citation or source_id,
        url=record.url if record else _fallback_url(source_id),
        section=record.section if record else None,
        snippet=claim,
        source_version=version,
        relevance=min(1.0, max(0.0, float(item.get("score") or 0.0))),
        relation=item.get("relevance_reason"),
        claim_kind=_claim_kind(item.get("claim_type"), source_type),
        fixed_in_version=fixed_in,
    )


def _claim_kind(claim_type: str | None, source_type: SourceType) -> ClaimKind:
    if claim_type == "documented_explanation":
        return ClaimKind.DOCUMENTED
    if claim_type == "fact":
        return ClaimKind.REPORTED_FACT if source_type is SourceType.ISSUE else ClaimKind.DOCUMENTED
    return ClaimKind.HYPOTHESIS


def _fallback_url(source_id: str) -> str:
    match = _ISSUE_ID.match(source_id)
    return GITHUB_ISSUE_URL.format(number=match.group(1)) if match else source_id


def _unique_id(candidate: str, index: int, taken: set[str]) -> str:
    return candidate if candidate not in taken else f"{candidate}#{index}"


def _first_group(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(1) if match else None


def _clean(value: Any) -> str | None:
    """Snapshot files store missing values as null, "None" or ""."""
    return None if value in (None, "", "None") else str(value)


def _read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)
