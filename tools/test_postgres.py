"""Opt-in Supabase integration check. Financial fixtures are rolled back."""
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.update(json.loads((ROOT / '.env.cloud.json').read_text()))
from backend import cloud

origin = os.environ['APP_ORIGIN']
client = cloud.app.test_client()
def get(path):
    return client.get(path, base_url=origin)
def post(path, data, csrf=None, method='POST'):
    headers = {'Origin':origin}
    if csrf: headers['X-CSRF-Token'] = csrf
    return client.open(path, method=method, json=data, headers=headers, base_url=origin)
def ok(response):
    assert response.status_code == 200, (response.status_code, response.json)
    return response.json

password = (ROOT / 'data/owner-login.txt').read_text().split('Temporary password: ')[1].splitlines()[0]
assert get('/api/records').status_code == 401
assert len(ok(get('/api/public/projects'))) == 3
csrf = ok(post('/api/login', {'password':password}))['csrf']
print('Real Supabase Auth login and owner session passed.')

class RollbackDatabase(cloud.Database):
    def commit(self):
        pass

connection = psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row, prepare_threshold=None)
database = RollbackDatabase(connection)
@contextmanager
def fixture_db():
    yield database
try:
    with patch.object(cloud,'db',fixture_db), patch.object(cloud.local,'db',fixture_db):
        job = ok(post('/api/jobs',{'name':'Integration fixture','client':'Disposable test','fee':'3000'},csrf))['id']
        invoice = ok(post('/api/invoices',{'job_id':job,'number':'INTEGRATION-ROLLBACK','issue_date':'2026-09-27','due_date':'2026-10-11','amount':'1500'},csrf))['id']
        ok(post('/api/payments',{'invoice_id':invoice,'date':'2026-09-27','amount':'750','method':'Transfer'},csrf))
        ok(post('/api/expenses',{'date':'2026-09-27','payee':'Test','category':'Tools','amount':'200','business_percent':50},csrf))
        summary = ok(get('/api/records?year=2026'))['summary']
        assert (summary['received'], summary['expenses'], summary['net_cash'], summary['outstanding']) == (75000,10000,65000,75000), summary
        assert b'750.00' in get('/api/export?type=payments&year=2026').data
        assert len(ok(get('/api/audit'))) >= 4
    print('PostgreSQL financial calculations, CSV and audit passed; fixtures rolled back.')
finally:
    connection.rollback()
    connection.close()

backup = ok(get('/api/backup'))
assert all(not backup['tables'][table] for table in ('jobs','invoices','payments','expenses','audit'))
assert len(backup['tables']['projects']) == 3
ok(post('/api/logout',{},csrf))
assert not ok(get('/api/session'))['authenticated']
print('Real backup snapshot and logout passed; no financial test records saved.')
