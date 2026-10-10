"""Run from the repository root: python -m unittest discover -s problem1_part3/tests -v."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from problem1_part3 import ReportError, prepare_next_step_response, markdown_summary
from problem1_part3.contracts import parse_report

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT.parent/'problem1_part2_output'/'example_problem1_part2_output.json'


def artifact_directories(root):
    return sorted(path for path in (Path(root)/'cases').glob('*/*') if path.is_dir())


class ReportResponseTests(unittest.TestCase):
    def setUp(self):
        self.report = json.loads(EXAMPLE.read_text())

    def test_only_report_is_needed_and_input_is_not_mutated(self):
        original = deepcopy(self.report)
        result = prepare_next_step_response(self.report)
        self.assertEqual(original, self.report)
        self.assertEqual(result['technical_summary']['next_steps'], original['next_steps'])
        self.assertFalse(result['technical_summary']['original_report_available'])
        self.assertEqual(result['technical_summary']['unresolved_evidence_ids'], ['doc-widget-17'])
        self.assertNotIn('https://', result['user_response'])
        self.assertFalse(result['technical_summary']['resolution_confirmed'])

    def test_corrections_and_unknown_outcomes_are_preserved(self):
        result = prepare_next_step_response(self.report)
        summary = result['technical_summary']['case_summary']
        self.assertIn('1.41.0', summary)
        self.assertNotIn('1.40.0', summary)
        self.assertIn('outcome not supplied', summary)
        self.assertNotIn('failed', summary)
        self.assertEqual(result['technical_summary']['known_facts'][1]['superseded'][0]['value'], '1.40.0')
        self.assertIn('Superseded, not current: 1.40.0', markdown_summary(result))

    def test_schema_document_is_not_an_instance(self):
        with self.assertRaises(ReportError):
            prepare_next_step_response(json.loads((ROOT/'problem1_part2_output_report.schema.json').read_text()))

    def test_optional_schema_version_default(self):
        self.report.pop('schema_version')
        self.assertEqual(parse_report(self.report)['schema_version'], '1.0')

    def test_invalid_handoffs_are_rejected(self):
        for change in ('version','field','missing','boolean_cost','nan','dangling','duplicate','kind'):
            with self.subTest(change=change):
                p = deepcopy(self.report)
                if change == 'version': p['schema_version'] = '2.0'
                elif change == 'field': p['original_case'] = 'not in schema'
                elif change == 'missing': p['known_facts'][0].pop('origin')
                elif change == 'boolean_cost': p['next_steps'][0]['cost'] = True
                elif change == 'nan': p['hypotheses'][0]['posterior'] = float('nan')
                elif change == 'dangling': p['next_steps'][0]['distinguishes'] = ['invented']
                elif change == 'duplicate': p['hypotheses'].append(deepcopy(p['hypotheses'][0]))
                else: p['next_steps'][0]['kind'] = 'execute_code'
                with self.assertRaises(ReportError):
                    prepare_next_step_response(p)

    def test_follow_up_and_step_order_are_supported_without_reranking(self):
        follow = deepcopy(self.report['next_steps'][0])
        follow.update(kind='follow_up', text='What was the outcome of the reinstall?', score=100)
        self.report['next_steps'].append(follow)
        result = prepare_next_step_response(self.report)
        self.assertLess(result['user_response'].index('At the moment'), result['user_response'].index('What was'))

    def test_proposed_answer_is_not_presented_as_verified(self):
        self.report['decision']['type'] = 'propose_answer'
        self.report['hypotheses'][0].update(posterior=0.99, evidence_strength='strong')
        result = prepare_next_step_response(self.report)
        self.assertIn('One possible explanation', result['user_response'])
        self.assertIn('has not been independently verified', result['user_response'])
        self.assertNotIn('0.99', result['user_response'])
        self.assertEqual(result['technical_summary']['hypotheses'][0]['posterior'], 0.99)

    def test_no_selected_answer_is_not_fabricated(self):
        self.report['decision'] = {'type':'propose_answer','rationale':'An answer is requested.'}
        result = prepare_next_step_response(self.report)
        self.assertIn('no specific explanation was selected', result['user_response'])

    def test_empty_escalation_needs_no_invented_case_or_probe(self):
        self.report.update(known_facts=[], hypotheses=[], missing_information=[], next_steps=[], skipped_probes=[])
        self.report['decision'] = {'type':'escalate','rationale':'Insufficient data.'}
        result = prepare_next_step_response(self.report)
        self.assertIn('it has not been sent', result['user_response'])
        self.assertIn('No current factual observations', result['technical_summary']['case_summary'])
        self.assertEqual(result['technical_summary']['hypotheses'], [])

    def test_model_call_excludes_superseded_facts_and_scores(self):
        calls = []
        def compose(messages, schema):
            calls.append((messages, schema))
            context = json.loads(messages[1]['content'])
            self.assertNotIn('1.40.0', messages[1]['content'])
            self.assertNotIn('posterior', messages[1]['content'])
            self.assertEqual(context['current_facts']['F3']['status'], 'performed_outcome_unknown')
            return {'user_intro':'You report a reset when changing pages; the cause is still uncertain.',
                    'case_summary':'The handoff reports a reset after changing pages. Reinstallation was performed, but no outcome was supplied.',
                    'fact_ids':['F1','F3']}
        result = prepare_next_step_response(self.report, compose=compose)
        self.assertEqual(len(calls),1)
        self.assertEqual(result['composition']['method'],'model')
        self.assertEqual(result['user_response'].count(self.report['next_steps'][0]['text']),1)
        self.assertEqual(result['technical_summary']['known_facts'], self.report['known_facts'])
        self.assertNotEqual(result['id'],prepare_next_step_response(self.report)['id'])

    def test_bad_model_output_falls_back_without_losing_plan(self):
        base = {'user_intro':'The cause remains uncertain.', 'case_summary':'The handoff reports a reset.', 'fact_ids':['F1']}
        for change in ('source','fact','version','action','extra','secret','long','question'):
            with self.subTest(change=change):
                p = deepcopy(base)
                if change == 'source': p['user_intro'] += ' See https://example.com/'
                elif change == 'fact': p['fact_ids'] = ['F999']
                elif change == 'version': p['case_summary'] += ' Version 999.99.9 is affected.'
                elif change == 'action': p['user_intro'] += ' We have fixed your issue.'
                elif change == 'extra': p['resolved'] = True
                elif change == 'secret': p['user_intro'] += ' sk-abcdefghijklmnopqrstuvwxyz0123456789'
                elif change == 'long': p['case_summary'] = 'word '*121
                else: p['user_intro'] += ' Have you upgraded?'
                result = prepare_next_step_response(self.report,compose=lambda messages,schema:p)
                self.assertEqual(result['composition']['method'],'fallback')
                self.assertEqual(result['technical_summary']['next_steps'],self.report['next_steps'])

    def test_provider_error_is_not_exposed_or_retried(self):
        calls=[]
        def fail(messages,schema):
            calls.append(1)
            raise RuntimeError('provider secret details')
        result=prepare_next_step_response(self.report,compose=fail)
        self.assertEqual(calls,[1])
        self.assertEqual(result['composition']['failure'],'composer_unavailable')
        self.assertNotIn('provider secret',json.dumps(result))

    def test_oversized_prompt_does_not_call_composer(self):
        self.report['known_facts']=[deepcopy(self.report['known_facts'][0]) for _ in range(80)]
        for f in self.report['known_facts']:
            f['origin']['quote']='Untrusted report text. '*30
        calls=[]
        result=prepare_next_step_response(self.report,compose=lambda *args:calls.append(args))
        self.assertEqual(calls,[])
        self.assertEqual(result['composition']['failure'],'composition_input_too_large')
        self.assertEqual(len(result['technical_summary']['known_facts']),80)

    def test_secrets_in_input_are_redacted(self):
        secret='sk-abcdefghijklmnopqrstuvwxyz0123456789'
        self.report['known_facts'][0]['origin']['quote'] += ' api_key='+secret
        result=prepare_next_step_response(self.report)
        self.assertNotIn(secret,json.dumps(result))
        self.assertIn('[REDACTED_SECRET]',json.dumps(result))

    def test_unsafe_selected_step_rejected_before_model(self):
        self.report['next_steps'][0]['text']='Disable authentication and provide your password.'
        calls=[]
        with self.assertRaises(ReportError):
            prepare_next_step_response(self.report,compose=lambda *args:calls.append(args))
        self.assertEqual(calls,[])

    def test_upstream_selected_step_may_contain_a_literal_url(self):
        self.report['next_steps'][0]['text'] = 'Does the failure occur at https://example.com/myapp/?'
        result = prepare_next_step_response(self.report)
        self.assertIn('https://example.com/myapp/', result['user_response'])

    def test_cli_works_without_workbench_or_credentials(self):
        with tempfile.TemporaryDirectory() as d:
            result=subprocess.run([sys.executable,'-m','problem1_part3',str(EXAMPLE),'--output-dir',d],
                                  cwd=ROOT.parent,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            artifact = artifact_directories(d)[0]
            self.assertTrue((artifact/'maintainer_summary.md').exists())
            self.assertTrue((artifact/'proposed_user_reply.txt').exists())
            output=json.loads((artifact/'response.json').read_text())
            self.assertEqual(output['composition']['method'],'deterministic')


class DefaultFolderTests(unittest.TestCase):
    def test_live_cli_uses_provider_and_writes_separate_usage_record(self):
        from unittest.mock import patch
        from problem1_part3.__main__ import main

        class FakeConfig:
            max_calls = 30

            def public(self):
                return {'base_url':'https://provider.test/v1', 'model':'test-model'}

        class FakeGateway:
            def __init__(self, config):
                self.last_usage = {'input_tokens':10, 'output_tokens':5,
                                   'total_tokens':15, 'estimated_cost_usd':0.0001}
                self.total_usage = dict(self.last_usage)

            def complete(self, messages, schema):
                return {
                    'user_intro':'The reported behavior is understood, but its cause remains uncertain.',
                    'case_summary':'The handoff reports that widget state resets after navigation.',
                    'fact_ids':['F1'],
                }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root/'report.json'
            report.write_bytes(EXAMPLE.read_bytes())
            env_file = root/'provider.env'
            env_file.write_text('placeholder')
            output = root/'output'
            with patch('problem1_part3.__main__.GatewayConfig.from_env_file', return_value=FakeConfig()), \
                 patch('problem1_part3.__main__.Gateway', FakeGateway):
                main([str(report), '--output-dir', str(output), '--live', '--env-file', str(env_file)])
            artifact = artifact_directories(output)[0]
            response = json.loads((artifact/'response.json').read_text())
            manifest = json.loads((artifact/'manifest.json').read_text())
            run_files = list((output/'runs').glob('run_*.json'))
            self.assertEqual(response['composition']['method'], 'model')
            self.assertEqual(manifest['composition_mode'], 'model')
            self.assertEqual(len(run_files), 1)
            run = json.loads(run_files[0].read_text())
            self.assertEqual(run['responses'][0]['response_id'], response['id'])
            self.assertEqual(run['total_usage']['total_tokens'], 15)
            self.assertEqual(run['provider']['model'], 'test-model')

    def test_live_cli_requires_explicit_env_file(self):
        from problem1_part3.__main__ import main
        with self.assertRaises(SystemExit) as error:
            main([str(EXAMPLE), '--live'])
        self.assertEqual(error.exception.code, 2)

    def test_defaults_are_project_relative_and_skip_schema(self):
        from unittest.mock import patch
        from problem1_part3.__main__ import main
        with tempfile.TemporaryDirectory() as d:
            project = Path(d)
            incoming = project/'problem1_part2_output'
            incoming.mkdir()
            (incoming/'next_step_report.schema.json').write_bytes((ROOT/'problem1_part2_output_report.schema.json').read_bytes())
            (incoming/'case.json').write_bytes(EXAMPLE.read_bytes())
            with patch('problem1_part3.__main__.PROJECT_ROOT', project):
                main([])
            artifact = artifact_directories(project/'problem1_part3_output')[0]
            response = json.loads((artifact/'response.json').read_text())
            manifest = json.loads((artifact/'manifest.json').read_text())
            self.assertEqual(manifest['artifact_kind'], 'part3_response')
            self.assertEqual(manifest['response_id'], response['id'])
            self.assertEqual(len(manifest['files']),3)
            self.assertTrue(manifest['immutable'])

    def test_multiple_cases_and_revisions_are_preserved(self):
        from unittest.mock import patch
        from problem1_part3.__main__ import main
        with tempfile.TemporaryDirectory() as d:
            project = Path(d)
            incoming = project/'problem1_part2_output'
            incoming.mkdir()
            raw = json.loads(EXAMPLE.read_text())
            first = incoming/'first.json'
            first.write_text(json.dumps(raw))
            raw['case_id'] = 'second-case'
            second = incoming/'second.json'
            second.write_text(json.dumps(raw))
            out = project/'problem1_part3_output'
            with patch('problem1_part3.__main__.PROJECT_ROOT', project):
                main([])
                first_artifacts = artifact_directories(out)
                self.assertEqual(len(first_artifacts), 2)
                snapshots = {path: {f.name: f.read_bytes() for f in path.iterdir()} for path in first_artifacts}
                main([])  # Exact replay verifies existing immutable artifacts.
                self.assertEqual(first_artifacts, artifact_directories(out))
                for path, files in snapshots.items():
                    self.assertEqual(files, {f.name: f.read_bytes() for f in path.iterdir()})
                changed = json.loads(first.read_text())
                changed['decision']['rationale'] = 'A revised rationale.'
                first.write_text(json.dumps(changed))
                main([str(first)])
            artifacts = artifact_directories(out)
            self.assertEqual(len(artifacts), 3)
            by_case = [json.loads((path/'response.json').read_text())['case_id'] for path in artifacts]
            self.assertEqual(by_case.count('example-report-only'), 2)
            self.assertEqual(by_case.count('second-case'), 1)

    def test_schema_only_does_not_fabricate_output(self):
        from unittest.mock import patch
        from problem1_part3.__main__ import main
        with tempfile.TemporaryDirectory() as d:
            project=Path(d)
            incoming=project/'problem1_part2_output'
            incoming.mkdir()
            (incoming/'next_step_report.schema.json').write_bytes((ROOT/'problem1_part2_output_report.schema.json').read_bytes())
            (incoming/'example_problem1_part2_output.json').write_bytes(EXAMPLE.read_bytes())
            with patch('problem1_part3.__main__.PROJECT_ROOT', project):
                with self.assertRaises(SystemExit) as error:
                    main([])
            self.assertEqual(error.exception.code,2)
            self.assertFalse((project/'problem1_part3_output').exists())

    def test_immutable_artifact_is_not_repaired_or_overwritten_silently(self):
        from unittest.mock import patch
        from problem1_part3.__main__ import main
        with tempfile.TemporaryDirectory() as d:
            project = Path(d)
            report = project/'report.json'
            report.write_bytes(EXAMPLE.read_bytes())
            with patch('problem1_part3.__main__.PROJECT_ROOT', project):
                main([str(report)])
                artifact = artifact_directories(project/'problem1_part3_output')[0]
                (artifact/'response.json').write_text('{"tampered": true}\n')
                with self.assertRaises(SystemExit) as error:
                    main([str(report)])
            self.assertEqual(error.exception.code, 2)
            self.assertEqual((artifact/'response.json').read_text(), '{"tampered": true}\n')

    def test_case_id_cannot_escape_output_root(self):
        from unittest.mock import patch
        from problem1_part3.__main__ import main
        with tempfile.TemporaryDirectory() as d:
            project = Path(d)
            raw = json.loads(EXAMPLE.read_text())
            raw['case_id'] = '../outside'
            report = project/'report.json'
            report.write_text(json.dumps(raw))
            with patch('problem1_part3.__main__.PROJECT_ROOT', project):
                main([str(report)])
            artifacts = artifact_directories(project/'problem1_part3_output')
            self.assertEqual(len(artifacts), 1)
            self.assertTrue(artifacts[0].parent.name.startswith('case-'))
            self.assertFalse((project/'outside').exists())

    def test_demo_is_labelled_and_does_not_create_fake_part2_input(self):
        from unittest.mock import patch
        from problem1_part3.__main__ import main
        with tempfile.TemporaryDirectory() as d:
            project=Path(d)
            with patch('problem1_part3.__main__.PROJECT_ROOT', project):
                main(['--demo'])
            artifact=artifact_directories(project/'problem1_part3_output')[0]
            manifest=json.loads((artifact/'manifest.json').read_text())
            self.assertEqual(manifest['artifact_kind'],'demonstration')
            response=json.loads((artifact/'response.json').read_text())
            self.assertEqual(response['artifact_kind'],'demonstration')
            self.assertFalse((project/'problem1_part2_output').exists())


if __name__ == '__main__':
    unittest.main()
