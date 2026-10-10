"""
Part 1: Finding and Synthesizing Evidence
Support-report analysis pipeline (RAG-style)

This script:
1. Ingests documentation, past reports, and release notes
2. Chunks + embeds them
3. Retrieves evidence relevant to a new report
4. Ranks and synthesizes the evidence
5. Produces a structured output that clearly distinguishes:
   - Reported facts
   - Documented explanations
   - Assistant hypotheses
   and always cites sources for technical claims.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Optional heavy dependencies – the script still works in "demo" mode without them
# ---------------------------------------------------------------------------
try:
    import numpy as np
    from sentence_transformers import SentenceTransformer

    HAS_EMBEDDINGS = True
except ImportError:
    HAS_EMBEDDINGS = False

try:
    from rank_bm25 import BM25Okapi

    HAS_BM25 = True
except ImportError:
    HAS_BM25 = False


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class SourceDocument:
    """A single source that can be searched (doc page, past report, release note)."""
    id: str
    source_type: str  # "documentation" | "past_report" | "release_note"
    title: str
    content: str
    url_or_path: str
    version: Optional[str] = None
    date: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Chunk:
    """A searchable chunk of a SourceDocument."""
    chunk_id: str
    source_id: str
    source_type: str
    title: str
    text: str
    section: Optional[str] = None
    version: Optional[str] = None
    start_char: int = 0
    end_char: int = 0
    embedding: Optional[List[float]] = None


@dataclass
class EvidenceItem:
    """A retrieved piece of evidence linked to the report."""
    chunk: Chunk
    score: float
    relevance_reason: str  # why this chunk is relevant to the symptoms
    claim_type: str  # "fact" | "documented_explanation" | "hypothesis"
    extracted_claim: str  # short claim extracted from the chunk
    citation: str  # human-readable citation string


@dataclass
class SynthesisResult:
    """Final structured output of Part 1."""
    report_summary: str
    known_facts: List[Dict[str, str]]  # {claim, citation}
    documented_explanations: List[Dict[str, str]]  # {claim, citation}
    hypotheses: List[Dict[str, str]]  # {claim, reasoning, citation_or_none}
    conflicting_sources: List[Dict[str, str]]  # description of conflicts
    evidence_used: List[EvidenceItem]
    remaining_gaps: List[str]
    recommended_next_action: str
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def simple_chunk(
        doc: SourceDocument,
        max_chars: int = 800,
        overlap: int = 100,
) -> List[Chunk]:
    """
    Character-based chunking that tries to respect paragraph boundaries.
    In production you would replace this with a more sophisticated
    structure-aware chunker (Markdown headings, code blocks, etc.).
    """
    text = doc.content.strip()
    if not text:
        return []

    # Prefer splitting on double newlines (paragraphs)
    paragraphs = re.split(r"\n\s*\n", text)
    chunks: List[Chunk] = []
    current = ""
    start = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(current) + len(para) + 2 <= max_chars:
            current = (current + "\n\n" + para).strip()
        else:
            if current:
                end = start + len(current)
                chunk_id = hashlib.sha1(f"{doc.id}:{start}:{end}".encode()).hexdigest()[:12]
                chunks.append(
                    Chunk(
                        chunk_id=chunk_id,
                        source_id=doc.id,
                        source_type=doc.source_type,
                        title=doc.title,
                        text=current,
                        version=doc.version,
                        start_char=start,
                        end_char=end,
                    )
                )
                # overlap
                overlap_text = current[-overlap:] if overlap and len(current) > overlap else ""
                start = end - len(overlap_text)
                current = (overlap_text + "\n\n" + para).strip()
            else:
                # single paragraph longer than max_chars → hard split
                for i in range(0, len(para), max_chars - overlap):
                    piece = para[i: i + max_chars]
                    end = start + len(piece)
                    chunk_id = hashlib.sha1(f"{doc.id}:{start}:{end}".encode()).hexdigest()[:12]
                    chunks.append(
                        Chunk(
                            chunk_id=chunk_id,
                            source_id=doc.id,
                            source_type=doc.source_type,
                            title=doc.title,
                            text=piece,
                            version=doc.version,
                            start_char=start,
                            end_char=end,
                        )
                    )
                    start = end - overlap if overlap else end
                current = ""
                continue

    if current:
        end = start + len(current)
        chunk_id = hashlib.sha1(f"{doc.id}:{start}:{end}".encode()).hexdigest()[:12]
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                source_id=doc.id,
                source_type=doc.source_type,
                title=doc.title,
                text=current,
                version=doc.version,
                start_char=start,
                end_char=end,
            )
        )
    return chunks


# ---------------------------------------------------------------------------
# Embedding & retrieval
# ---------------------------------------------------------------------------

class EvidenceRetriever:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.chunks: List[Chunk] = []
        self.model = None
        self.embeddings: Optional[np.ndarray] = None
        self.bm25 = None

        if HAS_EMBEDDINGS:
            self.model = SentenceTransformer(model_name)

    def add_documents(self, documents: List[SourceDocument], max_chars: int = 800):
        for doc in documents:
            self.chunks.extend(simple_chunk(doc, max_chars=max_chars))

        if not self.chunks:
            return

        if HAS_EMBEDDINGS and self.model is not None:
            texts = [c.text for c in self.chunks]
            embs = self.model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
            self.embeddings = embs
            for c, e in zip(self.chunks, embs):
                c.embedding = e.tolist()

        if HAS_BM25:
            tokenized = [c.text.lower().split() for c in self.chunks]
            self.bm25 = BM25Okapi(tokenized)

    def _cosine_sim(self, a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))

    def retrieve(
            self,
            query: str,
            top_k: int = 8,
            hybrid_alpha: float = 0.6,  # weight for dense vs sparse
    ) -> List[Tuple[Chunk, float]]:
        """
        Hybrid retrieval: dense (embeddings) + sparse (BM25).
        Falls back gracefully when libraries are missing.
        """
        if not self.chunks:
            return []

        scores = np.zeros(len(self.chunks))

        # Dense
        if HAS_EMBEDDINGS and self.model is not None and self.embeddings is not None:
            q_emb = self.model.encode([query], convert_to_numpy=True)[0]
            dense_scores = np.array([self._cosine_sim(q_emb, e) for e in self.embeddings])
            # normalize to [0,1]
            if dense_scores.max() > dense_scores.min():
                dense_scores = (dense_scores - dense_scores.min()) / (dense_scores.max() - dense_scores.min())
            scores += hybrid_alpha * dense_scores

        # Sparse
        if HAS_BM25 and self.bm25 is not None:
            tokenized_query = query.lower().split()
            sparse_scores = np.array(self.bm25.get_scores(tokenized_query))
            if sparse_scores.max() > 0:
                sparse_scores = sparse_scores / sparse_scores.max()
            scores += (1 - hybrid_alpha) * sparse_scores
        elif not HAS_EMBEDDINGS:
            # pure keyword fallback
            q_terms = set(query.lower().split())
            for i, c in enumerate(self.chunks):
                c_terms = set(c.text.lower().split())
                scores[i] = len(q_terms & c_terms) / (len(q_terms) + 1e-6)

        ranked_idx = np.argsort(scores)[::-1][:top_k]
        return [(self.chunks[i], float(scores[i])) for i in ranked_idx if scores[i] > 0]


# ---------------------------------------------------------------------------
# Claim extraction & classification helpers (lightweight heuristics)
# ---------------------------------------------------------------------------

FACT_PATTERNS = [
    r"\b(error|exception|crash|fails?|returns?|throws?)\b",
    r"\b(version|build|commit|release)\b.*\b(\d+\.\d+|\d{4}-\d{2}-\d{2})\b",
    r"\b(fixed in|resolved in|introduced in)\b",
]

EXPLANATION_PATTERNS = [
    r"\b(because|due to|caused by|root cause|limitation|known issue)\b",
    r"\b(this happens when|occurs if|only when)\b",
]


def classify_claim(text: str) -> str:
    lower = text.lower()
    for p in EXPLANATION_PATTERNS:
        if re.search(p, lower):
            return "documented_explanation"
    for p in FACT_PATTERNS:
        if re.search(p, lower):
            return "fact"
    return "hypothesis"  # default for weaker matches


def extract_short_claim(text: str, max_len: int = 180) -> str:
    # Take the first sentence or first max_len chars
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    claim = sentences[0] if sentences else text
    if len(claim) > max_len:
        claim = claim[: max_len - 3] + "..."
    return claim.strip()


def make_citation(chunk: Chunk) -> str:
    parts = [f"[{chunk.source_type}] {chunk.title}"]
    if chunk.version:
        parts.append(f"v{chunk.version}")
    if chunk.section:
        parts.append(f"§ {chunk.section}")
    parts.append(f"(chunk {chunk.chunk_id})")
    return " – ".join(parts)


# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------

def synthesize_evidence(
        report_title: str,
        report_body: str,
        retrieved: List[Tuple[Chunk, float]],
        conversation_history: Optional[List[str]] = None,
) -> SynthesisResult:
    """
    Turn ranked chunks into a structured, citation-aware synthesis.
    """
    evidence_items: List[EvidenceItem] = []
    known_facts: List[Dict[str, str]] = []
    documented: List[Dict[str, str]] = []
    hypotheses: List[Dict[str, str]] = []
    conflicts: List[Dict[str, str]] = []

    report_text = f"{report_title}\n\n{report_body}"
    if conversation_history:
        report_text += "\n\nConversation:\n" + "\n".join(conversation_history)

    # Build evidence items
    for chunk, score in retrieved:
        claim = extract_short_claim(chunk.text)
        claim_type = classify_claim(chunk.text)
        reason = (
            f"Matches symptoms/environment in the report "
            f"(score={score:.3f}). Source type: {chunk.source_type}."
        )
        item = EvidenceItem(
            chunk=chunk,
            score=score,
            relevance_reason=reason,
            claim_type=claim_type,
            extracted_claim=claim,
            citation=make_citation(chunk),
        )
        evidence_items.append(item)

        entry = {"claim": claim, "citation": item.citation}
        if claim_type == "fact":
            known_facts.append(entry)
        elif claim_type == "documented_explanation":
            documented.append(entry)
        else:
            hypotheses.append({
                "claim": claim,
                "reasoning": "Inferred from source similarity; not an explicit documented statement.",
                "citation": item.citation,
            })

    # Very lightweight conflict detection (same topic, opposing polarity)
    # In production this would use an LLM or a contradiction model.
    polarity_words = {
        "positive": ["fixed", "resolved", "works", "supported", "available"],
        "negative": ["broken", "fails", "unsupported", "limitation", "not supported", "regression"],
    }
    for i, a in enumerate(evidence_items):
        for b in evidence_items[i + 1:]:
            a_lower = a.extracted_claim.lower()
            b_lower = b.extracted_claim.lower()
            a_pos = any(w in a_lower for w in polarity_words["positive"])
            a_neg = any(w in a_lower for w in polarity_words["negative"])
            b_pos = any(w in b_lower for w in polarity_words["positive"])
            b_neg = any(w in b_lower for w in polarity_words["negative"])
            if (a_pos and b_neg) or (a_neg and b_pos):
                conflicts.append({
                    "description": (
                        f"Possible conflict between:\n"
                        f"  • {a.citation}: “{a.extracted_claim}”\n"
                        f"  • {b.citation}: “{b.extracted_claim}”\n"
                        f"Prioritize the more recent release note or the official documentation "
                        f"when versions differ; otherwise flag as unresolved ambiguity."
                    )
                })

    # Remaining gaps (heuristic)
    gaps = []
    if not any(e.chunk.source_type == "release_note" for e in evidence_items):
        gaps.append("No matching release note found – version that introduced/fixed the issue is unknown.")
    if not any(e.chunk.source_type == "past_report" for e in evidence_items):
        gaps.append("No similar past reports retrieved – frequency and workarounds are unclear.")
    if "version" not in report_text.lower() and "v" not in report_title.lower():
        gaps.append("User did not specify the exact product version or environment.")

    # Recommended next action
    if gaps:
        next_action = (
            "Ask the user for the exact product version, OS, and a minimal reproducible example. "
            "Also check the latest release notes for any related changelog entries."
        )
    elif conflicts:
        next_action = (
            "Resolve the conflicting sources (prefer official docs / newest release notes) "
            "before proposing a fix or workaround to the user."
        )
    else:
        next_action = (
            "Present the most relevant documented explanation and, if a fix exists, "
            "point the user to the version that contains it."
        )

    return SynthesisResult(
        report_summary=f"Title: {report_title}\nBody excerpt: {report_body[:300]}...",
        known_facts=known_facts,
        documented_explanations=documented,
        hypotheses=hypotheses,
        conflicting_sources=conflicts,
        evidence_used=evidence_items,
        remaining_gaps=gaps,
        recommended_next_action=next_action,
    )


# ---------------------------------------------------------------------------
# Demo data & main entry point
# ---------------------------------------------------------------------------

def build_demo_corpus() -> List[SourceDocument]:
    """Small synthetic corpus so the script can be run immediately."""
    return [
        SourceDocument(
            id="doc-001",
            source_type="documentation",
            title="API Rate Limits",
            content=(
                "The public API enforces a rate limit of 100 requests per minute per API key.\n\n"
                "When the limit is exceeded the server returns HTTP 429 Too Many Requests.\n\n"
                "Clients should implement exponential backoff. This limitation has existed since v2.0."
            ),
            url_or_path="docs/api/rate-limits.md",
            version="2.4",
        ),
        SourceDocument(
            id="doc-002",
            source_type="documentation",
            title="Authentication Errors",
            content=(
                "A 401 Unauthorized response is returned when the API key is missing or invalid.\n\n"
                "A 403 Forbidden response indicates the key is valid but lacks the required scope."
            ),
            url_or_path="docs/api/auth.md",
            version="2.4",
        ),
        SourceDocument(
            id="rel-003",
            source_type="release_note",
            title="Release 2.5.0",
            content=(
                "Fixed a regression where rate-limit headers were missing from 429 responses "
                "(introduced in 2.4.1). Clients can now correctly read X-RateLimit-Remaining.\n\n"
                "Also improved error messages for expired API keys."
            ),
            url_or_path="changelog/2.5.0.md",
            version="2.5.0",
            date="2025-11-12",
        ),
        SourceDocument(
            id="rep-004",
            source_type="past_report",
            title="Frequent 429 errors after upgrading to 2.4.1",
            content=(
                "User reports: After upgrading from 2.3 to 2.4.1 we suddenly receive many 429 responses "
                "even though our traffic did not increase. The response body is empty and no rate-limit "
                "headers are present. Workaround: pin to 2.3.2."
            ),
            url_or_path="issues/4821",
            version="2.4.1",
            date="2025-10-03",
        ),
        SourceDocument(
            id="rel-005",
            source_type="release_note",
            title="Release 2.4.1",
            content=(
                "Internal refactoring of the rate-limiter. No user-facing changes expected. "
                "Known issue: rate-limit headers may be omitted on some 429 responses."
            ),
            url_or_path="changelog/2.4.1.md",
            version="2.4.1",
            date="2025-09-28",
        ),
    ]


def main():
    # ------------------------------------------------------------------
    # 1. Build / load the knowledge base
    # ------------------------------------------------------------------
    corpus = build_demo_corpus()
    retriever = EvidenceRetriever()
    retriever.add_documents(corpus)

    # ------------------------------------------------------------------
    # 2. New incoming report (this would come from the ticketing system)
    # ------------------------------------------------------------------
    new_report_title = "Getting 429 errors with empty body after upgrade"
    new_report_body = (
        "We upgraded from 2.3.2 to 2.4.1 last week. Since then our integration receives "
        "HTTP 429 responses with an empty body and no rate-limit headers. "
        "Traffic volume is unchanged. Is this a known issue?"
    )
    conversation = [
        "Support: Which exact version are you running now?",
        "User: 2.4.1 (confirmed via /version endpoint).",
    ]

    # ------------------------------------------------------------------
    # 3. Retrieve evidence
    # ------------------------------------------------------------------
    query = f"{new_report_title}\n{new_report_body}"
    retrieved = retriever.retrieve(query, top_k=6)

    # ------------------------------------------------------------------
    # 4. Synthesize
    # ------------------------------------------------------------------
    result = synthesize_evidence(
        report_title=new_report_title,
        report_body=new_report_body,
        retrieved=retrieved,
        conversation_history=conversation,
    )

    # ------------------------------------------------------------------
    # 5. Pretty-print (in production you would return JSON or a structured card)
    # ------------------------------------------------------------------
    print("=" * 80)
    print("PART 1 – EVIDENCE SYNTHESIS RESULT")
    print("=" * 80)
    print("\n📋 Report summary")
    print(result.report_summary)

    print("\n✅ Known facts (with citations)")
    for f in result.known_facts:
        print(f"  • {f['claim']}")
        print(f"    ↳ {f['citation']}")

    print("\n📖 Documented explanations (with citations)")
    for e in result.documented_explanations:
        print(f"  • {e['claim']}")
        print(f"    ↳ {e['citation']}")

    print("\n🔍 Hypotheses (assistant inferences)")
    for h in result.hypotheses:
        print(f"  • {h['claim']}")
        print(f"    Reasoning: {h['reasoning']}")
        print(f"    ↳ {h['citation']}")

    if result.conflicting_sources:
        print("\n⚠️  Conflicting sources")
        for c in result.conflicting_sources:
            print(f"  • {c['description']}")

    print("\n❓ Remaining gaps")
    for g in result.remaining_gaps:
        print(f"  • {g}")

    print("\n➡️  Recommended next action")
    print(f"  {result.recommended_next_action}")

    print("\n" + "=" * 80)
    print("Raw evidence items (for debugging / maintainer view)")
    print("=" * 80)
    for item in result.evidence_used:
        print(f"[{item.score:.3f}] {item.citation}")
        print(f"    Claim ({item.claim_type}): {item.extracted_claim}")
        print(f"    Why relevant: {item.relevance_reason}")
        print()

    # Optional: dump machine-readable JSON
    out_path = Path("evidence_synthesis_result.json")
    # Convert dataclasses to dicts (EvidenceItem contains a Chunk)
    serializable = {
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
                "chunk_id": e.chunk.chunk_id,
            }
            for e in result.evidence_used
        ],
    }
    out_path.write_text(json.dumps(serializable, indent=2))
    print(f"\nJSON result written to {out_path.resolve()}")


if __name__ == "__main__":
    main()
