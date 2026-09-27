"""Cloud HTTP/security regressions with isolated records and a fake auth provider."""
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import cloud

class TestDatabase:
    def __init__(self, conn): self.conn = conn
    def execute(self, query, args=()):
        if query.startswith(('SELECT pg_advisory', 'SET TRANSACTION')):
            return self.conn.execute('SELECT 1')
        return self.conn.execute(query, args)
    def commit(self): self.conn.commit()

class CloudTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'fixture.sqlite3'
        with sqlite3.connect(self.path) as conn:
            conn.executescript((ROOT / 'backend/schema.sql').read_text())
            conn.execute('CREATE TABLE login_attempts(bucket TEXT, attempted_at INTEGER)')
            conn.execute("INSERT INTO projects(title,category,summary,published) VALUES('Published','Client work','Example',1)")
        conn.close()
        @contextmanager
        def db():
            conn = sqlite3.connect(self.path)
            conn.row_factory = sqlite3.Row
            try:
                with conn: yield TestDatabase(conn)
            finally: conn.close()
        self.env = patch.dict(os.environ, {'APP_ORIGIN':'https://portfolio.example', 'OWNER_EMAIL':'owner@example.com', 'OWNER_USER_ID':'owner-id', 'SUPABASE_URL':'https://example.supabase.co', 'SUPABASE_SERVICE_ROLE_KEY':'fake-server-key'}, clear=True)
        self.env.start()
        self.cloud_db = patch.object(cloud, 'db', db); self.cloud_db.start()
        self.local_db = patch.object(cloud.local, 'db', db); self.local_db.start()
        self.auth = patch.object(cloud, 'supabase', side_effect=self.provider); self.mock_auth = self.auth.start()
        self.client = cloud.app.test_client()
        self.origin = 'https://portfolio.example'
    def tearDown(self):
        self.auth.stop(); self.local_db.stop(); self.cloud_db.stop(); self.env.stop(); self.temp.cleanup()
    def provider(self, path, method='GET', data=None, **kwargs):
        if path.startswith('/auth/v1/token'):
            if data['password'] != 'Example-owner-password-2026': raise cloud.SupabaseError(400)
            return {'user':{'id':'owner-id'}, 'access_token':'fake-token'}
        if path.startswith('/storage/v1/object/sign/'):
            return {'signedURL':'/object/sign/portfolio-images/example.png?token=fake'}
        return {'ok':True}
    def get(self, path): return self.client.get(path, base_url=self.origin, buffered=True)
    def post(self, path, body, csrf=None, origin=None, method='POST'):
        headers = {'Origin': origin or self.origin}
        if csrf: headers['X-CSRF-Token'] = csrf
        return self.client.open(path, method=method, json=body, base_url=self.origin, headers=headers)
    def login(self):
        response = self.post('/api/login', {'password':'Example-owner-password-2026'})
        self.assertEqual(response.status_code, 200)
        return response.json['csrf']
    def test_public_and_admin_indexing(self):
        legacy = self.client.get('/?from=resume', base_url='https://lai-yoke-yau-resume.vercel.app')
        self.assertEqual(legacy.status_code, 308)
        self.assertEqual(legacy.headers['Location'], self.origin + '/?from=resume')
        response = self.get('/')
        self.assertEqual(response.status_code,200)
        self.assertNotIn('X-Robots-Tag', response.headers)
        self.assertEqual(self.get('/admin').headers['X-Robots-Tag'], 'noindex, nofollow')
        self.assertIn(b'noindex,nofollow', self.get('/admin').data)
        self.assertEqual(self.get('/api/records').status_code,401)
        self.assertEqual(self.get('/api/backup').status_code,401)
        for path in ['/backend/cloud.py','/.env','/data/portfolio.sqlite3','/contact.html','/pricing.html']:
            self.assertEqual(self.get(path).status_code,404)
    def test_closed_signup_and_owner_only(self):
        self.assertFalse(self.get('/api/session').json['setup'])
        self.assertEqual(self.post('/api/setup',{'password':'example'}).status_code,403)
        self.mock_auth.side_effect = lambda *a,**kw: {'user':{'id':'different-user'}}
        self.assertEqual(self.post('/api/login',{'password':'example'}).status_code,403)
    def test_host_origin_csrf_and_cookie(self):
        self.assertEqual(self.client.get('/api/session',base_url='https://attacker.example').status_code,403)
        self.assertEqual(self.post('/api/login',{'password':'x'},origin='https://attacker.example').status_code,403)
        response = self.post('/api/login',{'password':'Example-owner-password-2026'})
        for flag in ['Secure','HttpOnly','SameSite=Strict']: self.assertIn(flag,response.headers['Set-Cookie'])
        self.assertEqual(self.post('/api/jobs',{}).status_code,403)
    def test_login_rate_limit(self):
        for _ in range(10): self.assertEqual(self.post('/api/login',{'password':'wrong'}).status_code,401)
        self.assertEqual(self.post('/api/login',{'password':'wrong'}).status_code,429)
    def test_financial_records_and_backup(self):
        csrf=self.login()
        job=self.post('/api/jobs',{'name':'Fixture','client':'Example','fee':'3000'},csrf).json['id']
        invoice=self.post('/api/invoices',{'job_id':job,'number':'QA-1','issue_date':'2026-09-27','due_date':'2026-10-11','amount':'1500'},csrf).json['id']
        self.assertEqual(self.post('/api/payments',{'invoice_id':invoice,'date':'2026-09-27','amount':'750','method':'Transfer'},csrf).status_code,200)
        self.assertEqual(self.post('/api/expenses',{'date':'2026-09-27','payee':'Example','category':'Tools','amount':'200','business_percent':50},csrf).status_code,200)
        summary=self.get('/api/records?year=2026').json['summary']
        self.assertEqual((summary['received'],summary['expenses'],summary['net_cash'],summary['outstanding']),(75000,10000,65000,75000))
        backup=self.get('/api/backup')
        self.assertEqual(backup.json['format'],'portfolio-postgres-v1')
        self.assertNotIn('sessions',backup.json['tables'])
        self.assertNotIn('settings',backup.json['tables'])
        self.assertIn(b'750.00',self.get('/api/export?type=payments&year=2026').data)
    def test_draft_and_image_privacy(self):
        csrf=self.login()
        name='a'*32+'.png'
        draft={'title':'Draft','category':'Client work','summary':'Draft summary','image':'/media/'+name,'published':0}
        ident=self.post('/api/projects',draft,csrf).json['id']
        self.post('/api/logout',{},csrf)
        self.assertEqual(len(self.get('/api/public/projects').json),1)
        self.assertEqual(self.get('/media/'+name).status_code,404)
        csrf=self.login()
        draft['published']=1
        self.assertEqual(self.post('/api/projects/'+str(ident),draft,csrf,method='PUT').status_code,200)
        self.post('/api/logout',{},csrf)
        self.assertEqual(self.get('/media/'+name).status_code,302)
    def test_password_change_clears_sessions(self):
        csrf=self.login()
        response=self.post('/api/password',{'current':'Example-owner-password-2026','password':'Another-secure-password-2026'},csrf)
        self.assertEqual(response.status_code,200)
        self.assertFalse(self.get('/api/session').json['authenticated'])

if __name__ == '__main__': unittest.main()
