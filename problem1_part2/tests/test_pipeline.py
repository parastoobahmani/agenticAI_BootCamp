import json
from pathlib import Path

import pytest

from problem1_part2.implementation import AnalysisInput, AnalyzerConfig, analyze
from problem1_part2.implementation.schemas import DecisionType, ProbeBasis, ProbeKind
from problem1_part2.implementation.scoring import UNLISTED_CAUSE

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture
def stuck_loading() -> dict:
    return json.loads((EXAMPLES / "stuck_loading_on_server.json").read_text())


def _run(payload: dict, *comments: str, config: AnalyzerConfig | None = None):
    payload = json.loads(json.dumps(payload))
    payload["case"]["comments"] = [
        {"id": f"c{index}", "author": "reporter", "body": body} for index, body in enumerate(comments, 1)
    ]
    return analyze(AnalysisInput.model_validate(payload), config)


def _hypothesis(report, hypothesis_id):
    return next(item for item in report.hypotheses if item.hypothesis_id == hypothesis_id)


def test_first_turn_asks_the_most_discriminating_question(stuck_loading):
    report = _run(stuck_loading)

    assert report.decision.type is DecisionType.REQUEST_INFORMATION
    assert report.next_steps[0].facet == "reverse_proxy"
    assert all(step.basis is ProbeBasis.INFORMATION_GAIN for step in report.next_steps)
    assert len(report.next_steps) <= AnalyzerConfig().max_probes


def test_already_tried_check_is_not_repeated(stuck_loading):
    report = _run(stuck_loading)

    assert "reinstall_resolves" not in {step.facet for step in report.next_steps}
    assert "reinstall_resolves" in {item.facet for item in report.skipped_probes}
    assert "reproduces_locally" not in {step.facet for step in report.next_steps}


def test_known_facts_weaken_contradicted_hypothesis(stuck_loading):
    report = _run(stuck_loading)
    broken_env = _hypothesis(report, "h_broken_env")

    assert broken_env.posterior < broken_env.prior
    assert "reinstall_resolves=no" in broken_env.conflicting_facts
    assert any("h_broken_env conflicts" in note for note in report.limitations)


def test_check_done_without_result_becomes_follow_up(stuck_loading):
    report = _run(stuck_loading, "Yes, nginx is in front of it. I checked the browser console.")

    follow_up = report.next_steps[0]
    assert follow_up.facet == "websocket_error_in_console"
    assert follow_up.kind is ProbeKind.FOLLOW_UP
    assert "I checked the browser console." in follow_up.text


def test_confirming_answers_lead_to_proposed_answer(stuck_loading):
    report = _run(
        stuck_loading,
        "Yes, nginx is in front of it.",
        "The console says: WebSocket connection to wss://example.com/_stcore/stream failed.",
    )

    assert report.decision.type is DecisionType.PROPOSE_ANSWER
    assert report.decision.hypothesis_id == "h_proxy_websocket"
    assert report.hypotheses[0].hypothesis_id == "h_proxy_websocket"


def test_ruling_out_the_leader_moves_the_questions(stuck_loading):
    report = _run(stuck_loading, "There is no reverse proxy, I open the port directly.")

    assert report.hypotheses[0].hypothesis_id != "h_proxy_websocket"
    assert report.decision.type is DecisionType.REQUEST_INFORMATION
    assert "reverse_proxy" not in {step.facet for step in report.next_steps}


def test_user_correction_is_reported(stuck_loading):
    report = _run(stuck_loading, "We use nginx.", "Correction: there is no reverse proxy at all.")

    [fact] = [item for item in report.known_facts if item.facet == "reverse_proxy"]
    assert fact.value == "no"
    assert any("corrected reverse_proxy" in note for note in report.limitations)


def test_without_hypotheses_escalates_and_asks_only_missing_basics():
    payload = {
        "case": {
            "case_id": "x",
            "title": "Weird behaviour",
            "body": "Streamlit version: 1.38.0. Something is off with my app.",
        }
    }
    report = analyze(AnalysisInput.model_validate(payload))

    assert report.decision.type is DecisionType.ESCALATE
    assert [item.hypothesis_id for item in report.hypotheses] == [UNLISTED_CAUSE]
    assert report.next_steps, "the output must say how to continue"
    assert all(step.basis is ProbeBasis.FALLBACK for step in report.next_steps)
    assert "streamlit_version" not in {step.facet for step in report.next_steps}
    assert "No candidate explanation was found in the evidence base." in report.limitations


