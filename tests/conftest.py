import os
from uuid import uuid4
import pytest
from dotenv import load_dotenv
from psycopg.conninfo import conninfo_to_dict
load_dotenv()
from distribuidora.database import transaction
from distribuidora import services as s

@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    target=os.environ.get('TEST_DATABASE_URL')
    if not target: pytest.skip('Bloqueado: falta TEST_DATABASE_URL.')
    config=conninfo_to_dict(target)
    if config.get('user','').split('.')[0]!='cn_test_app' or os.environ.get('TEST_DATABASE_SCHEMA')!='cn_test':
        pytest.fail('Destino de prueba no permitido: se exige cn_test_app / cn_test.')
    monkeypatch.setenv('DATABASE_URL',target); monkeypatch.setenv('DATABASE_SCHEMA','cn_test')
    with transaction() as conn:
        identity=conn.execute('SELECT current_user AS role,current_schema() AS schema').fetchone()
        assert identity=={'role':'cn_test_app','schema':'cn_test'}
        # Única limpieza del proyecto: seis tablas y registro técnico del esquema aislado.
        conn.execute('TRUNCATE cn_test.operaciones,cn_test.movimientos_stock,cn_test.detalle_pedidos,cn_test.pedidos,cn_test.stock,cn_test.productos,cn_test.clientes')
    yield

@pytest.fixture
def sample():
    cid=s.save_client(dict(nombre_comercio='Cliente prueba',contacto='Ficticio',telefono='000',direccion='Demo'),str(uuid4()))
    pid=s.save_product(dict(codigo='P1',nombre='Producto prueba',descripcion='',precio_unitario=8000,stock_minimo=3),str(uuid4()))
    s.receive(pid,10,str(uuid4()))
    return cid,pid

@pytest.fixture
def client():
    from distribuidora import create_app
    return create_app({'TESTING':True,'SECRET_KEY':'test-only-key','SESSION_COOKIE_SECURE':False}).test_client()
