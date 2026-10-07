"""سند: محدودیت هزینه؛ دفتر مشترک تلاش‌های API، توکن و هزینهٔ برآوردی."""
import math
import os
import sqlite3
import time
from pathlib import Path
from langchain.agents.middleware import wrap_model_call
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_openai import ChatOpenAI
from src.store import pack


class BudgetError(RuntimeError):
    pass


def totals(path):
    if not Path(path).exists():
        return dict(attempts=0, successful_responses=0, input_tokens=0, output_tokens=0, accounted_usd=0)
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        return dict(db.execute("""SELECT COUNT(*) attempts,
          COALESCE(SUM(status IN ('ok','ok_no_usage')),0) successful_responses,
          COALESCE(SUM(input_tokens),0) input_tokens,
          COALESCE(SUM(output_tokens),0) output_tokens,
          COALESCE(SUM(amount),0) accounted_usd FROM usage""").fetchone())


def live_model(ledger):
    key, base, model = [os.getenv(k, '') for k in ['LLM_API_KEY', 'LLM_BASE_URL', 'LLM_MODEL']]
    if not key or not model or not base.startswith('https://'):
        raise BudgetError('Configure LLM_API_KEY, HTTPS LLM_BASE_URL and LLM_MODEL in .env')
    try:
        incoming = float(os.environ['LLM_INPUT_PRICE_PER_M'])
        outgoing = float(os.environ['LLM_OUTPUT_PRICE_PER_M'])
        limit = min(5.0, float(os.getenv('TEAM_BUDGET_USD', '5')))
    except (KeyError, ValueError):
        raise BudgetError('Set actual provider prices per million tokens in .env') from None
    if not all(math.isfinite(v) and v > 0 for v in [incoming, outgoing, limit]):
        raise BudgetError('Prices and budget must be positive finite numbers')
    Path(ledger).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(ledger) as db:
        db.execute('''CREATE TABLE IF NOT EXISTS usage(id INTEGER PRIMARY KEY,
          amount REAL, status TEXT, input_tokens INTEGER, output_tokens INTEGER,
          elapsed REAL, at TEXT DEFAULT CURRENT_TIMESTAMP)''')

    @wrap_model_call
    def account(request, handler):
        # شامل system prompt، سابقه و schema ابزارها؛ برآورد محافظه‌کارانه برای رزرو.
        payload = [m.model_dump() for m in request.messages]
        if request.system_message:
            payload.append(request.system_message.model_dump())
        schemas = [convert_to_openai_tool(t) for t in request.tools]
        upper_input = len(pack([payload, schemas]).encode()) + 2048
        reserve = (upper_input * incoming + 1000 * outgoing) / 1e6
        with sqlite3.connect(ledger, timeout=20) as db:
            db.execute('BEGIN IMMEDIATE')
            spent, attempts = db.execute('SELECT COALESCE(SUM(amount),0),COUNT(*) FROM usage').fetchone()
            if spent + reserve > limit or attempts >= 200:
                raise BudgetError('TEAM_BUDGET_OR_REQUEST_LIMIT_REACHED')
            ident = db.execute("INSERT INTO usage(amount,status) VALUES(?,'uncertain')", (reserve,)).lastrowid
        print(f'[API] attempt={ident} model={model} reserved_usd={reserve:.6f}', flush=True)
        started = time.perf_counter()
        try:
            response = handler(request)
        except Exception:
            # ممکن است سرور هزینه گرفته باشد؛ رزرو آزاد و درخواست تکرار نمی‌شود.
            with sqlite3.connect(ledger) as db:
                db.execute('UPDATE usage SET elapsed=? WHERE id=?', (time.perf_counter() - started, ident))
            raise BudgetError('API_FAILED_OR_UNCERTAIN: reservation kept; no offline fallback') from None
        usage = response.result[-1].usage_metadata or {}
        actual = 'input_tokens' in usage and 'output_tokens' in usage
        it, ot = usage.get('input_tokens', 0), usage.get('output_tokens', 0)
        amount = (it * incoming + ot * outgoing) / 1e6 if actual else reserve
        with sqlite3.connect(ledger) as db:
            db.execute('UPDATE usage SET amount=?,status=?,input_tokens=?,output_tokens=?,elapsed=? WHERE id=?',
                       (amount, 'ok' if actual else 'ok_no_usage', it, ot,
                        time.perf_counter() - started, ident))
        print(f'[API] response_received={ident} usage_reported={actual}', flush=True)
        return response

    llm = ChatOpenAI(api_key=key, base_url=base, model=model, temperature=0,
                     max_tokens=1000, max_retries=0, timeout=30,
                     model_kwargs={'parallel_tool_calls': False})
    return llm, account
