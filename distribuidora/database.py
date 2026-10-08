"""Una conexión y transacción por operación, compatible con Supavisor."""
import os
from contextlib import contextmanager
import psycopg
from psycopg import sql
from psycopg.rows import dict_row

SCHEMAS = {'comercial_norte', 'cn_preview', 'cn_test'}

@contextmanager
def transaction(url=None, schema=None):
    target = url or os.environ.get('DATABASE_URL')
    namespace = schema or os.environ.get('DATABASE_SCHEMA', 'cn_preview')
    if not target or namespace not in SCHEMAS:
        raise RuntimeError('Falta configurar la conexión de base de datos.')
    with psycopg.connect(target, row_factory=dict_row, prepare_threshold=None,
                         connect_timeout=10) as conn:
        conn.execute(sql.SQL('SET LOCAL search_path TO {}, pg_catalog').format(sql.Identifier(namespace)))
        conn.execute("SET LOCAL statement_timeout = '15s'")
        conn.execute("SET LOCAL lock_timeout = '10s'")
        conn.execute("SET LOCAL TIME ZONE 'America/Asuncion'")
        yield conn

def query(statement, params=()):
    with transaction() as conn:
        return conn.execute(statement, params).fetchall()
