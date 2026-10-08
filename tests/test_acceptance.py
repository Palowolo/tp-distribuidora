from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import re
import pytest
import psycopg
from distribuidora import services as s
from distribuidora.database import query,transaction
from distribuidora.validation import BusinessError,gs,integer,MAX_INT

def key(): return str(uuid4())
def stock(pid): return query('SELECT cantidad_actual FROM stock WHERE producto_id=%s',(pid,))[0]['cantidad_actual']
def order(sample,qty=5): return s.create_order(sample[0],'Vendedor',[(sample[1],qty)],'',key())
def state(oid): return query('SELECT estado FROM pedidos WHERE id=%s',(oid,))[0]['estado']
def snapshot():
    return {t:query('SELECT * FROM '+t+' ORDER BY id') for t in ('clientes','productos','stock','pedidos','detalle_pedidos','movimientos_stock')}
def parallel(*actions):
    barrier=Barrier(len(actions))
    def call(action):
        barrier.wait()
        try: action(); return 'ok'
        except BusinessError: return 'rechazado'
    with ThreadPoolExecutor(max_workers=len(actions)) as pool: return list(pool.map(call,actions))

def test_CP01_catalogo(sample):
    cid,pid=sample; oid=order(sample)
    s.save_client(dict(nombre_comercio='Editado',contacto='Contacto',telefono='000',direccion='Nueva'),client_id=cid)
    s.save_product(dict(codigo='P1',nombre='Editado',precio_unitario=9000,stock_minimo=3),product_id=pid)
    assert query("SELECT id FROM clientes WHERE nombre_comercio ILIKE %s",('%editado%',))
    with pytest.raises(psycopg.IntegrityError): s.save_product(dict(codigo='P1',nombre='Duplicado',precio_unitario=1),key())
    s.deactivate('clientes',cid); s.deactivate('productos',pid)
    with pytest.raises(BusinessError): order(sample)
    assert query('SELECT precio_unitario FROM detalle_pedidos WHERE pedido_id=%s',(oid,))[0]['precio_unitario']==8000
    s.prepare(oid,{pid:5}); s.deliver(oid,{pid:5})
    assert state(oid)=='Entregado'

def test_CP02_ingreso_idempotente(sample):
    cid,pid=sample; token=key()
    s.receive(pid,5,token); s.receive(pid,5,token)
    assert stock(pid)==15
    assert len(query("SELECT * FROM movimientos_stock WHERE cantidad=5 AND tipo='ingreso'"))==1
    for n in (0,-1,'1.5',MAX_INT):
        with pytest.raises(BusinessError): s.receive(pid,n,key())
    with pytest.raises(BusinessError): s.receive(pid,6,token)

def test_CP03_precio_historico(sample):
    cid,pid=sample; token=key()
    oid=s.create_order(cid,'V',[(pid,3)],'',token)
    assert s.create_order(cid,'V',[(pid,3)],'',token)==oid
    with transaction() as c: c.execute('UPDATE productos SET precio_unitario=9000 WHERE id=%s',(pid,))
    d=query('SELECT * FROM detalle_pedidos WHERE pedido_id=%s',(oid,))[0]
    assert state(oid)=='Pendiente' and stock(pid)==10 and d['precio_unitario']==8000
    assert gs(d['solicitada']*d['precio_unitario'])=='Gs. 24.000'

def test_CP04_validacion_y_precio_manipulado(sample,client):
    cid,pid=sample
    for items in ([],[(pid,1),(pid,2)],[(pid,'1.5')],[(pid,11)]):
        with pytest.raises(BusinessError): s.create_order(cid,'V',items,'',key())
    assert not query('SELECT * FROM pedidos')
    html=client.get('/pedidos/nuevo').text
    csrf=re.search('name="csrf_token" value="([^"]+)"',html).group(1)
    response=client.post('/pedidos/nuevo',data=dict(csrf_token=csrf,operation_key=key(),cliente_id=cid,vendedor='V',producto_id=pid,cantidad=3,precio_unitario=1))
    assert response.status_code==303
    assert query('SELECT precio_unitario FROM detalle_pedidos')[0]['precio_unitario']==8000
    s.deactivate('clientes',cid)
    with pytest.raises(BusinessError): order(sample)

