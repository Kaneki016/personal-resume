"""Private invoice generation. Caller owns the transaction and owner-write lock."""
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

DEFAULTS = {'name': 'Lai Yoke Yau', 'email': 'laiyokeyau@gmail.com',
            'phone': '+60183822330', 'address': '', 'bank': '', 'account': '',
            'holder': '', 'terms': '50% deposit, balance on completion. Payment due within 14 days.'}
LIMITS = {'name':160, 'email':200, 'phone':80, 'address':600, 'bank':120,
          'account':80, 'holder':160, 'terms':1000}

def settings(c):
    row = c.execute("SELECT body FROM invoice_settings WHERE id='issuer'").fetchone()
    return {**DEFAULTS, **(json.loads(row['body']) if row else {})}

def save_settings(c, data, validate, audit):
    cleaned = {key:validate(data.get(key, ''), key, limit, key in ('name','terms'))
               for key,limit in LIMITS.items()}
    before = settings(c)
    c.execute("INSERT INTO invoice_settings(id,body) VALUES('issuer',?) ON CONFLICT(id) DO UPDATE SET body=excluded.body",
              (json.dumps(cleaned, ensure_ascii=False),))
    audit(c, 'update', 'invoice_settings', None, before, cleaned)
    return cleaned

def generate(c, data, validate, cents, day, audit):
    key = validate(data.get('request_key'), 'request reference', 80)
    if not re.fullmatch(r'[a-zA-Z0-9-]{16,80}', key):
        raise ValueError('Reopen the generator to create a request reference.')
    client = validate(data.get('client'), 'client name', 160)
    project = validate(data.get('project'), 'project name', 160)
    amount = cents(data.get('amount'))
    if amount <= 0: raise ValueError('Amount must be greater than zero.')
    description = validate(data.get('description'), 'billing description', 2000)
    today = datetime.now(timezone(timedelta(hours=8))).date()
    issue = day(data.get('issue_date') or today.isoformat())
    due = day(data.get('due_date') or (datetime.fromisoformat(issue).date()+timedelta(days=14)).isoformat())
    if due < issue: raise ValueError('Due date cannot precede issue date.')
    payload = dict(client=client, project=project, amount_cents=amount,
                   description=description, issue_date=issue, due_date=due)
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    previous = c.execute('SELECT id,fingerprint FROM invoice_documents WHERE request_key=?', (key,)).fetchone()
    if previous:
        if previous['fingerprint'] != fingerprint:
            raise ValueError('This request already generated an invoice. Reopen the generator for another invoice.')
        return dict(c.execute('SELECT id,number FROM invoices WHERE id=?', (previous['id'],)).fetchone())
    issuer = settings(c)
    if not all(issuer[k] for k in ('name','bank','account','holder')):
        raise ValueError('Save your issuer and bank details in Invoice settings first.')
    matches = list(c.execute('SELECT id FROM jobs WHERE LOWER(client)=LOWER(?) AND LOWER(name)=LOWER(?)', (client,project)))
    if len(matches)>1: raise ValueError('Multiple client projects have this name. Give them distinct names in Client projects first.')
    if matches:
        job_id = matches[0]['id']
    else:
        record = dict(name=project,client=client,fee_cents=0,fee_known=0)
        job_id = c.execute('INSERT INTO jobs(name,client,fee_cents,fee_known) VALUES(?,?,0,0)', (project,client)).lastrowid
        audit(c,'create','jobs',job_id,None,record)
    # Both SQLite and PostgreSQL callers serialise owner writes. Counter, document,
    # invoice and optional project commit together; a failed request consumes nothing.
    c.execute("INSERT INTO invoice_counter(id,value) VALUES('invoice',0) ON CONFLICT(id) DO NOTHING")
    value = c.execute("SELECT value FROM invoice_counter WHERE id='invoice'").fetchone()['value']
    for row in c.execute('SELECT number FROM invoices'):
        match = re.fullmatch(r'INV-(\d{6,})', row['number'])
        if match: value = max(value, int(match[1]))
    value += 1
    number = f'INV-{value:06d}'
    c.execute("UPDATE invoice_counter SET value=? WHERE id='invoice'", (value,))
    record = dict(job_id=job_id,number=number,issue_date=issue,due_date=due,amount_cents=amount,description=description)
    ident = c.execute('INSERT INTO invoices(job_id,number,issue_date,due_date,amount_cents,description) VALUES(?,?,?,?,?,?)', tuple(record.values())).lastrowid
    c.execute('INSERT INTO invoice_documents(id,request_key,fingerprint,body) VALUES(?,?,?,?)',
              (ident,key,fingerprint,json.dumps({**payload,'issuer':issuer},ensure_ascii=False)))
    audit(c,'create','invoices',ident,None,record)
    return {'id':ident,'number':number}

def render(c, ident, templates):
    row = c.execute('''SELECT i.*,j.client,j.name AS project,
        COALESCE((SELECT SUM(p.amount_cents) FROM payments p WHERE p.invoice_id=i.id AND p.void=0),0) AS paid_cents
        FROM invoices i JOIN jobs j ON j.id=i.job_id WHERE i.id=?''', (ident,)).fetchone()
    if not row: return None
    invoice = dict(row)
    saved = c.execute('SELECT body FROM invoice_documents WHERE id=?', (ident,)).fetchone()
    snapshot = json.loads(saved['body']) if saved else {'issuer':settings(c)}
    invoice.update(snapshot)
    invoice['balance'] = max(0, invoice['amount_cents']-invoice['paid_cents'])
    invoice['credit'] = max(0, invoice['paid_cents']-invoice['amount_cents'])
    money = lambda n: f'RM {int(n)//100:,}.{int(n)%100:02d}'
    return templates.get_template('invoice.html').render(i=invoice,money=money,legacy=not saved)
