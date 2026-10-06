"""Validate the teammate's bundled schema; no case/corpus dependencies."""
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator


class ReportError(ValueError):
    """Invalid or unsafe handoff; messages never include submitted values."""


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def redact(value):
    value = re.sub(r'(?i)\b(?:sk-[\w-]{12,}|gh[pousr]_[\w]{15,}|github_pat_[\w]{15,})', '[REDACTED_SECRET]', value)
    value = re.sub(r'(?i)(authorization\s*:\s*bearer\s+)\S+', r'\1[REDACTED_SECRET]', value)
    value = re.sub(r'''(?i)((?:api[_-]?key|password|token|secret)\s*[=:]\s*)['"]?[^\s'";,]+''', r'\1[REDACTED_SECRET]', value)
    return re.sub(r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b', '[REDACTED_EMAIL]', value)


def _clean(value, depth=0):
    if depth > 20:
        raise ReportError('NextStepReport nesting limit exceeded')
    if isinstance(value, str):
        if len(value) > 12000:
            raise ReportError('NextStepReport text limit exceeded')
        return redact(value)
    if isinstance(value, list):
        if len(value) > 100:
            raise ReportError('NextStepReport array limit exceeded')
        return [_clean(item, depth+1) for item in value]
    if isinstance(value, dict):
        if len(value) > 100 or any(not isinstance(k, str) or len(k) > 200 for k in value):
            raise ReportError('Invalid NextStepReport object keys')
        return {k: _clean(v, depth+1) for k, v in value.items()}
    return value


@lru_cache(maxsize=1)
def report_validator():
    schema = json.loads(Path(__file__).with_name('part1_2_output_report.schema.json').read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def parse_report(raw):
    """Schema validation plus documented local bounds and cross-reference checks.

    Input must be an INSTANCE, never a schema file. Missing schema_version uses
    the schema's advertised 1.0 default. Other omitted optional fields stay absent.
    """
    if not isinstance(raw, dict) or '$defs' in raw or '$schema' in raw:
        raise ReportError('Expected a NextStepReport instance, not a JSON Schema')
    try:
        if len(canonical(raw).encode()) > 200000:
            raise ReportError('NextStepReport exceeds 200 KB')
        report = _clean(deepcopy(raw))
    except (TypeError, ValueError, RecursionError) as error:
        if isinstance(error, ReportError):
            raise
        raise ReportError('NextStepReport must contain finite JSON values') from None
    if next(report_validator().iter_errors(report), None) is not None:
        raise ReportError('NextStepReport does not match the supplied JSON Schema')
    report.setdefault('schema_version', '1.0')
    if report['schema_version'] != '1.0':
        raise ReportError('Unsupported NextStepReport schema_version; expected 1.0')
    if not report['case_id'].strip() or len(report['case_id']) > 200:
        raise ReportError('Invalid NextStepReport case_id')
    if len(report['next_steps']) > 10:
        raise ReportError('At most ten selected next steps can be presented')
    ids = [h['hypothesis_id'] for h in report['hypotheses']]
    if any(not i.strip() for i in ids) or len(ids) != len(set(ids)):
        raise ReportError('Empty or duplicate hypothesis IDs')
    references = [report['decision'].get('hypothesis_id')]
    references += [h for m in report['missing_information'] for h in m['relevant_hypotheses']]
    references += [h for s in report['next_steps'] for h in s['distinguishes']]
    if any(h is not None and h not in ids for h in references):
        raise ReportError('NextStepReport refers to an unknown hypothesis')
    # Probability/score calibration, expectation syntax and facet naming are
    # upstream responsibilities. Do not guess their semantics or recompute them.
    return report


def safe_prose(value, maximum=1800):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ReportError('Invalid response text length')
    if redact(value) != value:
        raise ReportError('Generated response contains sensitive text')
    if re.search(r'(?i)(https?://|\bsudo\b|\brm\s+-|curl\s|wget\s|ignore (?:all |previous |the )*instructions|system prompt|reveal.{0,20}(?:secret|key)|disable.{0,25}(?:security|csrf|xsrf|authentication)|(?:share|send|provide).{0,30}(?:password|api.?key|access token))', value):
        raise ReportError('Unsafe or unsupported content in response text')
    return value.strip()
