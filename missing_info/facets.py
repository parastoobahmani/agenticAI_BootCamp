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
