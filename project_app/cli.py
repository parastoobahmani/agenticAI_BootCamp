from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import sys

from problem1_part3 import ReportError
from problem1_part3.configuration import GatewayConfig
from problem1_part3.provider import Gateway

from .pipeline import IntegrationError, ProjectPipeline, load_case_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="project-app",
        description="Run the integrated support pipeline and create a pending Problem 2 proposal.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="process one case JSON")
    run.add_argument("case_file", help="JSON matching the Part 2 Case contract")
    run.add_argument("--live", action="store_true", help="use the configured provider for Part 3 prose")
    run.add_argument("--env-file", help="provider env file; required with --live")
    run.add_argument("--runs-dir")
    run.add_argument("--db")
    run.add_argument("--tracker")
    run.add_argument("--top-k", type=int, default=10)

    serve = subparsers.add_parser("serve", help="run the local user and maintainer web application")
    serve.add_argument("--host", default="127.0.0.1", choices=("127.0.0.1", "localhost", "::1"))
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--live", action="store_true", help="use the configured provider for Part 3 prose")
    serve.add_argument("--env-file", help="provider env file; required with --live")
    serve.add_argument("--runs-dir")
    serve.add_argument("--db")
    serve.add_argument("--tracker")
    serve.add_argument("--web-db")
    serve.add_argument("--top-k", type=int, default=10)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.live and not args.env_file:
        print("error: --env-file is required with --live", file=sys.stderr)
        return 2
    try:
        options = {"top_k": args.top_k}
        if args.runs_dir:
            options["runs_dir"] = args.runs_dir
        if args.db:
            options["db_path"] = args.db
        if args.tracker:
            options["tracker_path"] = args.tracker
        pipeline = ProjectPipeline(**options)

        if args.command == "serve":
            from .web_server import make_server
            from .web_service import ProjectWebService
            from .web_store import WebStore

            config = GatewayConfig.from_env_file(args.env_file) if args.live else None
            web_db = Path(args.web_db) if args.web_db else Path(__file__).resolve().parent / "runtime" / "web.sqlite3"
            service = ProjectWebService(pipeline, WebStore(web_db), gateway_config=config)
            server = make_server(service, args.host, args.port)
            shown_host = "127.0.0.1" if args.host in {"localhost", "::1"} else args.host
            print(f"Support workbench: http://{shown_host}:{server.server_port}/", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
            return 0

        case = load_case_file(args.case_file)
        gateway = None
        provider = None
        if args.live:
            config = GatewayConfig.from_env_file(args.env_file)
            gateway = Gateway(config)
            provider = config.public()
        result = pipeline.run(
            case,
            compose=gateway.complete if gateway else None,
            provider_metadata=provider,
            provider_usage=(lambda: gateway.last_usage) if gateway else None,
        )
    except (IntegrationError, ReportError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    payload = result.to_dict()
    python = shlex.quote(sys.executable)
    payload["next_commands"] = {
        "inspect": f"{python} -m problem2_parts1_2 show {shlex.quote(result.case_id)}",
        "approve": f"{python} -m problem2_parts1_2 approve {shlex.quote(result.case_id)} {shlex.quote(result.proposal_id)}",
        "execute_after_approval": (
            f"{python} -m problem2_parts1_2 execute {shlex.quote(result.case_id)} "
            f"{shlex.quote(result.proposal_id)} --token <approval-token>"
        ),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0
