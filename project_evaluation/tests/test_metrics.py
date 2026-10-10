import pytest

import step3_compute_metrics as metrics


def _log(case_id, action, *, error=None, next_step=None, operational=None):
    return {
        "case_id": case_id,
        "system": "integrated",
        "bucket": "ambiguous",
        "run": {
            "action": action, "text": "", "error": error,
            "retrieved_source_ids": ["issue-9", "doc-a"], "retrieved_chunk_ids": [],
            "latency_sec": 0.1, "setup_sec": 0.0,
            "usage": {"api_requests": 0, "input_tokens": 0, "output_tokens": 0, "estimated_cost_usd": 0.0},
            "next_step": next_step, "operational": operational,
        },
    }


@pytest.fixture(autouse=True)
def annotations(monkeypatch):
    labels = {
        "c1": {"bucket": "ambiguous", "acceptable_actions_turn0": ["ask_clarification"],
               "missing_information": ["streamlit_version"], "relevant_source_ids": ["doc-a"]},
        "c2": {"bucket": "ambiguous", "acceptable_actions_turn0": ["ask_clarification"]},
    }
    monkeypatch.setattr(metrics, "load_annotation", lambda case_id: labels.get(case_id, {}))


def test_unlabelled_recall_is_null_not_zero():
    result = metrics.system_metrics([_log("c2", "ask_clarification")], [])
    assert result["evidence_quality"]["recall@5"] == {"mean": None, "n_labeled": 0}


def test_errors_count_as_wrong_decisions_and_are_reported():
    failures = []
    result = metrics.system_metrics([_log("c1", "ask_clarification"), _log("c2", None, error="ReportError: x")], failures)

    assert result["n_errors"] == 1
    assert result["decision_quality"]["overall_accuracy"] == 0.5
    assert result["decision_quality"]["actions_by_bucket"]["ambiguous"]["error"] == 1
    assert failures[0]["probable_cause"] == "system_error"


def test_next_step_and_operational_metrics():
    log = _log(
        "c1", "ask_clarification",
        next_step={"decision": "request_information", "asked": ["streamlit_version"],
                   "bases": ["information_gain"], "known": ["browser"]},
        operational={"case_persisted": True, "tracker_unchanged": True},
    )
    result = metrics.system_metrics([log], [])

    quality = result["next_step_quality"]
    assert quality["re_asked_known_information"]["rate"] == 0.0
    assert quality["first_step_hits_labelled_missing_information"] == {"rate": 1.0, "n": 1}
    assert result["operational_success"]["all_checks"]["rate"] == 1.0
    assert result["evidence_quality"]["recall@5"]["mean"] == 1.0


@pytest.mark.parametrize(
    ("action", "expected", "cause"),
    [
        ("escalate", ["answer"], "over_escalation"),
        ("ask_clarification", ["answer"], "unnecessary_question"),
        ("answer", ["escalate"], "unsupported_answer"),
    ],
)
def test_probable_cause(action, expected, cause):
    assert metrics.probable_cause(action, expected, None) == cause
