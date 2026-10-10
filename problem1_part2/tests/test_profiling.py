import pytest

from problem1_part2.implementation.profiling import RuleBasedProfiler, profile_hypothesis, version_expectations
from problem1_part2.implementation.schemas import Evidence, Expectation, Hypothesis, SourceType


def _hypothesis(statement: str, **fields) -> Hypothesis:
    return Hypothesis(hypothesis_id="h1", statement=statement, confidence=0.5, **fields)


def _release_note(fixed_in: str) -> Evidence:
    return Evidence(
        evidence_id=f"rn-{fixed_in}",
        source_type=SourceType.RELEASE_NOTE,
        title=f"Version {fixed_in}",
        url="https://docs.streamlit.io/develop/quick-reference/release-notes",
        snippet="Bug fix: ...",
        relevance=0.7,
        fixed_in_version=fixed_in,
    )


def test_proxy_hypothesis_predicts_websocket_failure_behind_proxy():
    expectations = RuleBasedProfiler().profile(
        _hypothesis("The nginx reverse proxy does not forward the WebSocket upgrade headers"), []
    )
    assert expectations["reverse_proxy"].values == ["yes"]
    assert expectations["websocket_error_in_console"].values == ["yes"]
    assert expectations["health_endpoint_ok"].values == ["yes"]
    assert expectations["reproduces_locally"].values == ["no"]


def test_fixed_and_introduced_versions_become_a_range():
    expectations = version_expectations(_hypothesis("Regression introduced in 1.28.0, fixed in 1.30.1"), [])
    assert expectations["streamlit_version"].version_spec == ">=1.28.0,<1.30.1"
    assert expectations["upgrade_resolves"].values == ["yes"]


def test_fix_version_falls_back_to_newest_evidence():
    expectations = version_expectations(
        _hypothesis("Known bug in st.data_editor"), [_release_note("1.29.0"), _release_note("1.31.0")]
    )
    assert expectations["streamlit_version"].version_spec == "<1.31.0"


def test_unrelated_hypothesis_has_no_expectations():
    assert RuleBasedProfiler().profile(_hypothesis("Something unexpected happens"), []) == {}


def test_bundle_expectations_take_precedence_and_invalid_ones_are_dropped():
    hypothesis = _hypothesis(
        "WebSocket blocked by the proxy",
        expectations={
            "reverse_proxy": Expectation(values=["no"]),
            "not_a_facet": Expectation(values=["x"]),
            "browser": Expectation(values=["netscape"]),
        },
    )
    profiled = profile_hypothesis(hypothesis, [], [RuleBasedProfiler()])

    assert profiled.expectations["reverse_proxy"].values == ["no"]
    assert "websocket_error_in_console" in profiled.expectations
    assert "not_a_facet" not in profiled.expectations
    assert "browser" not in profiled.expectations
    assert profiled.source == "bundle+rules"
    assert len(profiled.warnings) == 2


def test_source_is_none_without_any_expectation():
    profiled = profile_hypothesis(_hypothesis("Something unexpected happens"), [], [RuleBasedProfiler()])
    assert profiled.source == "none"
    assert profiled.expectations == {}


class _FixedProfiler:
    def __init__(self, name, expectations):
        self.name = name
        self._expectations = expectations

    def profile(self, hypothesis, evidence):
        return self._expectations


def test_profilers_fill_only_open_facets_in_order():
    first = _FixedProfiler("llm", {"reverse_proxy": Expectation(values=["no"])})
    silent = _FixedProfiler("broken", {})
    profiled = profile_hypothesis(
        _hypothesis("WebSocket blocked by the proxy"), [], [first, silent, RuleBasedProfiler()]
    )

    assert profiled.expectations["reverse_proxy"].values == ["no"]
    assert "websocket_error_in_console" in profiled.expectations
    assert profiled.source == "llm+rules"


@pytest.mark.parametrize(
    ("statement", "expected"),
    [
        (
            "The multiselect has no key and its options come in a different order, so it resets.",
            {"widget_has_key": ["no"], "options_change_between_reruns": ["yes"], "lost_after_page_reload": ["no"]},
        ),
        ("A page reload starts a new session, so the value is gone.", {"lost_after_page_reload": ["yes"]}),
        ("The keyed widget is not rendered in some run, so its state is cleaned up.", {"widget_has_key": ["yes"]}),
        ("Widget keys are deleted when you switch_page to another page.", {"multipage_app": ["yes"]}),
        ("The value set in the on_change callback is overwritten.", {"uses_callback": ["yes"]}),
        ("Pending widget changes are lost when interrupted by st.rerun.", {"calls_st_rerun": ["yes"]}),
        ("This is expected behavior, not a bug.", {"regression": ["no"], "upgrade_resolves": ["no"]}),
    ],
)
def test_session_state_and_widget_families(statement, expected):
    expectations = RuleBasedProfiler().profile(_hypothesis(statement), [])
    for facet, values in expected.items():
        assert expectations[facet].values == values


def test_introduced_in_version_implies_regression():
    expectations = version_expectations(_hypothesis("Regression introduced in 1.64.0"), [])
    assert expectations["regression"].values == ["yes"]
