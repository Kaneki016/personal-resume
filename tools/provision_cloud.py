"""One-time CLI provisioning. Secrets stay in ignored local files and Vercel."""
import json
import secrets
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
REF = 'yidjqjtwqrsonxxujdtb'
ENV_FILE = ROOT / '.env.cloud.json'

def cli(args, value=None):
    result = subprocess.run(['npx.cmd', '--yes', *args], cwd=ROOT, input=value,
                            capture_output=True, text=True, encoding='utf-8')
    if result.returncode:
        # CLI errors can echo credentials or SQL. Keep them off stdout.
        raise RuntimeError('CLI command failed: ' + ' '.join(args[:3]))
    return result.stdout

def api(env, path, data=None):
    key = env['SUPABASE_SERVICE_ROLE_KEY']
    req = Request(env['SUPABASE_URL'] + '/auth/v1/' + path,
                  data=json.dumps(data).encode() if data is not None else None,
                  headers={'apikey':key, 'Authorization':'Bearer '+key, 'Content-Type':'application/json'})
    with urlopen(req, timeout=30) as response:
        return json.load(response)

def main():
    (ROOT / 'data').mkdir(exist_ok=True)
    if ENV_FILE.exists():
        env = json.loads(ENV_FILE.read_text())
    else:
        keys = json.loads((ROOT / '.env.supabase-keys.json').read_text(encoding='utf-8-sig'))
        key = next(row['api_key'] for row in keys if row['name'] == 'service_role')
        password = secrets.token_hex(32)
        env = {'APP_ORIGIN':'https://laiyokeyau.vercel.app',
               'SUPABASE_URL':f'https://{REF}.supabase.co',
               'SUPABASE_SERVICE_ROLE_KEY':key, 'OWNER_EMAIL':'laiyokeyau@gmail.com',
               'DATABASE_URL':f'postgresql://portfolio_app.{REF}:{password}@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres?sslmode=require'}
        ENV_FILE.write_text(json.dumps(env), encoding='utf-8')
        role_sql = f"CREATE ROLE portfolio_app LOGIN PASSWORD '{password}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;\n"
        (ROOT / 'data/provision-role.sql').write_text(role_sql + (ROOT / 'supabase/app-role.sql').read_text(), encoding='utf-8')
    result = json.loads(cli(['supabase@latest','db','query','--linked','--project-ref',REF,
                             "SELECT 1 FROM pg_roles WHERE rolname='portfolio_app'"]))
    if not result.get('rows'):
        cli(['supabase@latest','db','query','--linked','--project-ref',REF,'--file','data/provision-role.sql'])
    print('Private database login ready.')
    users = api(env, 'admin/users?page=1&per_page=100').get('users', [])
    owner = next((u for u in users if u.get('email') == env['OWNER_EMAIL']), None)
    if owner is None:
        owner_password = secrets.token_urlsafe(24)
        owner = api(env,'admin/users',{'email':env['OWNER_EMAIL'],'password':owner_password,'email_confirm':True})
        (ROOT / 'data/owner-login.txt').write_text('Admin: https://laiyokeyau.vercel.app/admin\nEmail: '+env['OWNER_EMAIL']+'\nTemporary password: '+owner_password+'\nChange this password from the admin Settings after signing in.\n', encoding='utf-8')
    env['OWNER_USER_ID'] = owner['id']
    ENV_FILE.write_text(json.dumps(env), encoding='utf-8')
    print('Owner account ready; credentials are stored locally, outside Git.')
    for name, value in env.items():
        secret = name in ('SUPABASE_SERVICE_ROLE_KEY','DATABASE_URL')
        cli(['vercel@latest','env','add',name,'production','--force','--yes',
             '--sensitive' if secret else '--no-sensitive'], value)
        print('Configured production variable:', name)

if __name__ == '__main__':
    try:
        main()
    except HTTPError as error:
        raise SystemExit('Supabase request failed with HTTP '+str(error.code))
