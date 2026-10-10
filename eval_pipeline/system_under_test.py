"""Thin wrapper around the evidence pipeline. Replace `reply` with your real assistant."""
from __future__ import annotations

import time
from typing import Any, Dict, List

from evidence_core import EvidenceRetriever, SourceDocument, synthesize_evidence


class SupportAssistant:
    """System under test. Tracks simple interceptor state for operational checks."""

    def __init__(self):
        self.state = {
            "status": "open",
            "waiting_for_user": False,
            "escalated": False,
            "last_action": "",
        }
        self.last_token_estimate = 0
        self.last_latency_sec = 0.0

    def reply(
        self,
        conversation: List[Dict[str, str]],
        corpus: List[SourceDocument],
    ) -> Dict[str, Any]:
        t0 = time.perf_counter()
        user_turns = [m["content"] for m in conversation if m["role"] == "user"]
        title = user_turns[0].split("\n")[0][:120] if user_turns else "untitled"
        body = "\n".join(user_turns)

        retriever = EvidenceRetriever()
        retriever.add_documents(corpus)
        retrieved = retriever.retrieve(body, top_k=10)
        result = synthesize_evidence(title, body, retrieved, user_turns[1:] or None)

        # Simple policy → state transitions
        action = "answer"
        text_parts = []
        if result.remaining_gaps and not self.state["waiting_for_user"]:
            action = "ask_clarification"
            self.state["waiting_for_user"] = True
            text_parts.append(result.recommended_next_action)
        elif result.conflicting_sources:
            action = "escalate"
            self.state["escalated"] = True
            self.state["status"] = "escalated"
            text_parts.append("Escalating to maintainers with evidence summary.")
        else:
            action = "answer"
            self.state["waiting_for_user"] = False
            if result.documented_explanations:
                text_parts.append(result.documented_explanations[0]["claim"])
                text_parts.append("Source: " + result.documented_explanations[0]["citation"])
            elif result.known_facts:
                text_parts.append(result.known_facts[0]["claim"])
                text_parts.append("Source: " + result.known_facts[0]["citation"])
            else:
                text_parts.append(result.recommended_next_action)

        self.state["last_action"] = action
        response_text = "\n".join(text_parts)

        self.last_latency_sec = time.perf_counter() - t0
        # rough token estimate
        self.last_token_estimate = (len(body) + len(response_text)) // 4

        return {
            "text": response_text,
            "action": action,
            "result": result,
            "state": dict(self.state),
            "latency_sec": self.last_latency_sec,
            "token_estimate": self.last_token_estimate,
            "retrieved_chunk_ids": result.retrieved_chunk_ids,
        }