def test_CP05_preparacion_acumulada(sample):
    oid=order(sample); pid=sample[1]
    s.prepare(oid,{pid:0}); assert state(oid)=='Pendiente'
    s.prepare(oid,{pid:2}); assert stock(pid)==8 and state(oid)=='En preparación'
    with pytest.raises(BusinessError): s.prepare(oid,{pid:1})
    s.prepare(oid,{pid:5}); s.prepare(oid,{pid:5})
    assert stock(pid)==5 and state(oid)=='Preparado'
    assert [r['cantidad'] for r in query("SELECT cantidad FROM movimientos_stock WHERE tipo='egreso' ORDER BY id")]==[2,3]

def test_CP06_preparacion_concurrente(sample):
    pid=sample[1]
    a=order(sample,5); s.prepare(a,{pid:5}); s.deliver(a,{pid:5})
    b,c=order(sample,4),order(sample,4)
    result=parallel(lambda:s.prepare(b,{pid:4}),lambda:s.prepare(c,{pid:4}))
    assert sorted(result)==['ok','rechazado'] and stock(pid)==1
    assert len(query("SELECT * FROM movimientos_stock WHERE tipo='egreso'"))==2

def test_CP07_entrega_acumulada(sample):
    oid=order(sample); pid=sample[1]
    with pytest.raises(BusinessError): s.deliver(oid,{pid:1})
    s.prepare(oid,{pid:5}); s.deliver(oid,{pid:3}); s.deliver(oid,{pid:3})
    assert state(oid)=='Preparado' and stock(pid)==5
    for n in (2,6):
        with pytest.raises(BusinessError): s.deliver(oid,{pid:n})
    s.deliver(oid,{pid:5}); assert state(oid)=='Entregado'
    with pytest.raises(BusinessError): s.edit_order(oid,'Otro','')
    with pytest.raises(BusinessError): s.cancel(oid)

def test_CP07_entrega_simultanea(sample):
    oid=order(sample); pid=sample[1]; s.prepare(oid,{pid:5})
    result=parallel(lambda:s.deliver(oid,{pid:3}),lambda:s.deliver(oid,{pid:5}))
    assert result.count('ok')>=1 and state(oid)=='Entregado' and stock(pid)==5
    assert query('SELECT entregada FROM detalle_pedidos WHERE pedido_id=%s',(oid,))[0]['entregada']==5

def test_CP08_cancelacion_parcial(sample):
    oid=order(sample); pid=sample[1]; s.prepare(oid,{pid:5}); s.deliver(oid,{pid:3}); s.cancel(oid)
    with pytest.raises(BusinessError): s.cancel(oid)
    assert stock(pid)==7 and state(oid)=='Cancelado'
    d=query('SELECT * FROM detalle_pedidos WHERE pedido_id=%s',(oid,))[0]
    assert (d['preparada'],d['entregada'])==(5,3)
    assert [m['cantidad'] for m in query("SELECT cantidad FROM movimientos_stock WHERE tipo='devolucion'")]==[2]

def test_CP08_cancelacion_simultanea(sample):
    oid=order(sample); pid=sample[1]; s.prepare(oid,{pid:5}); s.deliver(oid,{pid:3})
    assert sorted(parallel(lambda:s.cancel(oid),lambda:s.cancel(oid)))==['ok','rechazado']
    assert stock(pid)==7

