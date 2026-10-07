"""رابط سادهٔ خط فرمان؛ سند مسئله ۲ بخش‌های ۱، ۲ و ۳."""
import argparse
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from src.agent import Session
from src.budget import BudgetError, live_model, totals
from src.demo_model import DemoModel
from src.store import Store, StoreError

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')


def show(value):
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def main():
    parser = argparse.ArgumentParser(description='Simple LangChain Streamlit support agent')
    parser.add_argument('--demo', action='store_true', help='Fake model; zero API calls')
    parser.add_argument('--runtime', default=str(ROOT / 'runtime'))
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('init-demo')
    create = sub.add_parser('create')
    create.add_argument('id'); create.add_argument('--title', required=True)
    create.add_argument('--body', required=True); create.add_argument('--facts', default='{}')
    for name in ['show', 'run', 'review', 'recover', 'audit']:
        cmd = sub.add_parser(name); cmd.add_argument('id')
        if name == 'run':
            cmd.add_argument('--message', default='پرونده را بررسی و پیشنهاد را برای تأیید آماده کن.')
    update = sub.add_parser('update'); update.add_argument('id')
    update.add_argument('--message', required=True); update.add_argument('--facts', default='{}')
    update.add_argument('--check', help='JSON: {"name":"websocket","result":"403"}')
    sub.add_parser('cost')
    reset = sub.add_parser('reset'); reset.add_argument('--yes', action='store_true')
    args = parser.parse_args()
    folder = Path(args.runtime)
    ledger = Path(os.getenv('TEAM_LEDGER', str(ROOT / 'runtime' / 'team_cost.sqlite')))
    if args.command == 'cost':
        show(totals(ledger)); return
    if args.command == 'reset':
        if not args.yes:
            print('Use reset --yes to delete LOCAL cases and checkpoints. Cost ledger is kept.'); return
        for name in ['cases.sqlite', 'checkpoints.sqlite']:
            for suffix in ['', '-wal', '-shm', '-journal']:
                (folder / (name + suffix)).unlink(missing_ok=True)
        print('Local cases reset; cost ledger kept.'); return
    db = Store(folder / 'cases.sqlite')
    try:
        if args.command == 'init-demo':
            show(db.create('demo', 'Streamlit app stuck loading behind nginx',
                           'Designed demo: the page keeps loading after deployment. The cause is unknown.'))
        elif args.command == 'create':
            show(db.create(args.id, args.title, args.body, json.loads(args.facts)))
        elif args.command == 'update':
            show(db.update(args.id, args.message, json.loads(args.facts),
                           json.loads(args.check) if args.check else None))
        elif args.command in {'show', 'audit'}:
            show(db.read(args.id) if args.command == 'show' else db.audit(args.id))
        else:
            mode = 'DEMO - fake model, NO API' if args.demo else 'LIVE - LangChain + your API'
            print('MODE:', mode)
            model, middleware = (DemoModel(), []) if args.demo else live_model(ledger)
            if not args.demo:
                middleware = [middleware]
            session = Session(folder, args.id, model, middleware)
            try:
                if args.command == 'review':
                    pending = session.pending()
                    show({'waiting_for_human': pending})
                    if len(pending) != 1:
                        return
                    choice = input('approve / edit / reject: ').strip()
                    if choice not in {'approve', 'edit', 'reject'}:
                        raise StoreError('INVALID_REVIEW')
                    payload = json.loads(input('New payload JSON (not approved yet): ')) if choice == 'edit' else None
                    result = session.review(choice, payload)
                elif args.command == 'recover':
                    result = session.recover()
                else:
                    result = session.run(args.message)
                for message in result.get('messages', []):
                    if message.type == 'ai':
                        for call in message.tool_calls:
                            print('[TOOL]', call['name'])
                if session.pending():
                    show({'waiting_for_human': session.pending(), 'published': False})
                elif result.get('messages'):
                    print(result['messages'][-1].content)
                show({'api_totals_all_live_runs': totals(ledger)})
            finally:
                session.close()
    finally:
        db.db.close()


if __name__ == '__main__':
    try:
        main()
    except (StoreError, BudgetError, ValueError) as exc:
        print('STOP:', str(exc))
        raise SystemExit(1)
    except Exception as exc:
        # متن خام خطای شبکه ممکن است اطلاعات حساس داشته باشد.
        print('STOP:', type(exc).__name__, '- state kept; inspect configuration or recover checkpoint.')
        raise SystemExit(1)
