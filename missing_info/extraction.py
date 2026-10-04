"""Extract what is already known (and already tried) from the case conversation.

Extraction is deliberately conservative: a facet is only filled when the text
states it explicitly. Anything not matched stays unknown, because guessing a
version or a check result would make the next-step selection wrong.

Only messages written by the reporter are used. Maintainers' comments often
mention versions or environments that are *not* the user's ("fixed in 1.30",
"works for me on Chrome") and other users' "me too" comments describe their own
setups.

Rules are tried in order within a message and the first match for a facet wins,
so more specific rules come first. Across messages, later statements override
earlier ones; the overridden statements are kept as ``superseded``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from missing_info.facets import FACETS_BY_ID
from missing_info.schemas import Case, FactObservation, FactOrigin, FactStatus, KnownFact

_FLAGS = re.IGNORECASE | re.MULTILINE
_MAX_QUOTE_LENGTH = 200

# Pieces reused across patterns. "[^.\n]{0,N}?" keeps a match inside one sentence.
_SAME_SENTENCE = r"[^.\n]{{0,{}}}?"
_NEGATIVE_OUTCOME = (
    r"(?:didn'?t|did not|doesn'?t|does not|won'?t|no luck|not help|no help|nothing changed|"
    r"same (?:issue|problem|result)|still|کمکی نکرد|فایده\u200c?\s?ای نداشت|درست نشد)"
)
_POSITIVE_OUTCOME = r"(?:fixed|solved|resolved|fixes|solves|resolves|helped|worked|did the trick)"
_VERSION_PREFIX = r"(?:\s*(?:version|ver\.?))?\s*(?:==|:|=|is|-)?\s*v?"
_VERSION = r"(\d+\.\d+(?:\.\d+)?(?:(?:a|b|rc)\d+)?)\b"
_NOT_NEGATED = r"(?<!n't )(?<!not )(?<!never )"
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_SENTENCE_END = re.compile(r"[.!?؟。](?=\s)|\n")


def _near(first: str, second: str, distance: int = 60) -> str:
    """``first`` followed by ``second`` within the same sentence."""
    return f"(?:{first})" + _SAME_SENTENCE.format(distance) + f"(?:{second})"


@dataclass(frozen=True)
class ExtractionRule:
    facet: str
    pattern: re.Pattern[str]
    # Fixed value to record; ``None`` records the first capture group instead.
    value: str | None = None
    status: FactStatus = FactStatus.OBSERVED

    def __post_init__(self) -> None:
        if self.facet not in FACETS_BY_ID:
            raise ValueError(f"extraction rule for unknown facet {self.facet!r}")

    def value_from(self, match: re.Match[str]) -> str | None:
        if self.status is FactStatus.PERFORMED_OUTCOME_UNKNOWN:
            return None
        if self.value is not None:
            return self.value
        return match.group(1).strip()[:_MAX_QUOTE_LENGTH]


def _rule(
    facet: str,
    pattern: str,
    value: str | None = None,
    status: FactStatus = FactStatus.OBSERVED,
) -> ExtractionRule:
    return ExtractionRule(facet, re.compile(pattern, _FLAGS), value, status)


def _check_rules(facet: str, action: str) -> list[ExtractionRule]:
    """Rules for a "did X fix it?" check: negative, positive, then "done, result unknown"."""
    return [
        _rule(facet, _near(action, _NEGATIVE_OUTCOME), "no"),
        _rule(facet, _near(_NEGATIVE_OUTCOME, r"(?:after|even after|despite)\s+" + action, 30), "no"),
        _rule(facet, _near(action, _POSITIVE_OUTCOME), "yes"),
        _rule(facet, action, status=FactStatus.PERFORMED_OUTCOME_UNKNOWN),
    ]


_LOCAL_PLACE = (
    r"(?:locally|on localhost|on (?:my|our) (?:own |local )?(?:machine|computer|laptop|pc|system)|"
    r"(?:روی )?سیستم\s?(?:خودم|شخصی)|لوکال)"
)
_WORKS = (
    _NOT_NEGATED
    + r"\b(?:works?|working|worked|runs?|running|opens?|loads?|fine|ok(?:ay)?)\b"
    + r"|باز می\u200c?\s?(?:شود|شه)|کار می\u200c?\s?(?:کند|کنه)"
)
_FAILS = r"\b(?:happens|fails?|failing|occurs|reproduces|reproducible|broken|stuck|hangs?|crash\w*)\b"

RULES: tuple[ExtractionRule, ...] = (
    # --- versions (the issue-template "Debug info" lines first, then free text)
    _rule("streamlit_version", r"^\s*[-*]?\s*streamlit version\s*:\s*v?" + _VERSION),
    _rule("streamlit_version", r"\bstreamlit" + _VERSION_PREFIX + _VERSION),
    _rule("python_version", r"\bpython" + _VERSION_PREFIX + r"(3\.\d+(?:\.\d+)?)\b"),
    # --- environment
    _rule("operating_system", r"\bwindows\b|\bwin ?1[01]\b", "windows"),
    _rule("operating_system", r"\bmac ?os\b|\bos ?x\b|\bmacbook\b|\b(?:sonoma|ventura|monterey|sequoia)\b", "macos"),
    _rule("operating_system", r"\b(?:linux|ubuntu|debian|centos|fedora|rhel|alpine)\b", "linux"),
    _rule("browser", r"\b(?:google )?chrom(?:e|ium)\b", "chrome"),
    _rule("browser", r"\bfirefox\b", "firefox"),
    _rule("browser", r"\bsafari\b", "safari"),
    _rule("browser", r"(?<!cutting )\b(?:microsoft )?edge\b(?! case)", "edge"),
    _rule(
        "deployment_target",
        # "Open in Streamlit Cloud" is a link in the GitHub issue template, not a deployment.
        r"(?<!open in )\bstreamlit (?:community )?cloud\b|share\.streamlit\.io|\.streamlit\.app\b",
        "community_cloud",
    ),
    _rule("deployment_target", r"\bkubernetes\b|\bk8s\b|\bhelm chart\b", "kubernetes"),
    # Not "container": st.container is a Streamlit API.
    _rule("deployment_target", r"\bdocker\b|\bdocker-compose\b", "docker"),
    _rule(
        "deployment_target",
        r"\bheroku\b|\brender\.com\b|\bcloud run\b|\bapp engine\b|\bapp service\b|\bfly\.io\b",
        "paas",
    ),
    _rule(
        "deployment_target",
        r"\b(?:on|to|onto|in) (?:an? |the |my |our )?(?:remote |linux |production |cloud |ubuntu |company |web |dedicated )?"
        r"(?:server|vps|vm|ec2(?: instance)?|droplet)\b|\b(?:remote|production|linux|ubuntu|cloud) server\b|"
        r"\bvps\b|\bec2\b|سرور",
        "remote_server",
    ),
    _rule("reverse_proxy", r"\b(?:no|without(?: a| any)?|not (?:using|behind)(?: a| any)?) (?:reverse[- ])?proxy\b", "no"),
    _rule(
        "reverse_proxy",
        # Not "Apache Arrow": pyarrow errors are common in Streamlit issues.
        r"\b(?:nginx|apache(?! arrow)|httpd|traefik|caddy|haproxy|reverse[- ]proxy|load[- ]balancer|ingress)\b",
        "yes",
    ),
    _rule("served_under_subpath", r"\bbaseUrlPath\b|\bbase[_ ]url[_ ]path\b|\bsub[- ]?path\b|\bpath prefix\b", "yes"),
    # --- local vs. remote behaviour ("works locally" is checked before "fails ... locally")
    _rule("reproduces_locally", _near(_WORKS, _LOCAL_PLACE), "no"),
    _rule("reproduces_locally", _near(_LOCAL_PLACE, _WORKS, 40), "no"),
    _rule("reproduces_locally", _near(_FAILS, _LOCAL_PLACE, 30), "yes"),
    _rule("reproduces_locally", _near(_LOCAL_PLACE, r"\b(?:too|as well|either)\b", 30), "yes"),
    # --- checks with an outcome
    _rule(
        "websocket_error_in_console",
        r"\bno\s+(?:\w+\s+){0,3}(?:errors?|warnings?)\b[^.\n]{0,40}(?:console|websocket)|"
        r"console (?:is|was|shows nothing|looks) (?:clean|empty)",
        "no",
    ),
    _rule(
        "websocket_error_in_console",
        _near(r"(?:websocket|/_stcore/stream)", r"(?:fail|error|closed|refused|1006|disconnect|reconnect)")
        + "|"
        + _near(r"(?:fail|error)", r"websocket", 40),
        "yes",
    ),
    _rule(
        "websocket_error_in_console",
        r"\b(?:checked|looked at|opened) (?:the )?(?:browser(?:'s)? )?(?:dev ?tools|developer tools|console)",
        status=FactStatus.PERFORMED_OUTCOME_UNKNOWN,
    ),
    _rule("health_endpoint_ok", _near(r"_stcore/health|\bhealthz\b", r"(?:fail|error|404|502|503|timeout|refused)", 40), "no"),
    _rule("health_endpoint_ok", _near(r"_stcore/health|\bhealthz\b", r"\b(?:ok|200)\b", 40), "yes"),
    _rule(
        "reproduces_in_other_browser",
        _NOT_NEGATED + r"\bworks? (?:fine |ok |well )?(?:in|on|with) (?:an?other|a different|other) browser|"
        + _NOT_NEGATED + r"\bworks? (?:fine |ok |well )?(?:in|on) (?:firefox|chrome|safari|edge|incognito|a private window)\b",
        "no",
    ),
    _rule(
        "reproduces_in_other_browser",
        _near(r"(?:other|another|different|all|multiple) browsers?|incognito|private window", r"(?:same|too|as well|also|still)", 40),
        "yes",
    ),
    _rule(
        "reproduces_in_other_browser",
        r"\btried (?:it )?(?:in |with |on )?(?:an?other|other|a different|different) browsers?\b|\btried incognito\b",
        status=FactStatus.PERFORMED_OUTCOME_UNKNOWN,
    ),
    *_check_rules(
        "upgrade_resolves",
        r"(?:(?:upgrad\w*|updat\w*)(?: to)? (?:streamlit|the latest|latest|to \d)|pip install (?:-U|--upgrade) streamlit)",
    ),
    *_check_rules(
        "reinstall_resolves",
        r"(?:re-?install\w*|clean install|fresh (?:venv|virtual ?env\w*)|نصب دوباره|دوباره نصب)",
    ),
    *_check_rules("cache_clear_resolves", r"(?:clear\w* (?:the |streamlit'?s? )?cache|cache clear)"),
    # --- free-text details
    _rule("error_message", r"^\s*((?:\w+\.)*\w*(?:Error|Exception)\b:[^\n]*)"),
    _rule("error_message", r"(WebSocket connection to \S+ failed[^\n]*)"),
    _rule("code_snippet", r"```py(?:thon)?\b|^\s*import streamlit\b|^\s*from streamlit\b|^\s*st\.\w+\(", "present"),
)


@dataclass(frozen=True)
class Segment:
    location: str
    text: str


def reporter_segments(case: Case) -> list[Segment]:
    """Title, body and the reporter's own comments, in chronological order."""
    segments = [Segment("title", case.title), Segment("body", case.body)]
    for comment in case.comments:
        if comment.is_from_maintainer:
            continue
        if case.author and comment.author and comment.author != case.author:
            continue
        segments.append(Segment(f"comment:{comment.id}", comment.body))
    return segments


