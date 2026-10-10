"""Command-line interface of the missing-information analyzer.

    missing-info analyze examples/stuck_loading_on_server.json --format markdown
    missing-info analyze input.json --llm --llm-cache runs/llm_cache.json
    missing-info from-part1 examples/part1/evidence_synthesis_result.json --case examples/part1/session_state_case.json
    missing-info from-part1 result.json --issue 17265 --data-dir ../finding_synthesizing_evidence/data/raw
    missing-info schema --output-dir schemas
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from collections.abc import Callable
from typing import TYPE_CHECKING

from missing_info.config import AnalyzerConfig
from missing_info.pipeline import analyze
from missing_info.profiling import ExpectationProfiler, RuleBasedProfiler
from missing_info.part1_adapter import SourceIndex, bundle_from_synthesis, case_from_snapshot
from missing_info.render import to_markdown
from missing_info.schemas import AnalysisInput, Case, NextStepReport

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


def _read_part1_input(args: argparse.Namespace) -> AnalysisInput:
    data_dir = Path(args.data_dir) if args.data_dir else None
    if args.issue is not None:
        if data_dir is None:
            raise RuntimeError("--issue needs --data-dir (part 1's data/raw folder)")
        case = case_from_snapshot(args.issue, data_dir)
    else:
        case = Case.model_validate_json(Path(args.case).read_text(encoding="utf-8"))
    synthesis = json.loads(Path(args.synthesis).read_text(encoding="utf-8"))
    sources = SourceIndex.from_snapshot(data_dir) if data_dir else None
    return AnalysisInput(case=case, evidence_bundle=bundle_from_synthesis(synthesis, sources))


def _cmd_analyze(args: argparse.Namespace) -> int:
    return _run(args, lambda: _read_input(args.input))


def _cmd_from_part1(args: argparse.Namespace) -> int:
    return _run(args, lambda: _read_part1_input(args))


def _run(args: argparse.Namespace, read: Callable[[], AnalysisInput]) -> int:
    try:
        data = read()
        llm_profiler = _llm_profiler(args) if args.llm else None
    except (OSError, ValueError, LookupError, RuntimeError) as exc:  # ValidationError is a ValueError
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


def _add_run_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--output", help="write to this file instead of stdout")
    parser.add_argument("--llm", action="store_true", help="infer hypothesis expectations with an LLM")
    parser.add_argument("--model", default=None, help="LLM model name (default: $MISSING_INFO_MODEL or gpt-4o-mini)")
    parser.add_argument("--llm-cache", help="JSON file to record and replay LLM replies")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="missing-info", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("analyze", help="analyze one case + evidence bundle")
    run.add_argument("input", help="AnalysisInput JSON file, or '-' for stdin")
    _add_run_options(run)
    run.set_defaults(handler=_cmd_analyze)

    part1 = commands.add_parser("from-part1", help="analyze a case using part 1's evidence_synthesis_result.json")
    part1.add_argument("synthesis", help="part 1 output (evidence_synthesis_result.json)")
    source = part1.add_mutually_exclusive_group(required=True)
    source.add_argument("--case", help="Case JSON file (the report that part 1 analysed)")
    source.add_argument("--issue", help="issue number to load from part 1's snapshot (needs --data-dir)")
    part1.add_argument("--data-dir", help="part 1's data/raw folder, to restore URLs/sections/versions")
    _add_run_options(part1)
    part1.set_defaults(handler=_cmd_from_part1)

    schema = commands.add_parser("schema", help="export JSON Schemas of the input and output")
    schema.add_argument("--output-dir", default="schemas")
    schema.set_defaults(handler=_cmd_schema)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
