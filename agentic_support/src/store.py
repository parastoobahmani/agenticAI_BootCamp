"""سند: مسئله ۲، بخش ۱ (حافظه) و بخش ۲ (تأیید و اجرای امن)."""
import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path


def pack(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def digest(value):
    return hashlib.sha256(pack(value).encode()).hexdigest()


class StoreError(ValueError):
    pass


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=20, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS cases(id TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS proposals(
          id INTEGER PRIMARY KEY, case_id TEXT, revision INTEGER, payload TEXT,
          hash TEXT, status TEXT DEFAULT 'pending', approved_hash TEXT,
          request_key TEXT UNIQUE);
        CREATE TABLE IF NOT EXISTS receipts(id INTEGER PRIMARY KEY, result TEXT);
        CREATE TABLE IF NOT EXISTS audit(
          id INTEGER PRIMARY KEY, case_id TEXT, event TEXT, detail TEXT,
          at TEXT DEFAULT CURRENT_TIMESTAMP);
        """)
        self.db.commit()

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def log(self, case_id, event, detail):
        self.db.execute('INSERT INTO audit(case_id,event,detail) VALUES(?,?,?)',
                        (case_id, event, pack(detail)))

    def read(self, case_id):
        row = self.db.execute('SELECT data FROM cases WHERE id=?', (case_id,)).fetchone()
        if not row:
            raise StoreError('CASE_NOT_FOUND')
        return json.loads(row['data'])

    def save(self, case):
        self.db.execute('UPDATE cases SET data=? WHERE id=?', (pack(case), case['id']))

    def create(self, case_id, title, body, facts=None):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,60}', case_id):
            raise StoreError('INVALID_CASE_ID')
        self.validate_facts(facts or {})
        case = dict(id=case_id, title=title, body=body, facts=facts or {}, checks=[],
                    history=[], sources=[], unknowns=[], summary={}, comments=[],
                    state='open', labels=[], revision=0, turn=0)
        with self.transaction():
            self.db.execute('INSERT INTO cases VALUES(?,?)', (case_id, pack(case)))
            self.log(case_id, 'created', {})
        return case

    @staticmethod
    def validate_facts(facts):
        allowed = {'streamlit_version', 'python_version', 'os', 'browser', 'location',
                   'proxy', 'websocket_status', 'reproduction', 'error', 'resolved'}
        if not isinstance(facts, dict) or not set(facts) <= allowed:
            raise StoreError('INVALID_FACTS')
        for key, value in facts.items():
            valid = isinstance(value, bool) if key == 'resolved' else (
                value is None or isinstance(value, str) and len(value) <= 2000)
            if not valid:
                raise StoreError('INVALID_FACT_VALUE')

    def update(self, case_id, message, facts=None, check=None):
        """اطلاعات تازه را فقط کاربر ثبت می‌کند؛ مدل نمی‌تواند تأیید حل مشکل بسازد."""
        self.validate_facts(facts or {})
        if check and (set(check) != {'name', 'result'} or
                      not all(isinstance(v, str) for v in check.values())):
            raise StoreError('INVALID_CHECK')
        with self.transaction():
            case = self.read(case_id)
            case['history'].append({'message': message, 'facts': facts or {}, 'check': check})
            case['facts'].update(facts or {})
            if check:
                case['checks'].append(check)
            case['revision'] += 1
            case['turn'] += 1  # نوبت جدید؛ checkpoint قبلی دیگر فعال نیست.
            case['summary'], case['unknowns'] = {}, []
            self.save(case)
            self.db.execute("UPDATE proposals SET status='stale' WHERE case_id=? AND status IN ('pending','approved')", (case_id,))
            self.log(case_id, 'updated', {'fields': list(facts or {}), 'turn': case['turn']})
        return case

    def remember(self, case_id, revision, **values):
        with self.transaction():
            case = self.read(case_id)
            if case['revision'] != revision:
                raise StoreError('STALE_ANALYSIS')
            if not set(values) <= {'sources', 'summary', 'unknowns'}:
                raise StoreError('INVALID_MEMORY')
            case.update(values)
            self.save(case)

    @staticmethod
    def validate_payload(payload, case):
        if not isinstance(payload, dict) or not payload or not set(payload) <= {'comment', 'state', 'labels'}:
            raise StoreError('INVALID_ACTION')
        if 'comment' in payload and (not isinstance(payload['comment'], str) or
                not payload['comment'].strip() or len(payload['comment']) > 12000):
            raise StoreError('INVALID_COMMENT')
        if 'state' in payload and payload['state'] not in {'open', 'closed'}:
            raise StoreError('INVALID_STATE')
        if payload.get('state') == 'closed' and case['facts'].get('resolved') is not True:
            raise StoreError('RESOLUTION_NOT_CONFIRMED')
        if 'labels' in payload and (not isinstance(payload['labels'], list) or
                len(payload['labels']) > 10 or not all(isinstance(v, str) and
                re.fullmatch(r'[a-z0-9_-]{1,40}', v) for v in payload['labels'])):
            raise StoreError('INVALID_LABELS')

    def proposal(self, case_id, proposal_id):
        row = self.db.execute('SELECT * FROM proposals WHERE id=? AND case_id=?',
                              (proposal_id, case_id)).fetchone()
        if not row:
            raise StoreError('PROPOSAL_NOT_IN_CASE')
        result = dict(row)
        result['payload'] = json.loads(result['payload'])
        return result

    def propose(self, case_id, revision, payload, request_key):
        with self.transaction():
            old = self.db.execute('SELECT id,case_id FROM proposals WHERE request_key=?', (request_key,)).fetchone()
            if old:  # تکرار همان tool call یا ویرایش پس از restart
                return self.proposal(case_id, old['id'])
            case = self.read(case_id)
            if revision != case['revision']:
                raise StoreError('STALE_ANALYSIS')
            self.validate_payload(payload, case)
            self.db.execute("UPDATE proposals SET status='superseded' WHERE case_id=? AND status IN ('pending','approved')", (case_id,))
            cur = self.db.execute('INSERT INTO proposals(case_id,revision,payload,hash,request_key) VALUES(?,?,?,?,?)',
                                  (case_id, revision, pack(payload), digest(payload), request_key))
            self.log(case_id, 'proposed', {'proposal_id': cur.lastrowid})
        return self.proposal(case_id, cur.lastrowid)

    def review(self, case_id, proposal_id, choice, expected_hash):
        """از مسیر تصمیم انسان فراخوانی می‌شود؛ این تابع ابزار مدل نیست."""
        with self.transaction():
            p = self.proposal(case_id, proposal_id)
            if expected_hash != p['hash'] or digest(p['payload']) != p['hash']:
                raise StoreError('HASH_CHANGED')
            if p['revision'] != self.read(case_id)['revision']:
                raise StoreError('STALE_PROPOSAL')
            target = {'approve': 'approved', 'reject': 'rejected'}.get(choice)
            if target is None or p['status'] not in {'pending', target}:
                raise StoreError('INVALID_REVIEW')
            self.db.execute('UPDATE proposals SET status=?,approved_hash=? WHERE id=?',
                            (target, p['hash'] if choice == 'approve' else None, proposal_id))
            self.log(case_id, 'human_' + target, {'proposal_id': proposal_id})

    def receipt(self, proposal_id):
        row = self.db.execute('SELECT result FROM receipts WHERE id=?', (proposal_id,)).fetchone()
        return json.loads(row['result']) if row else None

    def execute(self, case_id, proposal_id, fault=None):
        """تغییر و رسید در یک تراکنش؛ fault فقط برای آزمون محلی است."""
        with self.transaction():
            p = self.proposal(case_id, proposal_id)
            old = self.receipt(proposal_id)
            if old:
                self.log(case_id, 'duplicate_receipt', {'proposal_id': proposal_id})
                return old
            case = self.read(case_id)
            if p['status'] != 'approved' or p['approved_hash'] != digest(p['payload']):
                raise StoreError('HUMAN_APPROVAL_REQUIRED')
            if p['revision'] != case['revision']:
                raise StoreError('STALE_PROPOSAL')
            self.validate_payload(p['payload'], case)
            if fault == 'before':
                raise StoreError('TEST_FAILURE_BEFORE_COMMIT')
            if 'comment' in p['payload']:
                case['comments'].append({'proposal_id': proposal_id, 'body': p['payload']['comment']})
            for key in ['state', 'labels']:
                if key in p['payload']:
                    case[key] = p['payload'][key]
            case['revision'] += 1
            self.save(case)
            result = dict(applied=True, case_id=case_id, proposal_id=proposal_id,
                          state=case['state'], comment_count=len(case['comments']))
            self.db.execute('INSERT INTO receipts VALUES(?,?)', (proposal_id, pack(result)))
            self.db.execute("UPDATE proposals SET status='executed' WHERE id=?", (proposal_id,))
            self.log(case_id, 'executed', result)
        if fault == 'after':
            raise StoreError('TEST_RESPONSE_LOST_AFTER_COMMIT')
        return result

    def audit(self, case_id):
        return [dict(r) for r in self.db.execute('SELECT * FROM audit WHERE case_id=? ORDER BY id', (case_id,))]
