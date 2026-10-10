"""File-based Part 3 integration. Defaults resolve from the package's parent."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import uuid

from . import prepare_next_step_response, markdown_summary, ReportError
from .configuration import GatewayConfig
from .contracts import fingerprint
from .provider import Gateway

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BUNDLED_DEMO_REPORT = PROJECT_ROOT/'problem1_part2_output'/'example_problem1_part2_output.json'


def _write(path, text):
    """Publish each completed file atomically; manifest is written last."""
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as f:
        temp = Path(f.name)
        f.write(text)
    try:
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def _safe_segment(value):
    """Keep case IDs readable without allowing path traversal."""
    if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,199}', value):
        return value
    return 'case-' + fingerprint(value)[:24]


def _publish_immutable(output, files):
    """Publish one complete response directory once, or verify an exact replay."""
    expected = {name: text.encode('utf-8') for name, text in files.items()}
    if output.exists():
        actual_names = {path.name for path in output.iterdir() if path.is_file()}
        if actual_names == set(expected) and all((output/name).read_bytes() == data
                                                  for name, data in expected.items()):
            return False
        raise ReportError('Immutable response path already exists with different or incomplete content')
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=output.name+'.tmp-', dir=output.parent))
    try:
        for name in ('response.json', 'proposed_user_reply.txt', 'maintainer_summary.md', 'manifest.json'):
            _write(staging/name, files[name])
        try:
            staging.replace(output)
        except OSError:
            if output.exists() and {path.name for path in output.iterdir() if path.is_file()} == set(expected) \
                    and all((output/name).read_bytes() == data for name, data in expected.items()):
                return False
            raise
        return True
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Compose from Part 2 JSON reports; schemas are not case reports')
    parser.add_argument('report', nargs='?', type=Path, help='Optional report file; otherwise scan the default input folder')
    parser.add_argument('--input-dir', type=Path, default=PROJECT_ROOT/'problem1_part2_output')
    parser.add_argument('--output-dir', type=Path,
                        help='Artifact root; defaults to project-root problem1_part3_output')
    parser.add_argument('--demo', action='store_true', help='Use the bundled authored example; never treated as real Part 2 output')
    parser.add_argument('--live', action='store_true', help='Use one bounded OpenAI-compatible composition call per report')
    parser.add_argument('--env-file', type=Path, help='Provider settings file; required with --live')
    args = parser.parse_args(argv)
    if args.demo and args.report:
        parser.error('--demo cannot be combined with an explicit report')
    if args.live and not args.env_file:
        parser.error('--live requires --env-file')
    if args.env_file and not args.live:
        parser.error('--env-file is only read with --live')
    try:
        discovered = sorted(path for path in args.input_dir.glob('*.json')
                            if not path.name.startswith('example_'))
        paths = [BUNDLED_DEMO_REPORT] if args.demo else ([args.report] if args.report else discovered)
        preflight = []
        for path in paths:
            if path.stat().st_size > 200000:
                raise ReportError('NextStepReport exceeds 200 KB')
            raw = json.loads(path.read_text())
            is_schema = isinstance(raw, dict) and ('$defs' in raw or '$schema' in raw)
            if is_schema:
                if args.report:
                    raise ReportError('The selected file is a JSON Schema, not a populated Part 2 report')
                continue
            # Perform every schema, bounds and selected-step safety check before
            # constructing the provider or spending on any report in the batch.
            preflight.append((path, raw, prepare_next_step_response(raw)))
        if not preflight:
            raise ReportError('No populated Part 2 reports found. The supplied schema defines the format but contains no case data. Use --demo only for an explicitly labelled example.')
        case_ids = [result['case_id'] for _, _, result in preflight]
        if len(case_ids) != len(set(case_ids)):
            raise ReportError('Duplicate case_id values in the selected Part 2 reports; no outputs written')
        config = GatewayConfig.from_env_file(args.env_file) if args.live else None
        if config and len(preflight) > config.max_calls:
            raise ReportError('Selected report count exceeds API_MAX_CALLS; no provider calls made')
        gateway = Gateway(config) if config else None
        reports = []
        for path, raw, offline_result in preflight:
            result = prepare_next_step_response(raw, compose=gateway.complete) if gateway else offline_result
            usage = dict(gateway.last_usage) if gateway else None
            reports.append((path, result, usage))
        output_root = args.output_dir or PROJECT_ROOT/'problem1_part3_output'
        run_items = []
        for path, result, usage in reports:
            result['artifact_kind'] = 'demonstration' if args.demo else 'part3_response'
            result.pop('id')
            result['id'] = 'response_' + fingerprint(result)[:24]
            case_id = result['case_id']
            output = output_root/'cases'/_safe_segment(case_id)/result['id']
            response_text = json.dumps(result, ensure_ascii=False, indent=2)+'\n'
            reply_text = result['user_response']
            summary_text = markdown_summary(result)
            payloads = {
                'response.json': response_text,
                'proposed_user_reply.txt': reply_text,
                'maintainer_summary.md': summary_text,
            }
            manifest = {
                'status':'complete', 'artifact_kind':'demonstration' if args.demo else 'part3_response',
                'case_id':case_id, 'input_filename':path.name,
                'input_origin':'bundled_authored_example' if args.demo else 'part2_report',
                'response_file':'response.json', 'response_id':result['id'],
                'input_fingerprint':result['input_fingerprint'],
                'immutable':True, 'composition_mode':result['composition']['method'],
                'files': {name: hashlib.sha256(text.encode('utf-8')).hexdigest()
                          for name, text in payloads.items()},
            }
            payloads['manifest.json'] = json.dumps(manifest, indent=2)+'\n'
            created = _publish_immutable(output, payloads)
            verb = 'Saved' if created else 'Verified existing'
            print(f"{verb} {'DEMONSTRATION' if args.demo else 'response'}: {output}")
            if gateway:
                run_items.append({
                    'case_id': case_id, 'response_id': result['id'],
                    'input_fingerprint': result['input_fingerprint'],
                    'composition': dict(result['composition']), 'usage': usage,
                })
        if gateway:
            run_id = 'run_' + uuid.uuid4().hex
            run_record = {
                'run_id': run_id, 'created_at': datetime.now(timezone.utc).isoformat(),
                'provider': config.public(), 'responses': run_items,
                'total_usage': dict(gateway.total_usage),
            }
            run_path = output_root/'runs'/(run_id+'.json')
            run_path.parent.mkdir(parents=True, exist_ok=True)
            _write(run_path, json.dumps(run_record, ensure_ascii=False, indent=2)+'\n')
            print(f'Saved live run record: {run_path}')
    except ReportError as error:
        parser.exit(2, str(error)+'\n')
    except (OSError, ValueError):
        parser.exit(2, 'Unable to compose: check file access and JSON syntax.\n')


if __name__ == '__main__':
    main()
