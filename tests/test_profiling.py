from missing_info.profiling import RuleBasedProfiler, profile_hypothesis, version_expectations
from missing_info.schemas import Evidence, Expectation, Hypothesis, SourceType


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
    profiled = profile_hypothesis(hypothesis, [], RuleBasedProfiler())

    assert profiled.expectations["reverse_proxy"].values == ["no"]
    assert "websocket_error_in_console" in profiled.expectations
    assert "not_a_facet" not in profiled.expectations
    assert "browser" not in profiled.expectations
    assert profiled.source == "bundle+rules"
    assert len(profiled.warnings) == 2


def test_source_is_none_without_any_expectation():
    profiled = profile_hypothesis(_hypothesis("Something unexpected happens"), [], RuleBasedProfiler())
    assert profiled.source == "none"
    assert profiled.expectations == {}
