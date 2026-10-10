from __future__ import annotations

import argparse
import json
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
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.live and not args.env_file:
        print("error: --env-file is required with --live", file=sys.stderr)
        return 2
    try:
        case = load_case_file(args.case_file)
        options = {"top_k": args.top_k}
        if args.runs_dir:
            options["runs_dir"] = args.runs_dir
        if args.db:
            options["db_path"] = args.db
        if args.tracker:
            options["tracker_path"] = args.tracker
        pipeline = ProjectPipeline(**options)

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
    except (IntegrationError, ReportError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    payload = result.to_dict()
    payload["next_commands"] = {
        "inspect": f"python -m problem2_parts1_2 show {result.case_id}",
        "approve": f"python -m problem2_parts1_2 approve {result.case_id} {result.proposal_id}",
        "execute_after_approval": (
            f"python -m problem2_parts1_2 execute {result.case_id} {result.proposal_id} --token <approval-token>"
        ),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0
