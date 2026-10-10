from __future__ import annotations

import json
import re
from pathlib import Path

from .config import EVIDENCE_PATH

_TOKEN = re.compile(r"[a-z0-9_.\-]+")


def tokens(text: str) -> list[str]:
    return _TOKEN.findall((text or "").lower())


class EvidenceStore:
    def __init__(self, path=EVIDENCE_PATH) -> None:
        self.path = Path(path)
        self.documents = self._load()

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8"))

    def reload(self) -> None:
        self.documents = self._load()

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        query_tokens = tokens(query)
        if not query_tokens:
            return []
        scored = []
        for document in self.documents:
            haystack = " ".join(
                [document.get("title", ""), document.get("text", ""), " ".join(document.get("tags", []))]
            )
            document_tokens = tokens(haystack)
            bag = set(document_tokens)
            overlap = [token for token in query_tokens if token in bag]
            if not overlap:
                continue
            hits = sum(document_tokens.count(token) for token in overlap)
            score = len(overlap) + hits / (len(document_tokens) + 1)
            scored.append((score, document))
        scored.sort(key=lambda row: (-row[0], row[1]["doc_id"]))
        return [
            {
                "doc_id": document["doc_id"],
                "kind": document["kind"],
                "ref": document["ref"],
                "title": document["title"],
                "snippet": (document.get("text", "")[:400]).strip(),
                "score": round(score, 4),
            }
            for score, document in scored[:top_k]
        ]
