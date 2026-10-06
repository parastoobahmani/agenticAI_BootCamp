"""File-based Part 3 integration. Defaults resolve from the package's parent."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from . import prepare_next_step_response, markdown_summary, ReportError
from .contracts import fingerprint

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BUNDLED_DEMO_REPORT = PROJECT_ROOT/'part1_2_output'/'example_part1_2_output.json'


def _write(path, text):
    """Publish each completed file atomically; manifest is written last."""
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as f:
        temp = Path(f.name)
        f.write(text)
    try:
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Compose from Part 2 JSON reports; schemas are not case reports')
    parser.add_argument('report', nargs='?', type=Path, help='Optional report file; otherwise scan the default input folder')
    parser.add_argument('--input-dir', type=Path, default=PROJECT_ROOT/'part1_2_output')
    parser.add_argument('--output-dir', type=Path,
                        help='Exact output directory; defaults to project-root part1_3_output (replaced on each run)')
    parser.add_argument('--demo', action='store_true', help='Use the bundled authored example; never treated as real Part 2 output')
    args = parser.parse_args(argv)
    if args.demo and args.report:
        parser.error('--demo cannot be combined with an explicit report')
    try:
        discovered = sorted(path for path in args.input_dir.glob('*.json')
                            if not path.name.startswith('example_'))
        paths = [BUNDLED_DEMO_REPORT] if args.demo else ([args.report] if args.report else discovered)
        reports = []
        for path in paths:
            if path.stat().st_size > 200000:
                raise ReportError('NextStepReport exceeds 200 KB')
            raw = json.loads(path.read_text())
            is_schema = isinstance(raw, dict) and ('$defs' in raw or '$schema' in raw)
            if is_schema:
                if args.report:
                    raise ReportError('The selected file is a JSON Schema, not a populated Part 2 report')
                continue
            reports.append((path, prepare_next_step_response(raw)))
        if not reports:
            raise ReportError('No populated Part 2 reports found. The supplied schema defines the format but contains no case data. Use --demo only for an explicitly labelled example.')
        if len(reports) > 1:
            raise ReportError('Multiple Part 2 reports found; select one explicitly: python -m part3 path/to/report.json. No outputs written.')
        for path, result in reports:
            result['artifact_kind'] = 'demonstration' if args.demo else 'part3_response'
            result.pop('id')
            result['id'] = 'response_' + fingerprint(result)[:24]
            case_id = result['case_id']
            output = args.output_dir or PROJECT_ROOT/'part1_3_output'
            output.mkdir(parents=True, exist_ok=True)
            (output/'manifest.json').unlink(missing_ok=True)
            _write(output/'response.json', json.dumps(result, ensure_ascii=False, indent=2)+'\n')
            _write(output/'user_response.txt', result['user_response'])
            _write(output/'maintainer_summary.md', markdown_summary(result))
            _write(output/'manifest.json', json.dumps({
                'status':'complete', 'artifact_kind':'demonstration' if args.demo else 'part3_response',
                'case_id':case_id, 'input_filename':path.name,
                'input_origin':'bundled_authored_example' if args.demo else 'part2_report',
                'response_file':'response.json', 'response_id':result['id'],
                'composition_mode':'offline',
                'files': {name: hashlib.sha256((output/name).read_bytes()).hexdigest()
                          for name in ('response.json', 'user_response.txt', 'maintainer_summary.md')},
            }, indent=2)+'\n')
            print(f"Saved {'DEMONSTRATION' if args.demo else 'response'}: {output}")
    except ReportError as error:
        parser.exit(2, str(error)+'\n')
    except (OSError, ValueError):
        parser.exit(2, 'Unable to compose: check file access and JSON syntax.\n')


if __name__ == '__main__':
    main()
