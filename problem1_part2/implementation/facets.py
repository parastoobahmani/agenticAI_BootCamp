"""Catalogue of diagnostic facets.

A facet is one piece of information that can tell candidate explanations apart:
either an attribute the user already knows (Streamlit version, deployment target)
or the outcome of a practical check the user can run (browser console, health
endpoint). Each facet carries the exact question/instruction shown to the user.

To support a new kind of problem, add a facet here, extraction rules for it in
``extraction.py`` and (optionally) profiling rules in ``profiling.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

YES_NO = ("yes", "no")


class FacetKind(str, Enum):
    ATTRIBUTE = "attribute"  # the user knows it; we ask a question
    CHECK = "check"  # the user must run something; we suggest a check


class ValueType(str, Enum):
    CATEGORY = "category"
    VERSION = "version"
    TEXT = "text"  # free text (error message, code); never a discriminator


@dataclass(frozen=True)
class Facet:
    id: str
    kind: FacetKind
    value_type: ValueType
    description: str
    prompt: str
    # Rough effort for the user: 1 = answer from memory, 3 = real work.
    cost: int
    values: tuple[str, ...] = ()
    # >0: worth requesting even when no hypothesis needs it (higher = earlier).
    fallback_priority: int = 0

    def __post_init__(self) -> None:
        if (self.value_type is ValueType.CATEGORY) != bool(self.values):
            raise ValueError(f"facet {self.id!r}: only category facets declare values")
        if self.cost < 1:
            raise ValueError(f"facet {self.id!r}: cost must be >= 1")


FACETS: tuple[Facet, ...] = (
    Facet(
        id="streamlit_version",
        kind=FacetKind.ATTRIBUTE,
        value_type=ValueType.VERSION,
        description="Streamlit version where the problem happens",
        prompt="Which Streamlit version is installed where the problem happens? "
        "(output of `streamlit version` in that environment)",
        cost=1,
        fallback_priority=3,
    ),
    Facet(
        id="python_version",
        kind=FacetKind.ATTRIBUTE,
        value_type=ValueType.VERSION,
        description="Python version where the problem happens",
        prompt="Which Python version runs the app where the problem happens? (`python --version`)",
        cost=1,
        fallback_priority=1,
    ),
    Facet(
        id="operating_system",
        kind=FacetKind.ATTRIBUTE,
        value_type=ValueType.CATEGORY,
        description="Operating system running the Streamlit server",
        prompt="Which operating system runs the Streamlit server (Windows, macOS or Linux)?",
        cost=1,
        values=("windows", "macos", "linux"),
    ),
    Facet(
        id="browser",
        kind=FacetKind.ATTRIBUTE,
        value_type=ValueType.CATEGORY,
        description="Browser used to open the app",
        prompt="Which browser do you open the app in?",
        cost=1,
        values=("chrome", "firefox", "safari", "edge", "other"),
    ),
    Facet(
        id="deployment_target",
        kind=FacetKind.ATTRIBUTE,
        value_type=ValueType.CATEGORY,
        description="Where the failing app runs",
        prompt="Where does the failing app run: your own machine, Streamlit Community Cloud, "
        "a Docker container, Kubernetes, a platform such as Heroku/Cloud Run, or your own server/VM?",
        cost=1,
        values=("local", "community_cloud", "docker", "kubernetes", "paas", "remote_server"),
        fallback_priority=2,
    ),
    Facet(
        id="reverse_proxy",
        kind=FacetKind.ATTRIBUTE,
        value_type=ValueType.CATEGORY,
        description="Whether a reverse proxy / load balancer sits in front of the app",
        prompt="Is the app served through a reverse proxy or load balancer "
        "(for example nginx, Apache, Traefik or a cloud load balancer)?",
        cost=1,
        values=YES_NO,
    ),
    Facet(
        id="served_under_subpath",
        kind=FacetKind.ATTRIBUTE,
        value_type=ValueType.CATEGORY,
        description="Whether the app is served under a URL sub-path",
        prompt="Is the app opened under a URL sub-path (e.g. https://example.com/myapp/) "
        "rather than at the root of the domain?",
        cost=1,
        values=YES_NO,
    ),
    Facet(
        id="reproduces_locally",
        kind=FacetKind.ATTRIBUTE,
        value_type=ValueType.CATEGORY,
        description="Whether the same code shows the problem on the user's own machine",
        prompt="Does the same code, with the same Streamlit version, show the problem "
        "when you run it on your own machine?",
        cost=1,
        values=YES_NO,
    ),
    Facet(
        id="websocket_error_in_console",
        kind=FacetKind.CHECK,
        value_type=ValueType.CATEGORY,
        description="Whether the browser reports a failed WebSocket connection",
        prompt="Open the browser developer tools (Console and Network → WS tabs), reload the "
        "page and check whether the WebSocket connection to `/_stcore/stream` fails or "
        "keeps reconnecting. Please paste any error shown there.",
        cost=2,
        values=YES_NO,
    ),
    Facet(
        id="health_endpoint_ok",
        kind=FacetKind.CHECK,
        value_type=ValueType.CATEGORY,
        description="Whether the Streamlit server answers its health endpoint",
        prompt="On the machine running the app, run `curl -i http://localhost:<port>/_stcore/health` "
        "(default port 8501). Does it answer `200 ok`?",
        cost=2,
        values=YES_NO,
    ),
    Facet(
        id="reproduces_in_other_browser",
        kind=FacetKind.CHECK,
        value_type=ValueType.CATEGORY,
        description="Whether the problem persists in another browser / private window",
        prompt="Does the problem persist in a private window or another browser with extensions disabled?",
        cost=1,
        values=YES_NO,
    ),
    Facet(
        id="upgrade_resolves",
        kind=FacetKind.CHECK,
        value_type=ValueType.CATEGORY,
        description="Whether upgrading Streamlit to the latest release removes the problem",
        prompt="In a fresh virtual environment, upgrade to the latest release "
        "(`pip install -U streamlit`) and retry. Does the problem disappear?",
        cost=2,
        values=YES_NO,
    ),
    Facet(
        id="reinstall_resolves",
        kind=FacetKind.CHECK,
        value_type=ValueType.CATEGORY,
        description="Whether a clean reinstall removes the problem",
        prompt="Recreate the virtual environment and reinstall your requirements from scratch. "
        "Does the problem disappear?",
        cost=2,
        values=YES_NO,
    ),
    Facet(
        id="cache_clear_resolves",
        kind=FacetKind.CHECK,
        value_type=ValueType.CATEGORY,
        description="Whether clearing Streamlit's cache changes the behaviour",
        prompt="Clear Streamlit's cache (`streamlit cache clear`, or 'Clear cache' in the app menu) "
        "and rerun. Does the behaviour change?",
        cost=1,
        values=YES_NO,
    ),
    # --- session state and widgets (the team's data domain)
    Facet(
        id="regression",
        kind=FacetKind.ATTRIBUTE,
        value_type=ValueType.CATEGORY,
        description="Whether the same code worked in an earlier Streamlit version",
        prompt="Did the same code work in an earlier Streamlit version? If so, which was the last version that worked?",
        cost=1,
        values=YES_NO,
    ),
    Facet(
        id="lost_after_page_reload",
        kind=FacetKind.ATTRIBUTE,
        value_type=ValueType.CATEGORY,
        description="Whether state is lost only after a browser reload / new tab / reconnect",
        prompt="Is the value lost only after a full browser reload, opening the app in a new tab or a "
        "reconnect, or also during normal interaction without reloading?",
        cost=1,
        values=YES_NO,
    ),
    Facet(
        id="widget_has_key",
        kind=FacetKind.ATTRIBUTE,
        value_type=ValueType.CATEGORY,
        description="Whether the affected widget has an explicit key",
        prompt="Does the affected widget have an explicit `key=` argument?",
        cost=1,
        values=YES_NO,
    ),
    Facet(
        id="options_change_between_reruns",
        kind=FacetKind.ATTRIBUTE,
        value_type=ValueType.CATEGORY,
        description="Whether the widget's label, options, default or format_func output change between reruns",
        prompt="Do the widget's label, options (or their order), default value or `format_func` output "
        "change from one rerun to the next?",
        cost=2,
        values=YES_NO,
    ),
    Facet(
        id="uses_callback",
        kind=FacetKind.ATTRIBUTE,
        value_type=ValueType.CATEGORY,
        description="Whether the value is set inside a widget callback",
        prompt="Is the value set or changed inside a widget callback (`on_click`, `on_change` or `on_submit`)?",
        cost=1,
        values=YES_NO,
    ),
    Facet(
        id="multipage_app",
        kind=FacetKind.ATTRIBUTE,
        value_type=ValueType.CATEGORY,
        description="Whether the problem involves switching pages in a multipage app",
        prompt="Does the problem happen when switching pages in a multipage app "
        "(`st.navigation`, `st.switch_page` or a `pages/` folder)?",
        cost=1,
        values=YES_NO,
    ),
    Facet(
        id="inside_fragment",
        kind=FacetKind.ATTRIBUTE,
        value_type=ValueType.CATEGORY,
        description="Whether the widget is inside an st.fragment",
        prompt="Is the widget inside an `@st.fragment` (including a fragment with `run_every`)?",
        cost=1,
        values=YES_NO,
    ),
    Facet(
        id="inside_dialog",
        kind=FacetKind.ATTRIBUTE,
        value_type=ValueType.CATEGORY,
        description="Whether the widget is inside an st.dialog",
        prompt="Is the widget inside an `@st.dialog`?",
        cost=1,
        values=YES_NO,
    ),
    Facet(
        id="inside_form",
        kind=FacetKind.ATTRIBUTE,
        value_type=ValueType.CATEGORY,
        description="Whether the widget is inside an st.form",
        prompt="Is the widget inside an `st.form`?",
        cost=1,
        values=YES_NO,
    ),
    Facet(
        id="calls_st_rerun",
        kind=FacetKind.ATTRIBUTE,
        value_type=ValueType.CATEGORY,
        description="Whether the app calls st.rerun around the failing interaction",
        prompt="Does the app call `st.rerun()` around the interaction where the value is lost?",
        cost=1,
        values=YES_NO,
    ),
    Facet(
        id="error_message",
        kind=FacetKind.ATTRIBUTE,
        value_type=ValueType.TEXT,
        description="Exact error message / traceback",
        prompt="Please paste the full error message or traceback, from the terminal running "
        "Streamlit and from the browser console if any.",
        cost=1,
        fallback_priority=4,
    ),
    Facet(
        id="code_snippet",
        kind=FacetKind.ATTRIBUTE,
        value_type=ValueType.TEXT,
        description="Minimal code that reproduces the problem",
        prompt="Please share a minimal, self-contained script that still shows the problem.",
        cost=3,
        fallback_priority=2,
    ),
)

FACETS_BY_ID: dict[str, Facet] = {facet.id: facet for facet in FACETS}


def get_facet(facet_id: str) -> Facet:
    try:
        return FACETS_BY_ID[facet_id]
    except KeyError:
        raise KeyError(f"unknown facet {facet_id!r}") from None
