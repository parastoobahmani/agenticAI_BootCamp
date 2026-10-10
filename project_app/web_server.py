"""Local HTTP server and role-specific HTML views for the integrated project."""

from __future__ import annotations

from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse

from .web_service import ProjectWebService, WebFlowError


MAX_FORM_BYTES = 128_000


def _e(value: Any) -> str:
    return escape("" if value is None else str(value), quote=True)


def _json(value: Any) -> str:
    return _e(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def _status_badge(status: str) -> str:
    label = status.replace("_", " ").title()
    return f'<span class="badge badge-{_e(status)}">{_e(label)}</span>'


def _layout(title: str, active: str, content: str, notice: str = "", error: str = "") -> str:
    message = ""
    if notice:
        message = f'<div class="notice" role="status">{_e(notice)}</div>'
    if error:
        message = f'<div class="notice error" role="alert">{_e(error)}</div>'
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_e(title)} · Support workbench</title>
  <link rel="stylesheet" href="/static/styles.css">
</head>
<body>
  <header class="topbar">
    <a class="brand" href="/user"><span class="brand-mark">S</span><span>Support workbench</span></a>
    <nav aria-label="Role views">
      <a class="{'active' if active == 'user' else ''}" href="/user">User</a>
      <a class="{'active' if active == 'maintainer' else ''}" href="/maintainer">Maintainer</a>
    </nav>
  </header>
  <main class="shell">
    {message}
    {content}
  </main>
  <footer>Local project server · actions remain behind human approval</footer>
</body>
</html>"""


def _user_home(service: ProjectWebService, csrf: str, notice: str = "") -> str:
    rows = service.list_cases()
    items = "".join(
        f'<a class="case-row" href="/user/cases/{quote(row["case"]["case_id"], safe="")}">'
        f'<span><strong>{_e(row["case"].get("title"))}</strong><small>{_e(row["case"]["case_id"])}</small></span>'
        f'{_status_badge("waiting" if row.get("pending_count") else "updated")}</a>'
        for row in rows
    ) or '<p class="empty">No cases yet.</p>'
    content = f"""
<section class="hero compact">
  <p class="eyebrow">User portal</p>
  <h1>Report a Streamlit problem</h1>
  <p>Describe what happened and include versions, environment, errors, and what you already tried.</p>
</section>
<div class="grid two">
  <section class="panel">
    <div class="panel-heading"><h2>New case</h2><span class="step">1</span></div>
    <form method="post" action="/user/cases" class="stack">
      <input type="hidden" name="csrf" value="{_e(csrf)}">
      <label>Case ID<input name="case_id" required maxlength="100" placeholder="e.g. app-loading-42"></label>
      <label>Title<input name="title" required maxlength="500" placeholder="Short description of the problem"></label>
      <label>What happened?<textarea name="body" required maxlength="50000" rows="10" placeholder="Include expected and actual behavior..."></textarea></label>
      <p class="hint">Do not paste passwords, API keys, or access tokens.</p>
      <button type="submit">Submit case</button>
    </form>
  </section>
  <section class="panel">
    <div class="panel-heading"><h2>Your cases</h2><span class="count">{len(rows)}</span></div>
    <div class="case-list">{items}</div>
  </section>
</div>"""
    return _layout("User portal", "user", content, notice=notice)


def _user_case(service: ProjectWebService, case_id: str, csrf: str, notice: str = "") -> str:
    detail = service.case_detail(case_id)
    case = detail["case"]
    state = detail["state"]
    timeline = [
        f'<article class="message user-message"><span>User report</span><p>{_e(case.get("body"))}</p></article>'
    ]
    for comment in case.get("comments", []):
        timeline.append(
            f'<article class="message user-message"><span>You</span><p>{_e(comment.get("body"))}</p></article>'
        )
    for comment in detail["ticket"].get("comments", []):
        timeline.append(
            f'<article class="message support-message"><span>Support</span><p>{_e(comment.get("body"))}</p></article>'
        )
    pending = detail["pending_count"]
    status = (
        '<div class="status-card waiting"><strong>Maintainer review in progress</strong>'
        '<p>A draft exists, but it has not been published.</p></div>'
        if pending else
        '<div class="status-card"><strong>Ready for more information</strong>'
        '<p>Add a follow-up whenever the situation changes.</p></div>'
    )
    content = f"""
<div class="page-heading">
  <div><a class="back" href="/user">← All cases</a><p class="eyebrow">Case {_e(case_id)}</p><h1>{_e(case.get('title'))}</h1></div>
  {_status_badge('waiting' if pending else state.get('status', 'open'))}
