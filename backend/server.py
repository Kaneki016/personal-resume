"""Local, single-owner portfolio and bookkeeping server. Python 3.10+, no packages required."""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, unquote
from decimal import Decimal, InvalidOperation
from datetime import date
import argparse, base64, csv, hashlib, hmac, io, json, mimetypes, os, re, secrets, sqlite3, time, threading, zipfile

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / 'dist'
PRIVATE = ROOT / 'private'
DATA = Path(os.environ.get('PORTFOLIO_DATA_DIR', ROOT / 'data')).resolve()
LOCK = threading.RLock()
ATTEMPTS = {}
PORT = 4317

def db():
    c = sqlite3.connect(DATA / 'portfolio.sqlite3', timeout=10)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c

def init():
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / 'uploads').mkdir(exist_ok=True)
    with db() as c:
        c.executescript((ROOT/'backend/schema.sql').read_text())
        if not c.execute("SELECT 1 FROM settings WHERE key='seeded'").fetchone():
            seed=json.loads((ROOT/'backend/seed.json').read_text(encoding='utf-8'))
            for p in seed['projects']:
                fields=list(p)
                c.execute(f"INSERT INTO projects ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})",list(p.values()))
            c.execute('INSERT INTO settings VALUES (?,?)',('seeded','1'))
        c.execute('DELETE FROM sessions WHERE expires<?',(int(time.time()),))

def rows(c, sql, args=()): return [dict(r) for r in c.execute(sql,args)]
def setting(c,key):
    r=c.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
    return r['value'] if r else None
def text(v, name, limit=1000, required=True):
    if not isinstance(v,str): raise ValueError(f'{name} must be text.')
    v=v.strip()
    if (required and not v) or len(v)>limit: raise ValueError(f'Check {name} (maximum {limit} characters).')
    return v
def cents(v):
    try:
        n=Decimal(str(v))
        if not n.is_finite() or n<0 or n>Decimal('99999999.99') or n*100!=(n*100).to_integral(): raise ValueError()
        return int(n*100)
    except (InvalidOperation, ValueError): raise ValueError('Enter a non-negative amount with at most two decimal places.')
def integer(v,low=0,high=999999999):
    if isinstance(v,bool): raise ValueError('Invalid integer.')
    try: n=int(v)
    except (ValueError,TypeError): raise ValueError('Invalid integer.')
    if str(n)!=str(v) or not low<=n<=high: raise ValueError('Invalid integer.')
    return n