def _quote(text: str, match: re.Match[str]) -> str:
    """The sentence (or line) containing the match, as evidence for the extracted fact."""
    start = max((m.end() for m in _SENTENCE_END.finditer(text, 0, match.start())), default=0)
    end_match = _SENTENCE_END.search(text, match.end())
    end = end_match.start() + 1 if end_match else len(text)
    return text[start:end].strip()[:_MAX_QUOTE_LENGTH]


def observe(segment: Segment, rules: tuple[ExtractionRule, ...] = RULES) -> list[FactObservation]:
    """All facet observations in one message; the first matching rule per facet wins."""
    text = _HTML_COMMENT.sub("", segment.text)  # issue templates hide instructions in comments
    observations: dict[str, FactObservation] = {}
    for rule in rules:
        if rule.facet in observations:
            continue
        match = rule.pattern.search(text)
        if match is None:
            continue
        observations[rule.facet] = FactObservation(
            facet=rule.facet,
            value=rule.value_from(match),
            status=rule.status,
            origin=FactOrigin(location=segment.location, quote=_quote(text, match)),
        )
    return list(observations.values())


def consolidate(observations: list[FactObservation]) -> list[KnownFact]:
    """Merge chronological observations into one fact per facet (latest statement wins).

    A later "I did X" without a result never replaces an earlier known result of X.
    """
    facts: dict[str, KnownFact] = {}
    for observation in observations:
        current = facts.get(observation.facet)
        if current is None:
            facts[observation.facet] = KnownFact(**observation.model_dump())
            continue
        if observation.status is FactStatus.PERFORMED_OUTCOME_UNKNOWN:
            continue
        if current.status is FactStatus.OBSERVED and current.value == observation.value:
            continue
        superseded = [*current.superseded]
        if current.status is FactStatus.OBSERVED:
            superseded.append(
                FactObservation(facet=current.facet, value=current.value, status=current.status, origin=current.origin)
            )
        facts[observation.facet] = KnownFact(**observation.model_dump(), superseded=superseded)
    return list(facts.values())


def extract_facts(case: Case, rules: tuple[ExtractionRule, ...] = RULES) -> list[KnownFact]:
    observations = [item for segment in reporter_segments(case) for item in observe(segment, rules)]
    return consolidate(observations)
