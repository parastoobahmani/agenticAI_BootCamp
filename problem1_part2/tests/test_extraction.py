import pytest

from problem1_part2.implementation.extraction import Segment, extract_facts, observe
from problem1_part2.implementation.schemas import Case, Comment, FactStatus


def _facts(text: str) -> dict[str, str | None]:
    return {item.facet: item.value for item in observe(Segment("body", text))}


def _case(body: str, comments: list[Comment] = (), author: str | None = "reporter") -> Case:
    return Case(case_id="1", title="App problem", body=body, author=author, comments=list(comments))


@pytest.mark.parametrize(
    ("text", "facet", "value"),
    [
        ("- Streamlit version: 1.31.0\n- Python version: 3.11.4", "streamlit_version", "1.31.0"),
        ("- Streamlit version: 1.31.0\n- Python version: 3.11.4", "python_version", "3.11.4"),
        ("pip freeze shows streamlit==1.28.2", "streamlit_version", "1.28.2"),
        ("Running streamlit 1.40.0rc1 on Python 3.12", "streamlit_version", "1.40.0rc1"),
        ("- Operating System: Windows 11", "operating_system", "windows"),
        ("Ubuntu 22.04 VM", "operating_system", "linux"),
        ("- Browser: Chrome", "browser", "chrome"),
        ("I deployed it to Streamlit Community Cloud", "deployment_target", "community_cloud"),
        ("it runs in docker-compose", "deployment_target", "docker"),
        ("deployed on our company server", "deployment_target", "remote_server"),
        ("we put nginx in front of it", "reverse_proxy", "yes"),
        ("there is no reverse proxy, I hit the port directly", "reverse_proxy", "no"),
        ("I set server.baseUrlPath to myapp", "served_under_subpath", "yes"),
        ("It works fine locally but hangs on the server", "reproduces_locally", "no"),
        ("The same thing also happens locally", "reproduces_locally", "yes"),
        ("WebSocket connection to wss://x/_stcore/stream failed", "websocket_error_in_console", "yes"),
        ("There are no errors in the browser console", "websocket_error_in_console", "no"),
        ("curl localhost:8501/_stcore/health returns ok", "health_endpoint_ok", "yes"),
        ("It works in Firefox", "reproduces_in_other_browser", "no"),
        ("Reinstalling didn't help.", "reinstall_resolves", "no"),
        ("Still stuck even after reinstalling everything", "reinstall_resolves", "no"),
        ("I upgraded streamlit and that fixed it", "upgrade_resolves", "yes"),
        ("ModuleNotFoundError: No module named 'foo'", "error_message", "ModuleNotFoundError: No module named 'foo'"),
        ("```python\nimport streamlit as st\n```", "code_snippet", "present"),
        ("- [x] Yes, this used to work in a previous version.", "regression", "yes"),
        ("It worked fine in 1.40 but not anymore", "regression", "yes"),
        ("The value is gone after I refresh the page", "lost_after_page_reload", "yes"),
        ("It resets on normal clicks, without reloading", "lost_after_page_reload", "no"),
        ("The selectbox has no key", "widget_has_key", "no"),
        ("st.selectbox('A', opts, key='choice')", "widget_has_key", "yes"),
        ("options come in a different order on each rerun", "options_change_between_reruns", "yes"),
        ("The value is set in an on_change callback", "uses_callback", "yes"),
        ("I call st.switch_page after saving", "multipage_app", "yes"),
        ("The widget lives in a fragment with run_every", "inside_fragment", "yes"),
        ("The input is inside a dialog", "inside_dialog", "yes"),
        ("The slider is inside a form", "inside_form", "yes"),
        ("then st.rerun() is called", "calls_st_rerun", "yes"),
    ],
)
def test_rule_extracts_explicit_statements(text, facet, value):
    assert _facts(text).get(facet) == value


@pytest.mark.parametrize(
    ("text", "facet"),
    [
        ("I put the widgets in st.container()", "deployment_target"),
        ("ArrowInvalid raised by Apache Arrow", "reverse_proxy"),
        ("[Open in Streamlit Cloud](https://issues.streamlitapp.com)", "deployment_target"),
        ("It doesn't work locally either", "reproduces_locally"),  # must not read as "works locally"
        ("Which version should I use?", "streamlit_version"),
        ("this is a cutting edge feature", "browser"),
        ("- [ ] Yes, this used to work in a previous version.", "regression"),  # unticked box
        ("After upgrading to 1.64.0, values disappear", "upgrade_resolves"),
        ("<!-- e.g. Chrome, Firefox -->", "browser"),
    ],
)
def test_rule_does_not_guess(text, facet):
    assert _facts(text).get(facet) in (None, "yes" if facet == "reproduces_locally" else None)


