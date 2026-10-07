"""آزمون اتصال ChatOpenAI و ثبت مصرف با HTTP جعلی؛ صفر درخواست اینترنتی."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import httpx2 as httpx
from openai import OpenAI
from langchain.agents import create_agent
from src.budget import live_model, totals, BudgetError
from src.agent import Session
from src.store import Store


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'ledger.sqlite'
        self.settings = dict(LLM_API_KEY='test-only-fake-key', LLM_BASE_URL='https://example.test/v1',
            LLM_MODEL='test-model', LLM_INPUT_PRICE_PER_M='1', LLM_OUTPUT_PRICE_PER_M='2', TEAM_BUDGET_USD='5',
            HTTP_PROXY='', HTTPS_PROXY='', ALL_PROXY='', http_proxy='', https_proxy='', all_proxy='')

    def tearDown(self):
        self.temp.cleanup()

    def model(self, handler):
        with patch.dict(os.environ, self.settings):
            model, budget = live_model(self.path)
        client = OpenAI(api_key='test-only-fake-key', base_url='https://example.test/v1', max_retries=0,
                        http_client=httpx.Client(transport=httpx.MockTransport(handler)))
        self.addCleanup(client.close)
        model.client = client.chat.completions
        return create_agent(model=model, tools=[], middleware=[budget])

    def test_success_usage(self):
        def respond(request):
            return httpx.Response(200, json={'id':'fake', 'object':'chat.completion', 'created':0,
                'model':'test-model', 'choices':[{'index':0, 'message':{'role':'assistant','content':'ok'},
                'finish_reason':'stop'}], 'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}})
        agent = self.model(respond)
        agent.invoke({'messages':[{'role':'user','content':'hello'}]})
        value = totals(self.path)
        self.assertEqual(value['successful_responses'], 1)
        self.assertEqual(value['input_tokens'], 10)
        self.assertAlmostEqual(value['accounted_usd'], 0.00002)

    def test_error_no_retry_and_reserve_kept(self):
        hits = []
        def fail(request):
            hits.append(1)
            raise httpx.ReadTimeout('Simulated timeout')
        agent = self.model(fail)
        with self.assertRaises(BudgetError):
            agent.invoke({'messages':[{'role':'user','content':'hello'}]})
        self.assertEqual(len(hits), 1)
        self.assertEqual(totals(self.path)['attempts'], 1)
        self.assertGreater(totals(self.path)['accounted_usd'], 0)

    def test_budget_stops_before_http(self):
        self.settings['TEAM_BUDGET_USD'] = '0.000001'
        def forbidden(request):
            self.fail('HTTP should not be called')
        with self.assertRaises(BudgetError):
            self.model(forbidden).invoke({'messages':[{'role':'user','content':'hello'}]})
        self.assertEqual(totals(self.path)['attempts'], 0)

    def test_chatopenai_tool_calling_to_human_pause(self):
        steps = [('read_case', {}), ('search_docs', {'query': 'session state'}),
            ('draft_reply', dict(reply='نسخه چیست؟', decision='ask', reason='مقایسهٔ نسخه‌ها',
                unknowns=['streamlit_version'], source_ids=[], question_field='streamlit_version')),
            ('apply_change', {'proposal_id': 1})]
        seen = []
        def respond(request):
            body = json.loads(request.content)
            self.assertEqual(len(body['tools']), 6)
            index = len(seen); seen.append(body)
            message = {'role':'assistant', 'content':'done'}
            if index < len(steps):
                name, args = steps[index]
                message = {'role':'assistant','content':None, 'tool_calls':[{'id':f'mock-{index}',
                    'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}
            return httpx.Response(200,json={'id':f'fake-{index}','object':'chat.completion','created':0,
                'model':'test-model','choices':[{'index':0,'message':message,
                    'finish_reason':'tool_calls' if index<len(steps) else 'stop'}],
                'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}})
        with patch.dict(os.environ,self.settings):
            model, account = live_model(self.path)
        client = OpenAI(api_key='test-only-fake-key',base_url='https://example.test/v1',max_retries=0,
            http_client=httpx.Client(transport=httpx.MockTransport(respond)))
        self.addCleanup(client.close)
        model.client = client.chat.completions
        db = Store(Path(self.temp.name)/'cases.sqlite')
        db.create('api_test','Streamlit session state','A designed test')
        session = Session(self.temp.name,'api_test',model,[account])
        try:
            session.run()
            self.assertEqual(len(session.pending()),1)
            self.assertEqual(db.read('api_test')['comments'],[])
            session.review('approve')
            self.assertEqual(len(db.read('api_test')['comments']),1)
            self.assertEqual(totals(self.path)['successful_responses'],5)
        finally:
            session.close(); db.db.close()
