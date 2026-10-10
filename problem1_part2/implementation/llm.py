"""Optional LLM-assisted hypothesis profiling.

The rule-based profiler only understands hypothesis families it has keywords
for. ``LLMProfiler`` asks a model to map *any* hypothesis onto the facet
catalogue. Its output is validated against the catalogue, and on any failure
it contributes nothing, so the next profiler in the list (normally the
rule-based one) takes over.

Cost control (the whole team shares a small API budget):
* one short JSON-mode request per hypothesis, temperature 0, capped output;
* ``OpenAICompatibleClient`` refuses to exceed ``max_requests``;
* ``CachedChatClient`` records responses to a JSON file and replays them, so
  evaluation re-runs and tests make no paid calls.

API keys are read from the environment and never logged or stored.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from problem1_part2.implementation.facets import FACETS, ValueType
from problem1_part2.implementation.schemas import Evidence, Expectation, Hypothesis

DEFAULT_BASE_URL = "https://api.metisai.ir/openai/v1"
DEFAULT_MODEL = "gpt-4o-mini"


class ChatClient(Protocol):
    def complete(self, system: str, user: str) -> str:
        """Return the model's reply (expected to be a JSON object as text)."""


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class UsageStats:
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_hits: int = 0

    def __str__(self) -> str:
        return (
            f"{self.requests} requests, {self.input_tokens} input tokens, "
            f"{self.output_tokens} output tokens, {self.cache_hits} cache hits"
        )


class OpenAICompatibleClient:
    """Chat-completions client for any OpenAI-compatible endpoint (Metis by default)."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        max_requests: int = 50,
        max_output_tokens: int = 400,
        timeout: float = 30.0,
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("install the optional dependency: pip install -e '.[llm]'") from exc
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        self.model = model
        self.max_requests = max_requests
        self.max_output_tokens = max_output_tokens
        self.usage = UsageStats()

    @classmethod
    def from_env(cls, model: str | None = None) -> OpenAICompatibleClient:
        api_key = os.environ.get("METIS_API_KEY")
        if not api_key:
            raise RuntimeError("set METIS_API_KEY to use the LLM profiler")
        return cls(
            api_key=api_key,
            model=model or os.environ.get("MISSING_INFO_MODEL", DEFAULT_MODEL),
            base_url=os.environ.get("METIS_BASE_URL", DEFAULT_BASE_URL),
        )

    def complete(self, system: str, user: str) -> str:
        if self.usage.requests >= self.max_requests:
            raise BudgetExceeded(f"request budget of {self.max_requests} exhausted")
        self.usage.requests += 1
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0,
            max_tokens=self.max_output_tokens,
            response_format={"type": "json_object"},
        )
        if response.usage is not None:
            self.usage.input_tokens += response.usage.prompt_tokens
            self.usage.output_tokens += response.usage.completion_tokens
        return response.choices[0].message.content or ""


class CachedChatClient:
    """Record/replay wrapper. With ``inner=None`` it only replays (no network at all).

    Keys are hashes of the prompts, so keep one cache file per model.
    """

    def __init__(self, path: Path, inner: ChatClient | None = None) -> None:
        self._path = path
        self._inner = inner
        self._entries: dict[str, str] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        self.usage = getattr(inner, "usage", None) or UsageStats()

    def complete(self, system: str, user: str) -> str:
        key = hashlib.sha256(f"{system}\n\n{user}".encode()).hexdigest()
        if key in self._entries:
            self.usage.cache_hits += 1
            return self._entries[key]
        if self._inner is None:
            raise LookupError("response not recorded and no live client configured")
        reply = self._inner.complete(system, user)
        self._entries[key] = reply
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._entries, indent=2, ensure_ascii=False), encoding="utf-8")
        return reply


SYSTEM_PROMPT = """\
You help triage Streamlit support cases. Given ONE candidate explanation of a \
user's problem, state what that explanation predicts about observable facets.

Rules:
- Use only the facet ids and values listed by the user. Category facets take a \
"values" list; version facets take a PEP 440 "version_spec" such as "<1.30.0".
- Include a facet only if the explanation clearly implies its value. Omit it when \
unsure; never guess.
- Reply with a JSON object only: {"expectations": {"<facet_id>": {"values": [...]}}} \
or {"expectations": {"<facet_id>": {"version_spec": "..."}}}. Use {"expectations": {}} \
if nothing is clearly implied."""


def _facet_catalogue() -> str:
    lines = []
    for facet in FACETS:
        if facet.value_type is ValueType.CATEGORY:
            lines.append(f"- {facet.id} (values: {' | '.join(facet.values)}): {facet.description}")
        elif facet.value_type is ValueType.VERSION:
            lines.append(f"- {facet.id} (version_spec): {facet.description}")
    return "\n".join(lines)


def parse_expectations(reply: str) -> dict[str, Expectation]:
    """Parse the model reply; malformed entries are dropped, malformed JSON raises ValueError."""
    payload: Any = json.loads(reply)
    raw = payload.get("expectations") if isinstance(payload, dict) else None
    if not isinstance(raw, dict):
        raise ValueError("reply has no 'expectations' object")
    parsed = {}
    for facet_id, item in raw.items():
        try:
            parsed[str(facet_id)] = Expectation.model_validate(item)
        except ValidationError:
            continue
    return parsed


class LLMProfiler:
    name = "llm"

    def __init__(self, client: ChatClient, max_snippet_chars: int = 400, max_evidence: int = 3) -> None:
        self._client = client
        self._max_snippet_chars = max_snippet_chars
        self._max_evidence = max_evidence
        self.errors: list[str] = []

    @property
    def usage(self) -> UsageStats | None:
        return getattr(self._client, "usage", None)

    def build_prompt(self, hypothesis: Hypothesis, evidence: list[Evidence]) -> str:
        sources = "\n".join(
            f"- [{item.source_type.value}] {item.title}"
            + (f" / {item.section}" if item.section else "")
            + (f" (fixed in {item.fixed_in_version})" if item.fixed_in_version else "")
            + f": {item.snippet[: self._max_snippet_chars]}"
            for item in sorted(evidence, key=lambda item: item.relevance, reverse=True)[: self._max_evidence]
        )
        return (
            f"Facets:\n{_facet_catalogue()}\n\n"
            f"Explanation: {hypothesis.statement}\n\n"
            f"Supporting sources:\n{sources or '- none'}"
        )

    def profile(self, hypothesis: Hypothesis, evidence: list[Evidence]) -> dict[str, Expectation]:
        try:
            return parse_expectations(self._client.complete(SYSTEM_PROMPT, self.build_prompt(hypothesis, evidence)))
        except Exception as exc:  # isolation boundary: an LLM failure must never break the analysis
            self.errors.append(f"{hypothesis.hypothesis_id}: {type(exc).__name__}: {exc}")
            return {}