def test_check_mentioned_without_result_is_marked_performed():
    observations = observe(Segment("body", "I already tried a different browser."))
    [fact] = [item for item in observations if item.facet == "reproduces_in_other_browser"]
    assert fact.status is FactStatus.PERFORMED_OUTCOME_UNKNOWN
    assert fact.value is None


def test_document_example_in_english():
    case = _case(
        "The app opens on my own machine, but on the server it stays on the loading screen. "
        "Reinstalling did not help."
    )
    facts = {item.facet: item.value for item in extract_facts(case)}
    assert facts == {
        "reproduces_locally": "no",
        "deployment_target": "remote_server",
        "reinstall_resolves": "no",
    }


def test_document_example_in_persian():
    case = _case("برنامه روی سیستم خودم باز می‌شود، اما روی سرور در صفحهٔ بارگذاری می‌ماند. نصب دوباره هم کمکی نکرد.")
    facts = {item.facet: item.value for item in extract_facts(case)}
    assert facts == {
        "reproduces_locally": "no",
        "deployment_target": "remote_server",
        "reinstall_resolves": "no",
    }


def test_later_correction_supersedes_earlier_statement():
    case = _case(
        "I'm on streamlit 1.30.0",
        [Comment(id="c1", body="Sorry, it is actually streamlit 1.25.0 on that server", author="reporter")],
    )
    [version] = [item for item in extract_facts(case) if item.facet == "streamlit_version"]
    assert version.value == "1.25.0"
    assert version.origin.location == "comment:c1"
    assert [old.value for old in version.superseded] == ["1.30.0"]


def test_result_free_mention_does_not_override_known_result():
    case = _case(
        "Reinstalling didn't help.",
        [Comment(id="c1", body="I reinstalled again today.", author="reporter")],
    )
    [fact] = [item for item in extract_facts(case) if item.facet == "reinstall_resolves"]
    assert fact.value == "no"
    assert fact.status is FactStatus.OBSERVED


def test_maintainer_and_third_party_comments_are_ignored():
    case = _case(
        "The app hangs.",
        [
            Comment(id="c1", body="This was fixed in streamlit 1.30.0", author="dev", author_association="MEMBER"),
            Comment(id="c2", body="Same for me with streamlit 1.12.0 on Windows", author="someone_else"),
        ],
    )
    assert extract_facts(case) == []


def test_quote_is_the_matching_sentence_only():
    [fact] = observe(Segment("body", "My app is slow. Reinstalling didn't help. Any idea?"))
    assert fact.origin.quote == "Reinstalling didn't help."


def test_console_checked_without_result_is_marked_performed():
    observations = observe(Segment("body", "I checked the browser console."))
    [fact] = [item for item in observations if item.facet == "websocket_error_in_console"]
    assert fact.status is FactStatus.PERFORMED_OUTCOME_UNKNOWN


def test_pasted_websocket_error_is_kept_as_error_message():
    text = "Console: WebSocket connection to wss://host/_stcore/stream failed"
    assert _facts(text)["error_message"].startswith("WebSocket connection to wss://host/_stcore/stream failed")


def test_features_missing_from_shared_code_are_recorded_as_no():
    code = "```python\nimport streamlit as st\nx = st.multiselect('Items', items)\n```"
    facts = {item.facet: item for item in extract_facts(_case(code))}

    for facet in ("uses_callback", "inside_fragment", "inside_dialog", "inside_form", "calls_st_rerun", "multipage_app"):
        assert facts[facet].value == "no"
    assert facts["widget_has_key"].value == "no"
    assert facts["uses_callback"].origin.quote == "(not used in the code shared in this message)"


def test_code_absence_never_overrides_an_explicit_statement():
    case = _case(
        "I use an on_click callback in the real app.",
        [Comment(id="c1", author="reporter", body="```python\nimport streamlit as st\nst.write('hi')\n```")],
    )
    facts = {item.facet: item for item in extract_facts(case)}
    assert facts["uses_callback"].value == "yes"
    assert facts["uses_callback"].superseded == []


def test_key_absence_needs_a_widget_in_the_code():
    facts = {item.facet for item in extract_facts(_case("```python\nimport streamlit as st\nst.write(1)\n```"))}
    assert "widget_has_key" not in facts


def test_text_without_code_infers_nothing_about_code_features():
    facts = {item.facet for item in extract_facts(_case("My multiselect loses its value."))}
    assert not facts & {"uses_callback", "inside_fragment", "widget_has_key"}