</div>
<div class="grid case-grid">
  <section class="panel conversation">
    <h2>Conversation</h2>
    {''.join(timeline)}
  </section>
  <aside class="stack">
    {status}
    <section class="panel">
      <h2>Add information</h2>
      <form method="post" action="/user/cases/{quote(case_id, safe='')}/messages" class="stack">
        <input type="hidden" name="csrf" value="{_e(csrf)}">
        <label>Follow-up<textarea name="body" required maxlength="12000" rows="7" placeholder="Share a test result, correction, or new symptom..."></textarea></label>
        <button type="submit">Send follow-up</button>
      </form>
      <p class="hint">New information invalidates an older unreviewed draft and starts a new analysis revision.</p>
    </section>
  </aside>
</div>"""
    return _layout(case.get("title", case_id), "user", content, notice=notice)


def _maintainer_home(service: ProjectWebService, notice: str = "") -> str:
    rows = service.list_cases()
    body = "".join(
        f'<tr><td><a href="/maintainer/cases/{quote(row["case"]["case_id"], safe="")}"><strong>{_e(row["case"].get("title"))}</strong>'
        f'<small>{_e(row["case"]["case_id"])}</small></a></td>'
        f'<td>{_status_badge("pending" if row.get("pending_count") else "reviewed")}</td>'
        f'<td>{row.get("proposal_count", 0)}</td><td>{_e(row.get("updated_at", ""))}</td></tr>'
        for row in rows
    ) or '<tr><td colspan="4" class="empty">No cases yet.</td></tr>'
    content = f"""
<section class="hero compact">
  <p class="eyebrow">Maintainer console</p>
  <h1>Review grounded responses</h1>
  <p>Inspect the decision trail, edit the exact draft, and control the publication boundary.</p>
</section>
<section class="panel table-panel">
  <table>
    <thead><tr><th>Case</th><th>Review</th><th>Revisions</th><th>Updated</th></tr></thead>
    <tbody>{body}</tbody>
  </table>
</section>"""
    return _layout("Maintainer console", "maintainer", content, notice=notice)


def _facts(summary: dict[str, Any]) -> str:
    rows = summary.get("known_facts", [])
    if not rows:
        return '<p class="empty">No extracted facts.</p>'
    return '<dl class="facts">' + "".join(
        f'<div><dt>{_e(row.get("facet"))}</dt><dd>{_e(row.get("value") or row.get("status"))}</dd></div>'
        for row in rows
    ) + '</dl>'


def _maintainer_case(service: ProjectWebService, case_id: str, csrf: str, notice: str = "") -> str:
    detail = service.case_detail(case_id)
    state, proposal = detail["state"], detail["proposal"]
    response = detail.get("response", {})
    summary = response.get("technical_summary", {})
    decision = summary.get("decision", {})
    draft = proposal.get("payload", {}).get("body", "") if proposal else ""
    pending = bool(proposal and proposal.get("status") == "pending")
    controls = f"""
<section class="panel review-panel">
  <div class="panel-heading"><h2>Human approval</h2>{_status_badge(proposal.get('status', 'none') if proposal else 'none')}</div>
  <form method="post" action="/maintainer/cases/{quote(case_id, safe='')}/approve" class="stack">
    <input type="hidden" name="csrf" value="{_e(csrf)}">
    <input type="hidden" name="proposal_id" value="{_e(proposal.get('proposal_id') if proposal else '')}">
    <label>Reply to publish<textarea name="body" maxlength="12000" rows="12" {'required' if pending else 'disabled'}>{_e(draft)}</textarea></label>
    <button type="submit" {'disabled' if not pending else ''}>Approve and publish</button>
  </form>
  <form method="post" action="/maintainer/cases/{quote(case_id, safe='')}/reject" class="stack reject-form">
    <input type="hidden" name="csrf" value="{_e(csrf)}">
    <input type="hidden" name="proposal_id" value="{_e(proposal.get('proposal_id') if proposal else '')}">
    <label>Review note<textarea name="note" maxlength="2000" rows="3" {'disabled' if not pending else ''} placeholder="Why this draft should not be published"></textarea></label>
    <button class="secondary danger" type="submit" {'disabled' if not pending else ''}>Reject draft</button>
  </form>
  <p class="hint">Editing the reply creates approval for the edited action hash. Publication targets the local ticket interceptor.</p>