def day(v):
    if not isinstance(v,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',v): raise ValueError('Use a valid date.')
    d=date.fromisoformat(v)
    if not 2000<=d.year<=2100: raise ValueError('Date must be between 2000 and 2100.')
    return v
def audit(c,action,entity,entity_id,before,after):
    c.execute('INSERT INTO audit(action,entity,entity_id,before_json,after_json) VALUES(?,?,?,?,?)',
        (action,entity,entity_id,json.dumps(before) if before else None,json.dumps(after) if after else None))
def clean_project(d):
    p={k:text(d.get(k,''),k,limit,k in ('title','category','summary')) for k,limit in [('title',140),('category',60),('summary',700),('details',6000),('tags',300),('url',1000),('image',300)]}
    if p['url'] and (urlsplit(p['url']).scheme not in ('http','https') or not urlsplit(p['url']).netloc): raise ValueError('Project link must be an http or https URL.')
    if p['image'] and not (re.fullmatch(r'/media/[a-f0-9]{32}\.(jpg|png|webp)',p['image']) or re.fullmatch(r'/assets/images/[a-zA-Z0-9_./-]+',p['image'])): raise ValueError('Upload an image or use an existing site asset.')
    if '..' in p['image']: raise ValueError('Invalid image path.')
    p['published']=integer(d.get('published',0),0,1)
    p['position']=integer(d.get('position',0),0,999)
    return p

class Handler(BaseHTTPRequestHandler):
    server_version='PortfolioLocal/1.0'
    def log_message(self,fmt,*args):
        # Do not log cookies, passwords, bodies, private records or URL queries.
        print(f'{self.command} {urlsplit(self.path).path} {args[1] if len(args)>1 else ""}',flush=True)
    def send(self,status,body=b'',mime='application/json; charset=utf-8',extra=None):
        if not isinstance(body,bytes): body=json.dumps(body,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)))
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','strict-origin-when-cross-origin')
        self.send_header('Cache-Control','no-store')
        route=urlsplit(self.path).path
        if route in ('/admin','/admin/','/admin.js','/admin.css') or (route.startswith('/api/') and not route.startswith('/api/public/')):
            self.send_header('X-Robots-Tag','noindex, nofollow')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        for k,v in (extra or {}).items():self.send_header(k,v)
        self.end_headers();self.wfile.write(body)
    def fail(self,status,message):self.send(status,{'error':message})
    def host_ok(self):return self.headers.get('Host') in (f'127.0.0.1:{PORT}',f'localhost:{PORT}')
    def origin_ok(self):return self.headers.get('Origin') in (f'http://127.0.0.1:{PORT}',f'http://localhost:{PORT}')
    def session(self,c):
        try:
            cookies=SimpleCookie(self.headers.get('Cookie','')); token=cookies['portfolio_session'].value
        except (KeyError,ValueError):return None
        return c.execute('SELECT * FROM sessions WHERE token_hash=? AND expires>?',(hashlib.sha256(token.encode()).hexdigest(),int(time.time()))).fetchone()
    def body(self):
        if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('JSON request required.')
        size=int(self.headers.get('Content-Length','0'))
        if not 0<size<=6*1024*1024:raise ValueError('Request is empty or exceeds 6 MB.')
        data=json.loads(self.rfile.read(size))
        if not isinstance(data,dict):raise ValueError('JSON object required.')
        return data
    def do_GET(self):
        if not self.host_ok():return self.fail(403,'Invalid host.')
        try:
            with db() as c:
                route=urlsplit(self.path).path
                if route=='/api/public/projects':return self.send(200,rows(c,'SELECT id,title,category,summary,details,tags,url,image,position FROM projects WHERE published=1 ORDER BY position,id'))
                if route=='/api/session':
                    s=self.session(c)
                    return self.send(200,{'setup':not bool(setting(c,'password')),'authenticated':bool(s),'csrf':s['csrf'] if s else None})
                if route.startswith('/api/'):
                    if not self.session(c):return self.fail(401,'Sign in to continue.')
                    if route=='/api/projects':return self.send(200,rows(c,'SELECT * FROM projects ORDER BY position,id'))
                    if route=='/api/records':return self.send(200,self.records(c))
                    if route=='/api/audit':return self.send(200,rows(c,'SELECT id,recorded_at,action,entity,entity_id FROM audit ORDER BY id DESC LIMIT 100'))
                    if route=='/api/export':return self.export(c)
                    if route=='/api/backup':return self.backup(c)
                    return self.fail(404,'Not found.')
                if route.startswith('/media/'):
                    name=route.removeprefix('/media/')
                    if not re.fullmatch(r'[a-f0-9]{32}\.(jpg|png|webp)',name):return self.fail(404,'Not found.')
                    # A draft's image is private until at least one published project uses it.
                    if not self.session(c) and not c.execute('SELECT 1 FROM projects WHERE image=? AND published=1',(route,)).fetchone():return self.fail(404,'Not found.')
                    return self.file(DATA/'uploads'/name)
                if route in ('/admin','/admin/'):
                    return self.file(PRIVATE/'admin.html')
                if route in ('/admin.js','/admin.css'):return self.file(PRIVATE/route[1:])
                route='/index.html' if route=='/' else unquote(route)
                path=(PUBLIC/route.lstrip('/')).resolve()
                if not path.is_relative_to(PUBLIC.resolve()) or any(part.startswith('.') for part in path.relative_to(PUBLIC.resolve()).parts):return self.fail(404,'Not found.')
                self.file(path)
        except (ValueError,TypeError) as e:self.fail(400,str(e))
        except Exception:self.fail(500,'Unable to load this resource. Please try again.')
    def file(self,path):
        if not path.is_file():return self.fail(404,'Not found.')
        mime=mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        self.send(200,path.read_bytes(),mime)
    def records(self,c):
        year=integer(parse_qs(urlsplit(self.path).query).get('year',[str(date.today().year)])[0],2000,2100)
        start,end=f'{year}-01-01',f'{year+1}-01-01'
        invoices=rows(c,'''SELECT i.*,j.name AS job_name,j.client,COALESCE((SELECT SUM(p.amount_cents) FROM payments p WHERE p.invoice_id=i.id AND p.void=0),0) AS paid_cents FROM invoices i JOIN jobs j ON j.id=i.job_id ORDER BY i.issue_date DESC,i.id DESC''')
        payments=rows(c,'''SELECT p.*,i.number,j.name AS job_name,j.client FROM payments p JOIN invoices i ON i.id=p.invoice_id JOIN jobs j ON j.id=i.job_id ORDER BY p.date DESC,p.id DESC''')
        expenses=rows(c,'SELECT * FROM expenses ORDER BY date DESC,id DESC')
        received=sum(p['amount_cents'] for p in payments if not p['void'] and start<=p['date']<end)
        spent=sum((e['amount_cents']*e['business_percent']+50)//100 for e in expenses if not e['void'] and start<=e['date']<end)
        outstanding=sum(max(0,i['amount_cents']-i['paid_cents']) for i in invoices if not i['void'])
        credit=sum(max(0,i['paid_cents']-i['amount_cents']) for i in invoices if not i['void'])
        return {'year':year,'jobs':rows(c,'SELECT * FROM jobs ORDER BY id DESC'),'invoices':invoices,'payments':payments,'expenses':expenses,
            'summary':{'received':received,'expenses':spent,'net_cash':received-spent,'outstanding':outstanding,'credit':credit,
            'invoiced':sum(i['amount_cents'] for i in invoices if not i['void'] and start<=i['issue_date']<end)}}
    def export(self,c):
        q=parse_qs(urlsplit(self.path).query);kind=q.get('type',['payments'])[0]
        if kind not in ('jobs','invoices','payments','expenses','audit'):raise ValueError('Unknown export type.')
        year=integer(q.get('year',[str(date.today().year)])[0],2000,2100)
        if kind=='audit': data=rows(c,'SELECT * FROM audit ORDER BY id');fields=['id','recorded_at','action','entity','entity_id','before_json','after_json']
        else:
            data=self.records(c)[kind]
            if kind!='jobs':
                datekey='issue_date' if kind=='invoices' else 'date'
                data=[r for r in data if r[datekey].startswith(str(year)+'-')]
            fields={'jobs':['id','name','client','fee_cents','status','notes','created_at'],
                'invoices':['id','job_id','number','client','job_name','issue_date','due_date','amount_cents','paid_cents','description','void'],
                'payments':['id','invoice_id','number','client','job_name','date','amount_cents','method','reference','notes','void'],
                'expenses':['id','date','payee','category','amount_cents','business_percent','reference','notes','void']}[kind]
        def safe(v):
            v='' if v is None else str(v)
            return "'"+v if v.lstrip().startswith(('=','+','-','@','\t','\r','\n')) else v
        buf=io.StringIO(newline='');writer=csv.writer(buf)
        writer.writerow([f.replace('_cents','_MYR') for f in fields]+(['currency'] if kind!='audit' else []))
        for row in data:
            vals=[f'{row.get(f,0)/100:.2f}' if f.endswith('_cents') else safe(row.get(f)) for f in fields]
            writer.writerow(vals+(['MYR'] if kind!='audit' else []))
        self.send(200,b'\xef\xbb\xbf'+buf.getvalue().encode('utf-8'),'text/csv; charset=utf-8',{'Content-Disposition':f'attachment; filename="{kind}-{year}.csv"'})
    def backup(self,c):
        memory=sqlite3.connect(':memory:');c.backup(memory)
        memory.execute('DELETE FROM sessions');memory.commit()
        blob=io.BytesIO()
        with zipfile.ZipFile(blob,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('portfolio.sqlite3',memory.serialize())
            for f in (DATA/'uploads').iterdir():
                if f.is_file():z.write(f,'uploads/'+f.name)
        memory.close()
        self.send(200,blob.getvalue(),'application/zip',{'Content-Disposition':f'attachment; filename="portfolio-private-backup-{date.today()}.zip"'})
    def do_POST(self):self.mutate()
    def do_PUT(self):self.mutate()
    def mutate(self):
        if not self.host_ok() or not self.origin_ok():return self.fail(403,'Same-origin request required.')
        try:
            data=self.body();route=urlsplit(self.path).path
            with LOCK, db() as c:
                if route in ('/api/setup','/api/login') and self.command=='POST':return self.login(c,route,data)
                s=self.session(c)
                if not s:return self.fail(401,'Sign in to continue.')
                if not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),s['csrf']):return self.fail(403,'Refresh the page and try again.')
                if route=='/api/logout':
                    c.execute('DELETE FROM sessions WHERE token_hash=?',(s['token_hash'],));c.commit()
                    return self.send(200,{'ok':True},extra={'Set-Cookie':'portfolio_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0'})
                if route=='/api/password':
                    if not self.password_matches(c,data.get('current','')):return self.fail(400,'Current password is incorrect.')
                    self.set_password(c,data.get('password'));c.execute('DELETE FROM sessions');c.commit();return self.send(200,{'ok':True})
                if route=='/api/upload':return self.upload(data)
                match=re.fullmatch(r'/api/(projects|jobs|invoices|payments|expenses)(?:/(\d+))?',route)
                if not match:return self.fail(404,'Not found.')
                entity,id_=match.groups();id_=int(id_) if id_ else None
                if (id_ is None and self.command!='POST') or (id_ is not None and self.command!='PUT'):return self.fail(405,'Use POST to create or PUT to update.')
                before=dict(c.execute(f'SELECT * FROM {entity} WHERE id=?',(id_,)).fetchone() or {}) if id_ else None
                if id_ and not before:return self.fail(404,'Record not found.')
                if entity=='projects':record=clean_project(data)
                elif entity=='jobs':
                    status=data.get('status','active')
                    if status not in ('active','complete','cancelled'):raise ValueError('Invalid project status.')
                    record={'name':text(data.get('name'),'project name',160),'client':text(data.get('client'),'client',160),'fee_cents':cents(data.get('fee')),'status':status,'notes':text(data.get('notes',''),'notes',3000,False)}
                elif entity=='invoices':
                    record={'job_id':integer(data.get('job_id'),1),'number':text(data.get('number'),'invoice number',80),'issue_date':day(data.get('issue_date')),'due_date':day(data.get('due_date')),'amount_cents':cents(data.get('amount')),'description':text(data.get('description',''),'description',2000,False),'void':integer(data.get('void',0),0,1)}
                    if record['due_date']<record['issue_date']:raise ValueError('Due date cannot precede issue date.')
                    paid=c.execute('SELECT COUNT(*) FROM payments WHERE invoice_id=? AND void=0',(id_,)).fetchone()[0] if id_ else 0
                    if paid and (record['void'] or record['job_id']!=before['job_id']):raise ValueError('Void or reassign its payments before voiding or reassigning this invoice.')
                elif entity=='payments':
                    record={'invoice_id':integer(data.get('invoice_id'),1),'date':day(data.get('date')),'amount_cents':cents(data.get('amount')),'method':text(data.get('method'),'payment method',80),'reference':text(data.get('reference',''),'reference',300,False),'notes':text(data.get('notes',''),'notes',2000,False),'void':integer(data.get('void',0),0,1)}
                    inv=c.execute('SELECT * FROM invoices WHERE id=?',(record['invoice_id'],)).fetchone()
                    if not inv or (inv['void'] and not record['void']):raise ValueError('Choose an active invoice.')
                else:
                    record={'date':day(data.get('date')),'payee':text(data.get('payee'),'payee',160),'category':text(data.get('category'),'category',80),'amount_cents':cents(data.get('amount')),'business_percent':integer(data.get('business_percent',100),0,100),'reference':text(data.get('reference',''),'receipt reference',300,False),'notes':text(data.get('notes',''),'notes',2000,False),'void':integer(data.get('void',0),0,1)}
                if 'amount_cents' in record and record['amount_cents']<=0:raise ValueError('Amount must be greater than zero.')
                fields=list(record)
                if id_:
                    c.execute(f"UPDATE {entity} SET {','.join(k+'=?' for k in fields)} WHERE id=?",[*record.values(),id_])
                else:
                    id_=c.execute(f"INSERT INTO {entity} ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})",list(record.values())).lastrowid
                audit(c,'update' if before else 'create',entity,id_,before,record);c.commit()
                return self.send(200,{'id':id_})
        except sqlite3.IntegrityError:self.fail(400,'Check the linked project/invoice and use a unique invoice number.')
        except (ValueError,TypeError,KeyError) as e:self.fail(400,str(e))
        except Exception:self.fail(500,'Save failed. Your entered details have been kept on this page. Try again.')
    def password_matches(self,c,password):
        saved=setting(c,'password')
        if not saved or not isinstance(password,str) or len(password)>256:return False
        salt,digest=saved.split(':')
        return hmac.compare_digest(hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),600000).hex(),digest)
    def set_password(self,c,password):
        if not isinstance(password,str) or not 12<=len(password)<=256:raise ValueError('Use a password with 12–256 characters.')
        salt=secrets.token_bytes(32);digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,600000).hex()
        c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('password',salt.hex()+':'+digest))
    def login(self,c,route,data):
        now=time.time();ip=self.client_address[0]
        recent=[t for t in ATTEMPTS.get(ip,[]) if now-t<300];ATTEMPTS[ip]=recent
        if len(recent)>=10:return self.fail(429,'Too many attempts. Please wait five minutes.')
        if route=='/api/setup':
            if setting(c,'password'):return self.fail(409,'An owner account already exists. Sign in instead.')
            self.set_password(c,data.get('password'))
        elif not self.password_matches(c,data.get('password')):
            recent.append(now);return self.fail(401,'Incorrect password.')
        ATTEMPTS[ip]=[]
        token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
        c.execute('DELETE FROM sessions WHERE expires<?',(int(now),))
        c.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),csrf,int(now)+28800));c.commit()
        self.send(200,{'csrf':csrf},extra={'Set-Cookie':f'portfolio_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=28800'})
    def upload(self,d):
        try:b=base64.b64decode(d.get('data',''),validate=True)
        except Exception:raise ValueError('Invalid image.')
        if not 0<len(b)<=4*1024*1024:raise ValueError('Image must be smaller than 4 MB.')
        if b.startswith(b'\x89PNG\r\n\x1a\n'):ext='png'
        elif b.startswith(b'\xff\xd8\xff'):ext='jpg'
        elif b[:4]==b'RIFF' and b[8:12]==b'WEBP':ext='webp'
        else:raise ValueError('Use a JPG, PNG or WebP image.')
        name=secrets.token_hex(16)+'.'+ext;(DATA/'uploads'/name).write_bytes(b)
        self.send(200,{'url':'/media/'+name})

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=4317);parser.add_argument('--data-dir')
    args=parser.parse_args();PORT=args.port
    if args.data_dir:DATA=Path(args.data_dir).resolve()
    init()
    server=ThreadingHTTPServer(('127.0.0.1',PORT),Handler)
    print(f'Portfolio ready: http://127.0.0.1:{PORT}/ | Owner area: /admin',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:server.server_close()
