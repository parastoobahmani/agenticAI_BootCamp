"""Command-line interface of the missing-information analyzer.

    missing-info analyze examples/stuck_loading_on_server.json --format markdown
    missing-info analyze input.json --llm --llm-cache runs/llm_cache.json
    missing-info schema --output-dir schemas
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from missing_info.config import AnalyzerConfig
from missing_info.pipeline import analyze
from missing_info.profiling import ExpectationProfiler, RuleBasedProfiler
from missing_info.render import to_markdown
from missing_info.schemas import AnalysisInput, NextStepReport

if TYPE_CHECKING:
    from missing_info.llm import ChatClient, LLMProfiler


def _read_input(path: str) -> AnalysisInput:
    raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    return AnalysisInput.model_validate_json(raw)


def _write(text: str, output: str | None) -> None:
    if output:
        Path(output).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


def _llm_profiler(args: argparse.Namespace) -> LLMProfiler:
    # Imported lazily: the LLM path needs the optional 'openai' dependency.
    from missing_info.llm import CachedChatClient, LLMProfiler, OpenAICompatibleClient

    client: ChatClient = OpenAICompatibleClient.from_env(model=args.model)
    if args.llm_cache:
        client = CachedChatClient(Path(args.llm_cache), client)
    return LLMProfiler(client)


def _cmd_analyze(args: argparse.Namespace) -> int:
    try:
        data = _read_input(args.input)
        llm_profiler = _llm_profiler(args) if args.llm else None
    except (OSError, ValidationError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    profilers: list[ExpectationProfiler] = [RuleBasedProfiler()]
    if llm_profiler is not None:
        profilers.insert(0, llm_profiler)

    report = analyze(data, AnalyzerConfig(), profilers)
    text = to_markdown(report) if args.format == "markdown" else report.model_dump_json(indent=2) + "\n"
    _write(text, args.output)

    if llm_profiler is not None:
        print(f"LLM usage: {llm_profiler.usage}", file=sys.stderr)
        for error in llm_profiler.errors:
            print(f"LLM fallback to rules: {error}", file=sys.stderr)
    return 0


def _cmd_schema(args: argparse.Namespace) -> int:
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, model in (("analysis_input", AnalysisInput), ("next_step_report", NextStepReport)):
        schema = json.dumps(model.model_json_schema(), indent=2, ensure_ascii=False)
        (out_dir / f"{name}.schema.json").write_text(schema + "\n", encoding="utf-8")
    print(f"wrote JSON Schemas to {out_dir}/", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="missing-info", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("analyze", help="analyze one case + evidence bundle")
    run.add_argument("input", help="AnalysisInput JSON file, or '-' for stdin")
    run.add_argument("--format", choices=("json", "markdown"), default="json")
    run.add_argument("--output", help="write to this file instead of stdout")
    run.add_argument("--llm", action="store_true", help="infer hypothesis expectations with an LLM")
    run.add_argument("--model", default=None, help="LLM model name (default: $MISSING_INFO_MODEL or gpt-4o-mini)")
    run.add_argument("--llm-cache", help="JSON file to record and replay LLM replies")
    run.set_defaults(handler=_cmd_analyze)

    schema = commands.add_parser("schema", help="export JSON Schemas of the input and output")
    schema.add_argument("--output-dir", default="schemas")
    schema.set_defaults(handler=_cmd_schema)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
