"""Import a local SQLite snapshot without passwords/sessions. Never print credentials."""
import argparse
import json
import os
import sqlite3
from pathlib import Path

import psycopg
from psycopg import sql

TABLES = ('projects', 'jobs', 'invoices', 'payments', 'expenses', 'audit', 'site_content')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sqlite', required=True)
    args = parser.parse_args()
    source = Path(args.sqlite).resolve()
    with sqlite3.connect(f'{source.as_uri()}?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        existing={row['name'] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        records = {table: [dict(row) for row in db.execute('SELECT * FROM '+table+' ORDER BY id')] if table in existing else [] for table in TABLES}
    with psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None) as db:
        db.execute("SET LOCAL search_path TO portfolio")
        db.execute('SELECT pg_advisory_xact_lock(271827182)')
        for table in TABLES:
            count = db.execute(sql.SQL('SELECT COUNT(*) FROM {}').format(sql.Identifier(table))).fetchone()[0]
            if count:
                raise SystemExit('Import stopped: destination contains records. No changes made.')
        for table in TABLES:
            for row in records[table]:
                statement = sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(
                    sql.Identifier(table), sql.SQL(',').join(map(sql.Identifier,row)),
                    sql.SQL(',').join(sql.Placeholder() for _ in row))
                db.execute(statement, list(row.values()))
            if table!='site_content':
                db.execute("SELECT setval(pg_get_serial_sequence(%s,'id'),COALESCE((SELECT MAX(id) FROM "+table+"),1),EXISTS(SELECT 1 FROM "+table+"))", ('portfolio.'+table,))
    print('Imported records:', json.dumps({table: len(rows) for table,rows in records.items()}))
    print('Account passwords and sessions were not copied. Upload data/uploads to the private portfolio-images bucket separately, keeping filenames.')

if __name__ == '__main__':
    main()
