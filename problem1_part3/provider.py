"""Bounded OpenAI-compatible JSON composer used by Part 3 live mode."""

from __future__ import annotations

import json
from typing import Any

from .configuration import GatewayConfig
from .contracts import ReportError


class Gateway:
    def __init__(self, config: GatewayConfig, *, client=None) -> None:
        self.config = config
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as error:
                raise ReportError('Live mode requires the openai package') from error
            try:
                client = OpenAI(api_key=config.api_key, base_url=config.base_url,
                                timeout=config.timeout_seconds, max_retries=0)
            except Exception as error:
                raise ReportError('Unable to initialize the live provider') from error
        self.client = client
        self.calls = 0
        self.unavailable = False
        self.last_usage = self._empty_usage()
        self.total_usage = self._empty_usage()

    @staticmethod
    def _empty_usage() -> dict:
        return {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0, 'estimated_cost_usd': 0.0}

    def complete(self, messages: list[dict], schema: dict) -> dict:
        if self.unavailable:
            raise ReportError('Live provider is unavailable for this run')
        if self.calls >= self.config.max_calls:
            raise ReportError('Live provider call budget exhausted')
        self.calls += 1
        self.last_usage = self._empty_usage()
        response_format: dict[str, Any]
        if self.config.structured_outputs:
            response_format = {'type': 'json_schema', 'json_schema': {
                'name': 'part3_composition', 'strict': True, 'schema': schema,
            }}
        else:
            response_format = {'type': 'json_object'}
        request = dict(
            model=self.config.model,
            messages=messages,
            temperature=0,
            response_format=response_format,
        )
        request[self.config.token_parameter] = self.config.max_output_tokens
        try:
            response = self.client.chat.completions.create(**request)
        except Exception as error:
            # Do not repeat a failed network/authentication request for every
            # report in a batch, and never expose provider exception text.
            self.unavailable = True
            raise ReportError('Live provider request failed') from error
        if not getattr(response, 'choices', None):
            raise ReportError('Provider returned no completion choice')
        usage = getattr(response, 'usage', None)
        input_tokens = int(getattr(usage, 'prompt_tokens', 0) or 0)
        output_tokens = int(getattr(usage, 'completion_tokens', 0) or 0)
        self.last_usage = {
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'total_tokens': int(getattr(usage, 'total_tokens', input_tokens + output_tokens) or 0),
            'estimated_cost_usd': round(
                input_tokens * self.config.input_usd_per_million / 1_000_000
                + output_tokens * self.config.output_usd_per_million / 1_000_000,
                8,
            ),
        }
        for name in self.total_usage:
            self.total_usage[name] += self.last_usage[name]
        self.total_usage['estimated_cost_usd'] = round(self.total_usage['estimated_cost_usd'], 8)
        content = response.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise ReportError('Provider returned empty completion content')
        try:
            parsed = json.loads(content)
        except (TypeError, json.JSONDecodeError) as error:
            raise ReportError('Provider returned invalid JSON content') from error
        return parsed
