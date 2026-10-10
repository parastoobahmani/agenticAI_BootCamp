"""Minimal evidence retrieval + synthesis used by the evaluation harness."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

@dataclass
class SourceDocument:
    id: str
    source_type: str
    title: str
    content: str
    url_or_path: str
    version: Optional[str] = None
    date: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Chunk:
    chunk_id: str
    source_id: str
    source_type: str
    title: str
    text: str
    version: Optional[str] = None
    start_char: int = 0
    end_char: int = 0

@dataclass
class EvidenceItem:
    chunk: Chunk
    score: float
    relevance_reason: str
    claim_type: str
    extracted_claim: str
    citation: str

@dataclass
class SynthesisResult:
    report_summary: str
    known_facts: List[Dict[str, str]]
    documented_explanations: List[Dict[str, str]]
    hypotheses: List[Dict[str, str]]
    conflicting_sources: List[Dict[str, str]]
    evidence_used: List[EvidenceItem]
    remaining_gaps: List[str]
    recommended_next_action: str
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    retrieved_chunk_ids: List[str] = field(default_factory=list)

def simple_chunk(doc: SourceDocument, max_chars: int = 900) -> List[Chunk]:
    text = (doc.content or "").strip()
    if not text:
        return []
    chunks = []
    for i in range(0, len(text), max_chars):
        piece = text[i : i + max_chars]
        cid = hashlib.sha1(f"{doc.id}:{i}".encode()).hexdigest()[:12]
        chunks.append(
            Chunk(
                chunk_id=cid,
                source_id=doc.id,
                source_type=doc.source_type,
                title=doc.title,
                text=piece,
                version=doc.version,
                start_char=i,
                end_char=i + len(piece),
            )
        )
    return chunks

class EvidenceRetriever:
    def __init__(self):
        self.chunks: List[Chunk] = []

    def add_documents(self, documents: List[SourceDocument]):
        self.chunks = []
        for d in documents:
            self.chunks.extend(simple_chunk(d))

    def retrieve(self, query: str, top_k: int = 10) -> List[Tuple[Chunk, float]]:
        q_terms = set(re.findall(r"[a-z0-9_\.]+", query.lower()))
        scored = []
        for c in self.chunks:
            c_terms = set(re.findall(r"[a-z0-9_\.]+", c.text.lower()))
            overlap = len(q_terms & c_terms)
            if overlap == 0:
                continue
            score = overlap / (len(q_terms) + 1e-6)
            scored.append((c, float(score)))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

def _classify(text: str) -> str:
    low = text.lower()
    if any(w in low for w in ("because", "due to", "caused by", "known issue", "limitation")):
        return "documented_explanation"
    if any(w in low for w in ("error", "exception", "fixed in", "version", "returns")):
        return "fact"
    return "hypothesis"

def synthesize_evidence(
    report_title: str,
    report_body: str,
    retrieved: List[Tuple[Chunk, float]],
    conversation_history: Optional[List[str]] = None,
) -> SynthesisResult:
    evidence_items = []
    facts, docs, hyps = [], [], []
    for chunk, score in retrieved:
        claim = chunk.text.strip().split("\n")[0][:180]
        ctype = _classify(chunk.text)
        citation = f"[{chunk.source_type}] {chunk.title} (chunk {chunk.chunk_id})"
        item = EvidenceItem(
            chunk=chunk,
            score=score,
            relevance_reason=f"keyword overlap score={score:.3f}",
            claim_type=ctype,
            extracted_claim=claim,
            citation=citation,
        )
        evidence_items.append(item)
        entry = {"claim": claim, "citation": citation}
        if ctype == "fact":
            facts.append(entry)
        elif ctype == "documented_explanation":
            docs.append(entry)
        else:
            hyps.append({"claim": claim, "reasoning": "inferred", "citation": citation})

    gaps = []
    if not any(e.chunk.source_type == "release_note" for e in evidence_items):
        gaps.append("No matching release note found.")
    if "version" not in (report_title + report_body).lower():
        gaps.append("User did not specify product version.")

    if gaps:
        next_action = "Ask the user for the exact Streamlit version and a minimal reproducible example."
    else:
        next_action = "Present the most relevant documented explanation and cite sources."

    return SynthesisResult(
        report_summary=f"Title: {report_title}\nBody excerpt: {report_body[:300]}...",
        known_facts=facts,
        documented_explanations=docs,
        hypotheses=hyps,
        conflicting_sources=[],
        evidence_used=evidence_items,
        remaining_gaps=gaps,
        recommended_next_action=next_action,
        retrieved_chunk_ids=[e.chunk.chunk_id for e in evidence_items],
    )