</section>"""
    steps = "".join(
        f'<li><strong>{_e(step.get("kind"))}</strong><span>{_e(step.get("text"))}</span><small>{_e(step.get("rationale"))}</small></li>'
        for step in summary.get("next_steps", [])
    ) or '<li class="empty">No selected next step.</li>'
    events = "".join(
        f'<li><span>{_e(event["actor"])}</span><strong>{_e(event["kind"].replace("_", " "))}'
        f'<small>{_e(event.get("detail", {}).get("note", ""))}</small></strong><time>{_e(event["created_at"])}</time></li>'
        for event in reversed(detail["events"][-10:])
    ) or '<li class="empty">No web events recorded.</li>'
    content = f"""
<div class="page-heading">
  <div><a class="back" href="/maintainer">← Review queue</a><p class="eyebrow">Case {_e(case_id)}</p><h1>{_e(state.get('title'))}</h1></div>
  {_status_badge('pending' if pending else (proposal.get('status', 'open') if proposal else 'open'))}
</div>
<div class="grid maintainer-grid">
  <div class="stack">
    <section class="panel"><h2>Original report</h2><p class="prose">{_e(state.get('body'))}</p></section>
    <section class="panel">
      <div class="panel-heading"><h2>Decision</h2><span class="decision-type">{_e(decision.get('type', 'unavailable'))}</span></div>
      <p class="prose">{_e(decision.get('rationale', 'No decision artifact is available.'))}</p>
      <h3>Current facts</h3>{_facts(summary)}
      <h3>Selected next steps</h3><ol class="steps">{steps}</ol>
    </section>
    <section class="panel"><h2>Audit trail</h2><ul class="audit">{events}</ul></section>
    <details class="panel raw"><summary>Inspect raw stage artifacts</summary>
      <h3>NextStepReport</h3><pre>{_json(detail.get('report', {}))}</pre>
      <h3>Evidence synthesis</h3><pre>{_json(detail.get('synthesis', {}))}</pre>
    </details>
  </div>
  <aside class="stack sticky">{controls}</aside>
