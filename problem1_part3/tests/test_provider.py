"""Provider tests use fakes and never make a network request."""

import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from problem1_part3 import ReportError
from problem1_part3.configuration import GatewayConfig
from problem1_part3.provider import Gateway


class FakeCompletions:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def create(self, **request):
        self.requests.append(request)
        return self.response


class FailingCompletions:
    def __init__(self):
        self.calls = 0

    def create(self, **request):
        self.calls += 1
        raise RuntimeError('sensitive provider details')


class ProviderTests(unittest.TestCase):
    def config(self, **changes):
        values = dict(
            api_key='private-value', base_url='https://api.example.test/v1', model='small-model',
            timeout_seconds=10.0, max_output_tokens=250, max_calls=2,
            structured_outputs=True, input_usd_per_million=0.5,
            output_usd_per_million=1.5, allowed_hosts=('api.example.test',),
            token_parameter='max_completion_tokens',
        )
        values.update(changes)
        return GatewayConfig(**values)

    def test_env_file_is_provider_interchangeable_and_secret_is_not_public(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'provider.env'
            path.write_text(
                'API_KEY=private-value\n'
                'API_BASE_URL=https://gateway.example.test/openai/v1\n'
                'API_MODEL=course-model\n'
                'API_ALLOWED_HOSTS=gateway.example.test\n'
                'API_STRUCTURED_OUTPUTS=false\n'
                'API_TOKEN_PARAMETER=max_tokens\n', encoding='utf-8')
            config = GatewayConfig.from_env_file(path)
        self.assertEqual(config.model, 'course-model')
        self.assertEqual(config.token_parameter, 'max_tokens')
        self.assertFalse(config.structured_outputs)
        self.assertNotIn('private-value', repr(config))
        self.assertNotIn('api_key', config.public())

    def test_remote_http_and_unlisted_hosts_are_rejected(self):
        cases = [
            'API_KEY=x\nAPI_BASE_URL=http://gateway.example.test/v1\nAPI_MODEL=m\n',
            'API_KEY=x\nAPI_BASE_URL=https://gateway.example.test/v1\nAPI_MODEL=m\nAPI_ALLOWED_HOSTS=other.example.test\n',
        ]
        for content in cases:
            with self.subTest(content=content), tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/'provider.env'
                path.write_text(content, encoding='utf-8')
                with self.assertRaises(ReportError):
                    GatewayConfig.from_env_file(path)

    def test_gateway_requests_schema_and_records_usage_and_cost(self):
        payload = {'user_intro':'The cause is uncertain.', 'case_summary':'The handoff reports one fact.', 'fact_ids':['F1']}
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))],
            usage=SimpleNamespace(prompt_tokens=1000, completion_tokens=500, total_tokens=1500),
        )
        completions = FakeCompletions(response)
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        gateway = Gateway(self.config(), client=client)
        actual = gateway.complete([{'role':'user','content':'data'}], {'type':'object'})
        self.assertEqual(actual, payload)
        request = completions.requests[0]
        self.assertEqual(request['model'], 'small-model')
        self.assertEqual(request['max_completion_tokens'], 250)
        self.assertEqual(request['response_format']['type'], 'json_schema')
        self.assertEqual(gateway.last_usage['total_tokens'], 1500)
        self.assertEqual(gateway.last_usage['estimated_cost_usd'], 0.00125)

    def test_call_budget_is_enforced_without_an_extra_request(self):
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{}'))], usage=None)
        completions = FakeCompletions(response)
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        gateway = Gateway(self.config(max_calls=1), client=client)
        gateway.complete([], {})
        with self.assertRaises(ReportError):
            gateway.complete([], {})
        self.assertEqual(len(completions.requests), 1)

    def test_failed_provider_is_not_called_again_for_the_batch(self):
        completions = FailingCompletions()
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        gateway = Gateway(self.config(), client=client)
        for _ in range(2):
            with self.assertRaisesRegex(ReportError, 'provider') as error:
                gateway.complete([], {})
            self.assertNotIn('sensitive', str(error.exception))
        self.assertEqual(completions.calls, 1)


if __name__ == '__main__':
    unittest.main()
