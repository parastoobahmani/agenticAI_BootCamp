"""
evidence_synthesis_streamlit.py
Part 1 – Finding & Synthesizing Evidence
Loads the static snapshot produced by the collection scripts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

# Re-use the dataclasses & logic from the previous answer
# (SourceDocument, Chunk, EvidenceItem, SynthesisResult,
#  simple_chunk, EvidenceRetriever, synthesize_evidence, …)

from problem1_part1.evidence_synthesis.evidence_core import (
    SourceDocument,
    EvidenceRetriever,
    synthesize_evidence,
    SynthesisResult,
)

RAW = Path(__file__).resolve().parents[1] / "data"


def load_past_reports() -> List[SourceDocument]:
    """Turn each issue + its comments into a single searchable document."""
    issues = [json.loads(l) for l in (RAW / "issues.jsonl").read_text().splitlines() if l.strip()]
    comments_by_issue = {}
    for line in (RAW / "comments.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        c = json.loads(line)
        comments_by_issue.setdefault(c["issue_number"], []).append(c)

    docs = []
    for iss in issues:
        comment_text = "\n\n".join(
            f"[comment by {c.get('author_association')} @ {c['created_at']}]\n{c['body']}"
            for c in sorted(comments_by_issue.get(iss["number"], []), key=lambda x: x["created_at"])
        )
        full = (
            f"Title: {iss['title']}\n"
            f"State: {iss['state']} ({iss.get('state_reason')})\n"
            f"Labels: {', '.join(iss.get('labels', []))}\n\n"
            f"{iss['body']}\n\n"
            f"--- Discussion ---\n{comment_text}"
        )
        docs.append(SourceDocument(
            id=f"issue-{iss['number']}",
            source_type="past_report",
            title=iss["title"],
            content=full,
            url_or_path=iss["html_url"],
            version=None,  # version lives inside the body text
            date=iss["created_at"],
            metadata={"number": iss["number"], "labels": iss.get("labels", [])},
        ))
    return docs


def load_documentation() -> List[SourceDocument]:
    docs = []
    for line in (RAW / "documentation.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        docs.append(SourceDocument(**{k: d[k] for k in SourceDocument.__dataclass_fields__ if k in d}))
    return docs


def load_release_notes() -> List[SourceDocument]:
    docs = []
    for line in (RAW / "release_notes.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        docs.append(SourceDocument(**{k: d[k] for k in SourceDocument.__dataclass_fields__ if k in d}))
    return docs


def build_corpus() -> List[SourceDocument]:
    return load_past_reports() + load_documentation() + load_release_notes()


# ---------------------------------------------------------------------------
# Example usage for a new incoming report
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    corpus = build_corpus()
    print(f"Corpus size: {len(corpus)} documents")

    retriever = EvidenceRetriever()
    retriever.add_documents(corpus)

    # --- this is the new user report you want to analyse ---
    new_title = "Session state lost after widget interaction in 1.64"
    new_body = (
        "After upgrading to 1.64.0, st.session_state values set inside a callback "
        "disappear on the next rerun. Minimal example:\n\n"
        "```python\nimport streamlit as st\n"
        "if 'count' not in st.session_state:\n    st.session_state.count = 0\n"
        "st.button('inc', on_click=lambda: st.session_state.count += 1)\n"
        "st.write(st.session_state.count)\n```\n"
        "Environment: Python 3.11, Streamlit 1.64.0, Chrome."
    )

    retrieved = retriever.retrieve(f"{new_title}\n{new_body}", top_k=10)
    result: SynthesisResult = synthesize_evidence(new_title, new_body, retrieved)

    # machine-readable output
    out = {
        "report_summary": result.report_summary,
        "known_facts": result.known_facts,
        "documented_explanations": result.documented_explanations,
        "hypotheses": result.hypotheses,
        "conflicting_sources": result.conflicting_sources,
        "remaining_gaps": result.remaining_gaps,
        "recommended_next_action": result.recommended_next_action,
        "generated_at": result.generated_at,
        "evidence_used": [
            {
                "score": e.score,
                "claim_type": e.claim_type,
                "extracted_claim": e.extracted_claim,
                "citation": e.citation,
                "relevance_reason": e.relevance_reason,
                "source_id": e.chunk.source_id,
                "source_type": e.chunk.source_type,
                "url": e.chunk.title,  # or store url_or_path in Chunk
            }
            for e in result.evidence_used
        ],
    }
    (RAW / "evidence_synthesis_result.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("Wrote evidence_synthesis_result.json")