</div>"""
    return _layout(state.get("title", case_id), "maintainer", content, notice=notice)


class ProjectRequestHandler(BaseHTTPRequestHandler):
    service: ProjectWebService
    csrf_token: str
    server_version = "SupportWorkbench/1.0"
    sys_version = ""

    def do_GET(self) -> None:
        if not self._valid_host():
            return self._error(421, "Invalid host")
        parsed = urlparse(self.path)
        notice = parse_qs(parsed.query).get("notice", [""])[0]
        path = parsed.path.rstrip("/") or "/"
        try:
            if path == "/":
                return self._redirect("/user")
            if path == "/healthz":
                return self._send_json({"ok": True})
            if path == "/static/styles.css":
                return self._send_bytes(STYLES.encode(), "text/css; charset=utf-8", cache=True)
            if path == "/user":
                return self._send_html(_user_home(self.service, self.csrf_token, notice))
            if path == "/maintainer":
                return self._send_html(_maintainer_home(self.service, notice))
            if path.startswith("/user/cases/"):
                case_id = unquote(path[len("/user/cases/"):])
                return self._send_html(_user_case(self.service, case_id, self.csrf_token, notice))
            if path.startswith("/maintainer/cases/"):
                case_id = unquote(path[len("/maintainer/cases/"):])
                return self._send_html(_maintainer_case(self.service, case_id, self.csrf_token, notice))
            self._error(404, "Page not found")
        except WebFlowError as exc:
            self._error(404, str(exc))
        except Exception:
            self._error(500, "The server could not complete this request")

    def do_POST(self) -> None:
        if not self._valid_host():
            return self._error(421, "Invalid host")
        path = urlparse(self.path).path.rstrip("/")
        try:
            form = self._form()
            if not secrets.compare_digest(form.get("csrf", ""), self.csrf_token):
                return self._error(403, "Invalid form token; reload the page and try again")
            if path == "/user/cases":
                result = self.service.submit_case(form.get("case_id", ""), form.get("title", ""), form.get("body", ""))
                return self._redirect_notice(f"/user/cases/{quote(result.case_id, safe='')}", "Case submitted; the draft is awaiting maintainer review.")
            if path.startswith("/user/cases/") and path.endswith("/messages"):
                case_id = unquote(path[len("/user/cases/"):-len("/messages")].rstrip("/"))
                self.service.add_user_message(case_id, form.get("body", ""))
                return self._redirect_notice(f"/user/cases/{quote(case_id, safe='')}", "Follow-up added and a new review revision was created.")
            if path.startswith("/maintainer/cases/") and path.endswith("/approve"):
                case_id = unquote(path[len("/maintainer/cases/"):-len("/approve")].rstrip("/"))
                self.service.approve_and_publish(case_id, form.get("proposal_id", ""), form.get("body", ""))
                return self._redirect_notice(f"/maintainer/cases/{quote(case_id, safe='')}", "The exact approved reply was published to the local ticket.")
            if path.startswith("/maintainer/cases/") and path.endswith("/reject"):
                case_id = unquote(path[len("/maintainer/cases/"):-len("/reject")].rstrip("/"))
                self.service.reject(case_id, form.get("proposal_id", ""), form.get("note", ""))
                return self._redirect_notice(f"/maintainer/cases/{quote(case_id, safe='')}", "Draft rejected. The case can resume when new information arrives.")
            self._error(404, "Page not found")
        except WebFlowError as exc:
            self._error(409, str(exc))
        except Exception:
            self._error(500, "The server could not complete this request")

    def _form(self) -> dict[str, str]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise WebFlowError("invalid request length") from exc
        if length <= 0 or length > MAX_FORM_BYTES:
            raise WebFlowError("form is empty or too large")
        if self.headers.get_content_type() != "application/x-www-form-urlencoded":
            raise WebFlowError("unsupported form encoding")
        raw = self.rfile.read(length).decode("utf-8")
        return {key: values[-1] for key, values in parse_qs(raw, keep_blank_values=True).items()}

    def _send_html(self, body: str, status: int = 200) -> None:
        self._send_bytes(body.encode("utf-8"), "text/html; charset=utf-8", status=status)

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        self._send_bytes((json.dumps(payload) + "\n").encode(), "application/json", status=status)

    def _send_bytes(self, body: bytes, content_type: str, *, status: int = 200, cache: bool = False) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.send_header("Cache-Control", "public, max-age=3600" if cache else "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _redirect_notice(self, location: str, notice: str) -> None:
        self._redirect(location + "?" + urlencode({"notice": notice}))

    def _error(self, status: int, message: str) -> None:
        content = f'<section class="panel error-page"><p class="eyebrow">Error {status}</p><h1>{_e(message)}</h1><p><a href="/">Return to the application</a></p></section>'
        self._send_html(_layout("Error", "", content), status=status)

    def _valid_host(self) -> bool:
        host = self.headers.get("Host", "").lower()
        return host == "localhost" or host.startswith("localhost:") \
            or host == "127.0.0.1" or host.startswith("127.0.0.1:") \
            or host == "[::1]" or host.startswith("[::1]:")


def make_server(service: ProjectWebService, host: str, port: int) -> ThreadingHTTPServer:
    token = secrets.token_urlsafe(32)
    handler = type("BoundProjectRequestHandler", (ProjectRequestHandler,), {
        "service": service,
        "csrf_token": token,
    })
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server


STYLES = r"""
:root{--ink:#13231e;--muted:#62736d;--line:#dce5e1;--paper:#f5f7f3;--card:#fff;--green:#0b7257;--green2:#dff3ea;--gold:#9a6710;--red:#9a3434;--shadow:0 14px 40px rgba(23,50,41,.08)}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.topbar{height:68px;padding:0 max(24px,calc((100vw - 1180px)/2));display:flex;align-items:center;justify-content:space-between;background:#10261f;color:#fff}.brand{display:flex;gap:11px;align-items:center;color:#fff;text-decoration:none;font-weight:700}.brand-mark{display:grid;place-items:center;width:34px;height:34px;border-radius:10px;background:#37b68a;color:#092219}.topbar nav{display:flex;gap:7px}.topbar nav a{color:#bbcec7;text-decoration:none;padding:9px 15px;border-radius:9px}.topbar nav a:hover,.topbar nav a.active{background:#28443a;color:#fff}.shell{max-width:1180px;margin:0 auto;padding:42px 24px 70px}.hero{padding:32px 0 28px}.hero.compact{max-width:760px}.eyebrow{text-transform:uppercase;letter-spacing:.13em;color:var(--green);font-weight:800;font-size:12px;margin:0 0 7px}h1{font-size:clamp(30px,4vw,48px);line-height:1.08;letter-spacing:-.035em;margin:0 0 12px}h2{font-size:20px;margin:0 0 18px}h3{font-size:14px;text-transform:uppercase;letter-spacing:.08em;margin:28px 0 12px;color:#53655f}p{margin:0 0 14px}.grid{display:grid;gap:24px}.grid.two{grid-template-columns:1.05fr .95fr}.case-grid{grid-template-columns:1.4fr .75fr}.maintainer-grid{grid-template-columns:minmax(0,1.35fr) minmax(320px,.65fr)}.stack{display:flex;flex-direction:column;gap:16px}.panel{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:24px;box-shadow:var(--shadow)}.panel-heading,.page-heading{display:flex;justify-content:space-between;gap:20px;align-items:flex-start}.step,.count{display:grid;place-items:center;background:var(--green2);color:var(--green);border-radius:999px;min-width:30px;height:30px;font-weight:800}.stack label{font-weight:700;font-size:13px;display:flex;flex-direction:column;gap:7px}input,textarea{width:100%;border:1px solid #bdcbc5;border-radius:10px;background:#fbfcfb;padding:12px 13px;font:inherit;font-weight:400;color:var(--ink);resize:vertical}input:focus,textarea:focus{outline:3px solid #bce8d8;border-color:var(--green)}button{border:0;border-radius:10px;background:var(--green);color:#fff;padding:12px 17px;font:inherit;font-weight:700;cursor:pointer}button:hover{background:#075d47}button:disabled{cursor:not-allowed;opacity:.45}.secondary{background:#eef2ef;color:var(--ink)}.danger{color:var(--red)}.hint,.empty,small{color:var(--muted);font-size:13px}.case-list{display:flex;flex-direction:column}.case-row{display:flex;justify-content:space-between;gap:12px;align-items:center;padding:16px 4px;border-bottom:1px solid var(--line);color:var(--ink);text-decoration:none}.case-row:last-child{border:0}.case-row span:first-child{display:flex;flex-direction:column}.badge{display:inline-block;padding:5px 10px;border-radius:999px;background:#e9eeeb;color:#52635d;text-transform:capitalize;font-size:12px;font-weight:800;white-space:nowrap}.badge-pending,.badge-waiting{background:#fff0cc;color:#855b05}.badge-approved,.badge-reviewed,.badge-updated,.badge-open{background:var(--green2);color:var(--green)}.badge-rejected{background:#f8dfdf;color:var(--red)}.page-heading{margin-bottom:25px;align-items:center}.page-heading h1{font-size:34px}.back{display:inline-block;color:var(--muted);text-decoration:none;margin-bottom:20px}.message{padding:17px 18px;border-radius:14px;margin:12px 0;max-width:88%}.message span{font-size:11px;text-transform:uppercase;letter-spacing:.09em;font-weight:800;color:var(--muted)}.message p{white-space:pre-wrap;margin:5px 0 0}.user-message{background:#eef2ef}.support-message{background:var(--green2);margin-left:auto}.status-card{border:1px solid var(--line);border-left:4px solid var(--green);border-radius:12px;background:#fff;padding:18px}.status-card.waiting{border-left-color:#d39523}.status-card p{color:var(--muted);margin:4px 0 0}.prose{white-space:pre-wrap}.decision-type{font-weight:800;color:var(--green)}.facts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:0}.facts div{background:#f2f5f3;border-radius:10px;padding:12px}.facts dt{font-size:11px;text-transform:uppercase;color:var(--muted);font-weight:800}.facts dd{margin:3px 0 0;font-weight:700}.steps{padding-left:22px}.steps li{padding:8px 0 12px}.steps li span,.steps li small{display:block}.steps li strong{text-transform:capitalize}.audit{list-style:none;padding:0;margin:0}.audit li{display:grid;grid-template-columns:90px 1fr auto;gap:10px;padding:10px 0;border-bottom:1px solid var(--line);font-size:13px}.audit span{color:var(--muted)}.audit strong small{display:block;font-weight:400}.audit time{color:var(--muted);font-size:11px}.raw summary{cursor:pointer;font-weight:800}.raw pre{max-height:420px;overflow:auto;padding:15px;background:#10261f;color:#d8ebe4;border-radius:10px;font:12px/1.55 ui-monospace,monospace}.sticky{position:sticky;top:20px;align-self:start}.reject-form{border-top:1px solid var(--line);padding-top:18px}.notice{padding:14px 17px;margin-bottom:20px;border-radius:11px;background:var(--green2);color:#075d47;font-weight:700}.notice.error{background:#f8dfdf;color:var(--red)}.table-panel{overflow:auto}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:14px;border-bottom:1px solid var(--line)}th{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}td a{display:flex;flex-direction:column;color:var(--ink);text-decoration:none}.error-page{max-width:700px;margin:70px auto}footer{text-align:center;padding:24px;color:var(--muted);font-size:12px}
@media(max-width:850px){.grid.two,.case-grid,.maintainer-grid{grid-template-columns:1fr}.sticky{position:static}.topbar{padding:0 18px}.shell{padding:28px 16px 55px}.facts{grid-template-columns:1fr}.audit li{grid-template-columns:70px 1fr}.audit time{display:none}}
"""
