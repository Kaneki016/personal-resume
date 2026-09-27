"""Vercel adapter: Supabase Auth/Storage and PostgreSQL, sharing local validation."""
import base64
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from decimal import Decimal
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import psycopg
from psycopg.rows import dict_row
from flask import Flask, Response, redirect, request, send_file
from werkzeug.exceptions import RequestEntityTooLarge
from backend import server as local

TABLES = ('projects', 'jobs', 'invoices', 'payments', 'expenses', 'audit')

def required(name):
    value = os.environ.get(name, '').strip()
    if not value:
        raise RuntimeError('Cloud configuration is incomplete.')
    return value

class Row(dict):
    def __init__(self, values):
        # PostgreSQL SUM(bigint) is numeric. Preserve exact integer sen in JSON.
        super().__init__({key: int(value) if isinstance(value, Decimal) and value == value.to_integral_value() else value
                          for key, value in values.items()})
    def __getitem__(self, key):
        return list(self.values())[key] if isinstance(key, int) else super().__getitem__(key)

class Cursor:
    def __init__(self, cursor, lastrowid=None):
        self.cursor, self.lastrowid = cursor, lastrowid
    def fetchone(self):
        row = self.cursor.fetchone()
        return Row(row) if row is not None else None
    def __iter__(self):
        return (Row(row) for row in self.cursor)

class Database:
    def __init__(self, connection):
        self.connection = connection
        self.started = False
    def execute(self, sql, args=()):
        if not self.started:
            self.connection.execute('SET LOCAL search_path TO portfolio')
            self.started = True
        sql = sql.replace('?', '%s')
        returning = re.match(r'INSERT INTO (projects|jobs|invoices|payments|expenses)\s', sql, re.I)
        if returning:
            sql += ' RETURNING id'
        try:
            cursor = self.connection.execute(sql, args)
            return Cursor(cursor, cursor.fetchone()['id'] if returning else None)
        except psycopg.IntegrityError as error:
            raise sqlite3.IntegrityError('Invalid linked record or duplicate invoice.') from error
    def commit(self):
        self.connection.commit()
        self.started = False

@contextmanager
def db():
    with psycopg.connect(required('DATABASE_URL'), row_factory=dict_row,
                         prepare_threshold=None, connect_timeout=10) as connection:
        yield Database(connection)

local.db = db

class SupabaseError(Exception):
    def __init__(self, status):
        self.status = status

def supabase(path, method='GET', data=None, token=None, content_type='application/json'):
    key = required('SUPABASE_SERVICE_ROLE_KEY')
    body = data if isinstance(data, bytes) else json.dumps(data).encode() if data is not None else None
    headers = {'apikey': key, 'Authorization': 'Bearer ' + (token or key), 'Content-Type': content_type}
    try:
        with urlopen(Request(required('SUPABASE_URL').rstrip('/') + path, data=body,
                             headers=headers, method=method), timeout=20) as response:
            raw = response.read()
            return json.loads(raw) if 'json' in response.headers.get('Content-Type', '') else raw
    except HTTPError as error:
        raise SupabaseError(error.code) from None

def origins():
    result = {required('APP_ORIGIN').rstrip('/')}
    # Preview URLs are assigned by Vercel, never taken from request headers.
    if os.environ.get('VERCEL_URL'):
        result.add('https://' + os.environ['VERCEL_URL'])
    return result

