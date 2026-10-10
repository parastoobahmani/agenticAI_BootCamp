import json

import pytest

from missing_info.llm import CachedChatClient, LLMProfiler, UsageStats, parse_expectations
from missing_info.profiling import RuleBasedProfiler, profile_hypothesis
from missing_info.schemas import Hypothesis


class _FakeClient:
    def __init__(self, reply: str | Exception):
        self.reply = reply
        self.calls = 0
        self.usage = UsageStats()

    def complete(self, system: str, user: str) -> str:
        self.calls += 1
        self.usage.requests += 1
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


HYPOTHESIS = Hypothesis(hypothesis_id="h1", statement="Server sits behind a misconfigured gateway", confidence=0.5)


def test_parse_expectations_keeps_valid_entries_only():
    reply = json.dumps(
        {"expectations": {"reverse_proxy": {"values": ["yes"]}, "streamlit_version": {"version_spec": "nope"}}}
    )
    assert set(parse_expectations(reply)) == {"reverse_proxy"}


@pytest.mark.parametrize("reply", ["not json", "[]", '{"something": 1}'])
def test_parse_expectations_rejects_malformed_replies(reply):
    with pytest.raises(ValueError):
        parse_expectations(reply)


def test_llm_profiler_uses_model_reply():
    client = _FakeClient(json.dumps({"expectations": {"reverse_proxy": {"values": ["yes"]}}}))
    profiled = profile_hypothesis(HYPOTHESIS, [], [LLMProfiler(client), RuleBasedProfiler()])

    assert profiled.expectations["reverse_proxy"].values == ["yes"]
    assert profiled.source == "llm"


def test_llm_failure_falls_back_to_next_profiler():
    profiler = LLMProfiler(_FakeClient(TimeoutError("slow")))
    hypothesis = Hypothesis(hypothesis_id="h1", statement="nginx drops the WebSocket upgrade", confidence=0.5)

    profiled = profile_hypothesis(hypothesis, [], [profiler, RuleBasedProfiler()])

    assert profiled.source == "rules"
    assert profiler.errors and "TimeoutError" in profiler.errors[0]


def test_prompt_lists_catalogue_and_hypothesis():
    prompt = LLMProfiler(_FakeClient("{}")).build_prompt(HYPOTHESIS, [])
    assert "reverse_proxy (values: yes | no)" in prompt
    assert "streamlit_version (version_spec)" in prompt
    assert HYPOTHESIS.statement in prompt
    assert "error_message" not in prompt  # free-text facets cannot be predicted


def test_cache_records_then_replays_without_calling(tmp_path):
    path = tmp_path / "cache.json"
    live = _FakeClient('{"expectations": {}}')

    assert CachedChatClient(path, live).complete("s", "u") == '{"expectations": {}}'
    replay = CachedChatClient(path)  # no live client at all
    assert replay.complete("s", "u") == '{"expectations": {}}'
    assert live.calls == 1
    assert replay.usage.cache_hits == 1


def test_replay_only_cache_misses_raise(tmp_path):
    with pytest.raises(LookupError):
        CachedChatClient(tmp_path / "missing.json").complete("s", "u")