def test_CP08_entrega_frente_cancelacion(sample):
    oid=order(sample); pid=sample[1]; s.prepare(oid,{pid:5})
    parallel(lambda:s.deliver(oid,{pid:3}),lambda:s.cancel(oid))
    assert state(oid)=='Cancelado'
    delivered=query('SELECT entregada FROM detalle_pedidos WHERE pedido_id=%s',(oid,))[0]['entregada']
    assert stock(pid)==10-delivered

def test_CP09_rollback(sample,monkeypatch):
    oid=order(sample); before=snapshot()
    def fail(*args): raise RuntimeError('Falla controlada después de stock')
    monkeypatch.setattr(s,'movement',fail)
    with pytest.raises(RuntimeError): s.prepare(oid,{sample[1]:5})
    assert snapshot()==before
    with pytest.raises(RuntimeError): s.receive(sample[1],5,key())
    assert snapshot()==before

def test_CP10_consultas_y_recarga(sample,client):
    from distribuidora.routes import consolidated,listing
    oid=order(sample); pid=sample[1]
    assert consolidated()[0]['faltante']==5
    s.prepare(oid,{pid:2}); assert consolidated()[0]['faltante']==3
    assert len(listing({'cliente_id':sample[0],'estado':'En preparación'}))==1
    s.cancel(oid); assert not consolidated()
    for url in (f'/pedidos/{oid}',f'/reportes?cliente_id={sample[0]}','/pedidos?estado=Cancelado'):
        assert client.get(url).status_code==200
        assert client.get(url).status_code==200

def test_VT01_rutas(sample,client):
    oid=order(sample); s.prepare(oid,{sample[1]:5})
    for url in ('/','/clientes','/productos','/stock','/pedidos/nuevo','/pedidos',f'/pedidos/{oid}','/deposito',f'/pedidos/{oid}/entrega','/reportes','/static/css/estilos.css','/static/js/app.js','/health'):
        assert client.get(url).status_code==200,url

def test_VT02_restricciones(sample):
    with pytest.raises(psycopg.IntegrityError):
        with transaction() as c: c.execute("INSERT INTO pedidos(cliente_id,vendedor) VALUES (%s,'V')",(sample[0],))
    with pytest.raises(psycopg.IntegrityError):
        with transaction() as c: c.execute('UPDATE stock SET cantidad_actual=-1 WHERE producto_id=%s',(sample[1],))
    with transaction() as c:
        assert not c.execute("SELECT has_schema_privilege(current_user,'comercial_norte','USAGE') AS permitido").fetchone()['permitido']

def test_VT03_csrf_y_sql(sample,client):
    assert client.post('/pedidos/nuevo',data={}).status_code==400
    response=client.get('/clientes?q=%27%20OR%201=1--')
    assert response.status_code==200 and b'Cliente prueba' not in response.data
    assert "frame-ancestors 'none'" in response.headers['Content-Security-Policy']

def test_VT04_dinero():
    assert gs(None)=='Gs. 0' and gs(97700)=='Gs. 97.700'
    for value in ('1.5',1.2,True,'1e3','-1'):
        with pytest.raises(BusinessError): integer(value)

def test_VT05_demo_repetible():
    from scripts.seed import seed
    seed(); first=snapshot(); seed(); assert snapshot()==first
    assert len(first['clientes'])==8 and len(first['productos'])==20 and len(first['pedidos'])==10
    assert len({p['estado'] for p in first['pedidos']})==5
    assert len([r for r in first['stock'] if r['cantidad_actual']<r['stock_minimo']])==2

def test_reenvios_concurrentes(sample):
    pid=sample[1]; token=key()
    assert parallel(lambda:s.receive(pid,2,token),lambda:s.receive(pid,2,token))==['ok','ok']
    assert stock(pid)==12
    token=key()
    assert parallel(lambda:s.create_order(sample[0],'V',[(pid,2)],'',token),lambda:s.create_order(sample[0],'V',[(pid,2)],'',token))==['ok','ok']
    assert len(query('SELECT * FROM pedidos'))==1
