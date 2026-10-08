from dotenv import load_dotenv
load_dotenv()
from distribuidora.database import transaction

with transaction() as conn:
    print(conn.execute('SELECT current_user, current_schema(), version()').fetchone())
    print({'tls_cliente_pooler':conn.info.ssl_in_use})
    print(conn.execute("SELECT count(*) AS tablas FROM information_schema.tables WHERE table_schema=current_schema()").fetchone())
