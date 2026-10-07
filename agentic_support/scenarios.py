"""بخش شما: مسئله ۲ بخش ۳. ده سناریوی چندنوبتی با ورودی و خروجی ذخیره‌شده."""
import json
import tempfile
from pathlib import Path
from src.agent import Session
from src.demo_model import DemoModel
from src.retrieval import ROOT
from src.store import Store, StoreError
from evaluate import facts_from_body

NAMES = ['مسیر عادی', 'اصلاح اطلاعات قبلی', 'رد پیشنهاد', 'ویرایش پیشنهاد', 'راه‌اندازی مجدد',
         'درخواست تکراری', 'تغییر پرونده پیش از اجرا', 'خرابی قبل از ثبت', 'دو پرونده', 'قطع پاسخ بعد از ثبت']


def run_scenario(index, case):
    events, sessions = [], []
    with tempfile.TemporaryDirectory() as folder:
        db = Store(Path(folder) / 'cases.sqlite')
        db.create(case['id'], case['title'], case['body'], facts_from_body(case['body']))

        def record(label, value):
            events.append({'event': label, 'value': value})

        def open_session(case_id=case['id'], fault=None):
            session = Session(folder, case_id, DemoModel(), fault=fault)
            sessions.append(session)
            return session

        def run(session):
            result = session.run()
            record('model_tool_sequence', [c['name'] for m in result['messages'] if m.type == 'ai' for c in m.tool_calls])
            record('pending_human_review', session.pending())

        def review(session, choice, payload=None):
            record('human_decision', {'choice': choice, 'payload': payload})
            result = session.review(choice, payload)
            record('result_after_review', {'pending': session.pending(), 'last_message': result['messages'][-1].content})

        try:
            record('real_issue_initial_input', {'id': case['id'], 'url': case['source_url'],
                'title': case['title'], 'body': case['body']})
            s = open_session(); run(s); review(s, 'approve')
            before = len(db.read(case['id'])['comments'])
            assert before == 1
            followup = {'streamlit_version': '1.50.0', 'location': 'server'}
            record('designed_followup_not_historical', followup)
            db.update(case['id'], 'Designed follow-up: version 1.50.0, server only.', followup,
                      {'name': 'minimal_reproduction', 'result': 'still fails in the designed scenario'})
            if index == 2:
                db.update(case['id'], 'Correction: the failing version is 1.51.0.', {'streamlit_version': '1.51.0'})
                record('user_correction', {'streamlit_version': '1.51.0'})
            s = open_session(fault={8: 'before', 10: 'after'}.get(index)); run(s)
            pending = s.pending()[0]
            proposal_id = pending['proposal_id']
            if index == 3:
                review(s, 'reject')
                assert len(db.read(case['id'])['comments']) == before
            elif index == 4:
                review(s, 'edit', {'comment': 'پس از بررسی انسانی: علت قطعی روشن نیست؛ خلاصه به نگه‌دارنده ارجاع شود.'})
                assert len(db.read(case['id'])['comments']) == before
                assert s.pending()[0]['proposal_id'] != proposal_id
                review(s, 'approve')
            elif index == 5:
                waiting = s.pending()
                s.close(); sessions.remove(s)
                s = open_session()
                assert s.pending() == waiting
                record('restart_restored_same_proposal', True)
                review(s, 'approve')
            elif index == 7:
                db.update(case['id'], 'Correction before approval: local also fails.', {'location': 'local_and_server'})
                record('case_changed_while_waiting', {'location': 'local_and_server'})
                review(s, 'approve')
                assert len(db.read(case['id'])['comments']) == before
                s = open_session(); run(s); review(s, 'approve')
            elif index == 9:
                db.create('other', 'Another Streamlit case', 'Designed second case.', {'python_version': '3.11'})
                other = open_session('other'); run(other)
                try:
                    db.execute('other', proposal_id)
                    raise AssertionError('Cross-case execution was allowed')
                except StoreError:
                    record('cross_case_request_blocked', True)
                review(s, 'approve'); review(other, 'reject')
                assert db.read('other')['comments'] == []
            else:
                review(s, 'approve')
                if index == 6:
                    receipts = [db.execute(case['id'], proposal_id) for _ in range(3)]
                    assert receipts[0] == receipts[-1]
                    record('three_retries_same_receipt', receipts)
                if index in [8, 10]:
                    count = len(db.read(case['id'])['comments'])
                    assert count == before + (index == 10)
                    record('after_failure_comment_count', count)
                    record('explicit_retry_same_approved_operation', db.execute(case['id'], proposal_id))
            final = db.read(case['id'])
            assert len(final['comments']) == before + (index != 3)
            assert final['state'] == 'open'  # پیشرفت پرونده با «حل کامل» یکی نیست.
            assert len(final['checks']) == 1
            if index == 2:
                assert final['summary']['environment']['streamlit_version'] == '1.51.0'
            record('final_state', {k: final[k] for k in ['facts','checks','history','summary','comments','state','revision']})
            record('audit', db.audit(case['id']))
        finally:
            for session in sessions:
                session.close()
            db.db.close()
    return {'scenario': f'S{index:02}', 'name': NAMES[index-1], 'case': case['id'],
            'split': 'dev' if index <= 5 else 'test', 'passed': True, 'trace': events}


def main():
    cases = json.loads((ROOT / 'evaluation/cases.json').read_text(encoding='utf-8'))
    selected = cases[:5] + cases[15:20]
    results = [run_scenario(i + 1, case) for i, case in enumerate(selected)]
    report = dict(mode='real_LangChain_graph_with_fake_model', api_calls=0, cost_usd=0,
        limitation='Initial reports are real; follow-ups and human decisions are designed. '
                   'Dev/test tags describe a regression suite, not an unseen assessment of LLM reasoning.',
        passed=sum(r['passed'] for r in results), total=len(results), results=results)
    (ROOT / 'reports/scenario_results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Scenarios passed:', report['passed'], '/', report['total'], '; API calls: 0')


if __name__ == '__main__':
    main()
