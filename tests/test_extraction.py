import pytest

from missing_info.extraction import Segment, extract_facts, observe
from missing_info.schemas import Case, Comment, FactStatus


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
