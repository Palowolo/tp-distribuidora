"""Aplicador manual a través de una conexión administrativa, nunca importado por Flask."""
import argparse
import os
from pathlib import Path
import hashlib
import psycopg
from psycopg.conninfo import conninfo_to_dict
from dotenv import load_dotenv
load_dotenv()

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--expected-host',required=True); args=parser.parse_args()
    url=os.environ.get('ADMIN_DATABASE_URL','')
    settings=conninfo_to_dict(url)
    if not url or settings.get('host')!=args.expected_host: raise SystemExit('Destino no confirmado.')
    with psycopg.connect(url,prepare_threshold=None) as conn:
        conn.execute('CREATE SCHEMA IF NOT EXISTS cn_migrations')
        conn.execute('REVOKE ALL ON SCHEMA cn_migrations FROM PUBLIC')
        conn.execute('CREATE TABLE IF NOT EXISTS cn_migrations.aplicadas(nombre text PRIMARY KEY,sha256 text NOT NULL,fecha timestamptz DEFAULT now())')
        for path in sorted(Path('supabase/migrations').glob('*.sql')):
            data=path.read_text(encoding='utf-8'); digest=hashlib.sha256(data.encode()).hexdigest()
            old=conn.execute('SELECT sha256 FROM cn_migrations.aplicadas WHERE nombre=%s',(path.name,)).fetchone()
            if old:
                if old[0]!=digest: raise RuntimeError('Una migración aplicada cambió.')
                continue
            # En Supabase, el historial remoto también puede haberse creado por MCP.
            if conn.execute("SELECT to_regclass('supabase_migrations.schema_migrations')").fetchone()[0]:
                prior=conn.execute('SELECT 1 FROM supabase_migrations.schema_migrations WHERE name=%s',('_'.join(path.stem.split('_')[1:]),)).fetchone()
                if prior:
                    conn.execute('INSERT INTO cn_migrations.aplicadas(nombre,sha256) VALUES (%s,%s)',(path.name,digest)); continue
            conn.execute(data)
            conn.execute('INSERT INTO cn_migrations.aplicadas(nombre,sha256) VALUES (%s,%s)',(path.name,digest))
            print('Aplicada:',path.name)