def _version_bug_payload(body: str) -> dict:
    return {
        "case": {"case_id": "v", "title": "data_editor loses edits", "body": body},
        "evidence_bundle": {
            "evidence": [
                {
                    "evidence_id": "rn:1.33.0",
                    "source_type": "release_note",
                    "title": "Version 1.33.0",
                    "url": "https://docs.streamlit.io/develop/quick-reference/release-notes",
                    "snippet": "Bug fix: st.data_editor keeps edits after a rerun.",
                    "relevance": 0.8,
                    "fixed_in_version": "1.33.0",
                }
            ],
            "hypotheses": [
                {
                    "hypothesis_id": "h_known_bug",
                    "statement": "Known st.data_editor bug.",
                    "confidence": 0.6,
                    "evidence_ids": ["rn:1.33.0"],
                },
                {"hypothesis_id": "h_usage", "statement": "Widget key changes between reruns.", "confidence": 0.4},
            ],
        },
    }


def test_unknown_version_is_asked_when_a_fix_version_is_known():
    report = analyze(AnalysisInput.model_validate(_version_bug_payload("Edits disappear after I click a button.")))

    assert report.next_steps[0].facet == "streamlit_version"
    assert "<1.33.0" in report.next_steps[0].rationale


def test_version_after_the_fix_rules_out_the_known_bug():
    report = analyze(
        AnalysisInput.model_validate(_version_bug_payload("Edits disappear. Streamlit version: 1.35.0"))
    )
    known_bug = _hypothesis(report, "h_known_bug")

    assert known_bug.posterior < known_bug.prior
    assert "streamlit_version=1.35.0" in known_bug.conflicting_facts


def test_similar_reports_alone_never_yield_an_answer():
    payload = {
        "case": {"case_id": "w", "title": "Cache issue", "body": "Clearing the cache fixed it once."},
        "evidence_bundle": {
            "evidence": [
                {
                    "evidence_id": "issue:1",
                    "source_type": "issue",
                    "title": "Stale cache",
                    "url": "https://github.com/streamlit/streamlit/issues",
                    "snippet": "Same here",
                    "relevance": 0.9,
                    "claim_kind": "reported_fact",
                    "author_association": "NONE",
                }
            ],
            "hypotheses": [
                {"hypothesis_id": "h_cache", "statement": "Stale st.cache_data entry.", "confidence": 1.0, "evidence_ids": ["issue:1"]}
            ],
        },
    }
    report = analyze(AnalysisInput.model_validate(payload), AnalyzerConfig(answer_threshold=0.5, answer_margin=0.1))

    assert report.hypotheses[0].hypothesis_id == "h_cache"
    assert report.decision.type is not DecisionType.PROPOSE_ANSWER
    assert any("rests only on similar reports" in note for note in report.limitations)


def test_report_round_trips_through_json(stuck_loading):
    report = _run(stuck_loading)
    assert type(report).model_validate_json(report.model_dump_json()) == report


def _example(name: str):
    return analyze(AnalysisInput.model_validate_json((EXAMPLES / f"{name}.json").read_text()))


def test_widget_reset_asks_what_separates_identity_from_new_session():
    report = _example("multiselect_selection_reset")

    assert report.decision.type is DecisionType.REQUEST_INFORMATION
    assert [step.facet for step in report.next_steps] == ["lost_after_page_reload", "options_change_between_reruns"]
    # The shared code has no key, which contradicts the keyed-widget cleanup explanation.
    cleanup = _hypothesis(report, "h_widget_cleanup")
    assert "widget_has_key=no" in cleanup.conflicting_facts
    assert cleanup.posterior < cleanup.prior
    assert "widget_has_key" not in {step.facet for step in report.next_steps}


def test_widget_reset_answers_lead_to_identity_explanation():
    report = _example("multiselect_selection_reset_after_answer")

    assert report.decision.type is DecisionType.PROPOSE_ANSWER
    assert report.decision.hypothesis_id == "h_widget_identity"
