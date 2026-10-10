"""Load an interchangeable OpenAI-compatible provider configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from urllib.parse import urlparse

from .contracts import ReportError


def _read_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise ReportError('Environment file does not exist')
    values: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:].strip()
        if '=' not in line:
            raise ReportError(f'Invalid environment assignment on line {number}')
        key, value = line.split('=', 1)
        key, value = key.strip(), value.strip()
        if not key or not key.replace('_', '').isalnum() or key[0].isdigit():
            raise ReportError(f'Invalid environment key on line {number}')
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        if key in values:
            raise ReportError(f'Duplicate environment key: {key}')
        values[key] = value
    return values


def _integer(values: dict[str, str], name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(values.get(name, default))
    except (TypeError, ValueError) as error:
        raise ReportError(f'{name} must be an integer') from error
    if not minimum <= value <= maximum:
        raise ReportError(f'{name} must be between {minimum} and {maximum}')
    return value


def _number(values: dict[str, str], name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(values.get(name, default))
    except (TypeError, ValueError) as error:
        raise ReportError(f'{name} must be a number') from error
    if not minimum <= value <= maximum:
        raise ReportError(f'{name} must be between {minimum} and {maximum}')
    return value


def _boolean(values: dict[str, str], name: str, default: bool) -> bool:
    raw = values.get(name, str(default)).strip().lower()
    if raw in {'1', 'true', 'yes', 'on'}:
        return True
    if raw in {'0', 'false', 'no', 'off'}:
        return False
    raise ReportError(f'{name} must be true or false')


@dataclass(frozen=True)
class GatewayConfig:
    api_key: str = field(repr=False)
    base_url: str
    model: str
    timeout_seconds: float
    max_output_tokens: int
    max_calls: int
    structured_outputs: bool
    input_usd_per_million: float
    output_usd_per_million: float
    allowed_hosts: tuple[str, ...]
    token_parameter: str

    @classmethod
    def from_env_file(cls, path: str | Path) -> 'GatewayConfig':
        file_values = _read_env(Path(path))
        values = dict(os.environ)
        values.update(file_values)
        api_key = values.get('API_KEY', '').strip()
        base_url = values.get('API_BASE_URL', '').strip().rstrip('/')
        model = values.get('API_MODEL', '').strip()
        if not api_key:
            raise ReportError('API_KEY is required for live mode')
        if not base_url:
            raise ReportError('API_BASE_URL is required for live mode')
        if not model:
            raise ReportError('API_MODEL is required for live mode')
        parsed = urlparse(base_url)
        if parsed.scheme not in {'https', 'http'} or not parsed.hostname or parsed.username or parsed.password \
                or parsed.query or parsed.fragment:
            raise ReportError('API_BASE_URL must be an HTTP(S) origin/path without credentials, query or fragment')
        if parsed.scheme != 'https' and parsed.hostname not in {'localhost', '127.0.0.1', '::1'}:
            raise ReportError('API_BASE_URL must use HTTPS except for a local gateway')
        allowed = tuple(host.strip().lower() for host in values.get('API_ALLOWED_HOSTS', parsed.hostname).split(',') if host.strip())
        if parsed.hostname.lower() not in allowed:
            raise ReportError('API_BASE_URL host is not listed in API_ALLOWED_HOSTS')
        token_parameter = values.get('API_TOKEN_PARAMETER', 'max_completion_tokens').strip()
        if token_parameter not in {'max_completion_tokens', 'max_tokens'}:
            raise ReportError('API_TOKEN_PARAMETER must be max_completion_tokens or max_tokens')
        return cls(
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout_seconds=_number(values, 'API_TIMEOUT_SECONDS', 30.0, 1.0, 120.0),
            max_output_tokens=_integer(values, 'API_MAX_OUTPUT_TOKENS', 500, 64, 2000),
            max_calls=_integer(values, 'API_MAX_CALLS', 30, 1, 100),
            structured_outputs=_boolean(values, 'API_STRUCTURED_OUTPUTS', True),
            input_usd_per_million=_number(values, 'API_INPUT_USD_PER_MILLION', 0.0, 0.0, 1000.0),
            output_usd_per_million=_number(values, 'API_OUTPUT_USD_PER_MILLION', 0.0, 0.0, 1000.0),
            allowed_hosts=allowed,
            token_parameter=token_parameter,
        )

    def public(self) -> dict:
        return {
            'base_url': self.base_url,
            'model': self.model,
            'timeout_seconds': self.timeout_seconds,
            'max_output_tokens': self.max_output_tokens,
            'max_calls': self.max_calls,
            'structured_outputs': self.structured_outputs,
            'token_parameter': self.token_parameter,
            'input_usd_per_million': self.input_usd_per_million,
            'output_usd_per_million': self.output_usd_per_million,
        }