class CloudHandler(local.Handler):
    def __init__(self):
        self.path = request.full_path.rstrip('?')
        self.headers = request.headers
        self.command = request.method
        self.rfile = io.BytesIO(request.get_data())
        self.client_address = (request.remote_addr or 'unknown', 0)
        self.response = None
    def host_ok(self):
        return self.headers.get('Host') in {urlsplit(origin).netloc for origin in origins()}
    def origin_ok(self):
        return self.headers.get('Origin') in origins()
    def send(self, status, body=b'', mime='application/json; charset=utf-8', extra=None):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.response = Response(body, status=status, content_type=mime)
        for key, value in (extra or {}).items():
            if key == 'Set-Cookie':
                value += '; Secure' if required('APP_ORIGIN').startswith('https://') else ''
            self.response.headers[key] = value
    def session(self, c):
        if self.command in ('POST', 'PUT'):
            # Serialise owner writes across serverless instances, including linked-record checks.
            c.execute('SELECT pg_advisory_xact_lock(271827182)')
        return super().session(c)
    def do_GET(self):
        route = urlsplit(self.path).path
        if route == '/api/session':
            if not self.host_ok():
                return self.fail(403, 'Invalid host.')
            with db() as c:
                session = self.session(c)
                return self.send(200, {'setup': False, 'authenticated': bool(session),
                                      'csrf': session['csrf'] if session else None, 'cloud': True})
        if route.startswith('/media/'):
            if not self.host_ok():
                return self.fail(403, 'Invalid host.')
            name = route.removeprefix('/media/')
            if not re.fullmatch(r'[a-f0-9]{32}\.(jpg|png|webp)', name):
                return self.fail(404, 'Not found.')
            with db() as c:
                if not self.session(c) and not local.published_image(c, route):
                    return self.fail(404, 'Not found.')
            try:
                signed = supabase('/storage/v1/object/sign/portfolio-images/' + name, 'POST', {'expiresIn': 60})
                url = required('SUPABASE_URL').rstrip('/') + '/storage/v1' + signed['signedURL']
                return self.send(302, b'', extra={'Location': url})
            except SupabaseError:
                return self.fail(404, 'Image not found.')
        return super().do_GET()
    def login(self, c, route, data):
        if route == '/api/setup':
            return self.fail(403, 'Owner registration is managed privately in Supabase.')
        password = data.get('password', '')
        if not isinstance(password, str) or not 1 <= len(password) <= 256:
            return self.fail(401, 'Incorrect password.')
        now = int(time.time())
        c.execute('SELECT pg_advisory_xact_lock(271827183)')
        c.execute('DELETE FROM login_attempts WHERE attempted_at<?', (now - 300,))
        if c.execute('SELECT COUNT(*) FROM login_attempts').fetchone()[0] >= 10:
            return self.fail(429, 'Too many attempts. Please wait five minutes.')
        c.execute('INSERT INTO login_attempts(bucket,attempted_at) VALUES(?,?)', ('owner', now))
        c.commit()
        try:
            auth = supabase('/auth/v1/token?grant_type=password', 'POST',
                            {'email': required('OWNER_EMAIL'), 'password': password})
        except SupabaseError as error:
            return self.fail(401 if error.status in (400, 401, 422) else 503,
                             'Incorrect password.' if error.status in (400, 401, 422) else 'Sign-in is temporarily unavailable.')
        if auth.get('user', {}).get('id') != required('OWNER_USER_ID'):
            return self.fail(403, 'This account cannot access the workspace.')
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        c.execute('DELETE FROM login_attempts')
        c.execute('DELETE FROM sessions WHERE expires<?', (now,))
        c.execute('INSERT INTO sessions VALUES(?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), csrf, now + 28800))
        c.commit()
        return self.send(200, {'csrf': csrf}, extra={'Set-Cookie': f'portfolio_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=28800'})
    def mutate(self):
        if urlsplit(self.path).path != '/api/password':
            return super().mutate()
        if not self.host_ok() or not self.origin_ok():
            return self.fail(403, 'Same-origin request required.')
        with db() as c:
            session = self.session(c)
            if not session:
                return self.fail(401, 'Sign in to continue.')
            if not hmac.compare_digest(self.headers.get('X-CSRF-Token', ''), session['csrf']):
                return self.fail(403, 'Refresh the page and try again.')
            data = self.body()
            password = data.get('password')
            current = data.get('current')
            if not isinstance(password, str) or not 12 <= len(password) <= 256:
                return self.fail(400, 'Use a password with 12–256 characters.')
            if not isinstance(current, str) or not 1 <= len(current) <= 256:
                return self.fail(400, 'Current password is incorrect.')
            try:
                auth = supabase('/auth/v1/token?grant_type=password', 'POST', {'email': required('OWNER_EMAIL'), 'password': current})
                if auth.get('user', {}).get('id') != required('OWNER_USER_ID'):
                    return self.fail(403, 'Owner access required.')
                supabase('/auth/v1/user', 'PUT', {'password': password}, token=auth['access_token'])
            except SupabaseError:
                return self.fail(400, 'Could not change the password. Check your current password and try again.')
            c.execute('DELETE FROM sessions')
            c.commit()
            return self.send(200, {'ok': True}, extra={'Set-Cookie': 'portfolio_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0'})
    def upload(self, data):
        try:
            image = base64.b64decode(data.get('data', ''), validate=True)
        except Exception:
            raise ValueError('Invalid image.')
        if not 0 < len(image) <= 3 * 1024 * 1024:
            raise ValueError('Image must be smaller than 3 MB.')
        if image.startswith(b'\x89PNG\r\n\x1a\n'):
            ext, mime = 'png', 'image/png'
        elif image.startswith(b'\xff\xd8\xff'):
            ext, mime = 'jpg', 'image/jpeg'
        elif image[:4] == b'RIFF' and image[8:12] == b'WEBP':
            ext, mime = 'webp', 'image/webp'
        else:
            raise ValueError('Use a JPG, PNG or WebP image.')
        name = secrets.token_hex(16) + '.' + ext
        supabase('/storage/v1/object/portfolio-images/' + name, 'POST', image, content_type=mime)
        return self.send(200, {'url': '/media/' + name})
    def backup(self, c):
        # Stable database snapshot. Images are exported separately from Supabase Storage.
        c.commit()
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        payload = {'format': 'portfolio-postgres-v1', 'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                   'tables': {table: local.rows(c, 'SELECT * FROM ' + table + ' ORDER BY id') for table in TABLES}}
        payload['image_backup_note'] = 'Export portfolio-images from Supabase Storage separately. This file contains records, not image bytes or account credentials.'
        return self.send(200, payload, extra={'Content-Disposition': 'attachment; filename="portfolio-records-backup.json"'})

app = Flask(__name__, static_folder=None)
app.config['MAX_CONTENT_LENGTH'] = 4_400_000

@app.after_request
def security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob: https://*.supabase.co; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    if request.path.startswith('/admin') or (request.path.startswith('/api/') and not request.path.startswith('/api/public/')):
        response.headers['X-Robots-Tag'] = 'noindex, nofollow'
    return response

@app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT'])
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT'])
def dispatch(path):
    try:
        if request.host == 'lai-yoke-yau-resume.vercel.app':
            return redirect(required('APP_ORIGIN').rstrip('/') + request.full_path.rstrip('?'), code=308)
        if request.method == 'GET' and not path.startswith(('api/', 'media/')):
            if path in ('admin', 'admin/'):
                return send_file(local.PRIVATE / 'admin.html')
            if path in ('admin.js', 'admin.css'):
                return send_file(local.PRIVATE / path)
            target = (local.PUBLIC / (path or 'index.html')).resolve()
            if not target.is_relative_to(local.PUBLIC.resolve()) or any(part.startswith('.') for part in target.relative_to(local.PUBLIC.resolve()).parts) or not target.is_file():
                return Response('Not found.', status=404)
            return send_file(target)
        handler = CloudHandler()
        if request.method == 'GET':
            handler.do_GET()
        else:
            handler.mutate()
        return handler.response
    except (ValueError, TypeError):
        return {'error': 'Check the supplied values.'}, 400
    except RequestEntityTooLarge:
        return {'error': 'Request is too large. Images must be smaller than 3 MB.'}, 413
    except Exception:
        # Do not expose database URLs, auth responses or private data in errors.
        return {'error': 'The workspace is temporarily unavailable. Please try again.'}, 503
