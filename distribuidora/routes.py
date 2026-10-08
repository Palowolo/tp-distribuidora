from datetime import date
from flask import Blueprint, request, render_template, redirect, url_for, flash, abort
from .database import query
from . import services as s
from .validation import integer, BusinessError, MAX_INT

catalog = Blueprint('catalog',__name__)
orders = Blueprint('orders',__name__)
reports = Blueprint('reports',__name__)

def form_key(): return request.form.get('operation_key')
def done(endpoint, **values):
    flash('Operación guardada correctamente.','success')
    return redirect(url_for(endpoint,**values),code=303)

@catalog.route('/clientes',methods=['GET','POST'])
def clients():
    if request.method=='POST':
        cid = request.form.get('id')
        s.save_client(request.form,form_key(),integer(cid,'Cliente',1,MAX_INT) if cid else None)
        return done('catalog.clients')
    search = request.args.get('q','')[:160]
    rows = query('SELECT * FROM clientes WHERE nombre_comercio ILIKE %s ORDER BY nombre_comercio',('%'+search+'%',))
    edit = query('SELECT * FROM clientes WHERE id=%s',(integer(request.args['editar'],'Cliente',1,MAX_INT),))[0] if request.args.get('editar') else None
    return render_template('clientes.html',rows=rows,edit=edit,q=search)

@catalog.route('/productos',methods=['GET','POST'])
def products():
    if request.method=='POST':
        pid = request.form.get('id')
        s.save_product(request.form,form_key(),integer(pid,'Producto',1,MAX_INT) if pid else None)
        return done('catalog.products')
    search = request.args.get('q','')[:160]
    rows = query('SELECT p.*,s.cantidad_actual,s.stock_minimo FROM productos p JOIN stock s ON s.producto_id=p.id WHERE p.nombre ILIKE %s OR p.codigo ILIKE %s ORDER BY p.nombre',('%'+search+'%','%'+search+'%'))
    edit = next((p for p in rows if str(p['id'])==request.args.get('editar')),None)
    return render_template('productos.html',rows=rows,edit=edit,q=search)

@catalog.post('/<kind>/<int:entity_id>/baja')
def deactivate(kind,entity_id):
    if kind not in ('clientes','productos'): abort(404)
    s.deactivate(kind,entity_id)
    return done('catalog.clients' if kind=='clientes' else 'catalog.products')

@catalog.route('/stock',methods=['GET','POST'])
def stock():
    if request.method=='POST':
        s.receive(request.form.get('producto_id'),request.form.get('cantidad'),form_key())
        return done('catalog.stock')
    rows = query('SELECT p.*,s.cantidad_actual,s.stock_minimo FROM productos p JOIN stock s ON s.producto_id=p.id ORDER BY p.nombre')
    movements = query('SELECT m.*,p.nombre FROM movimientos_stock m JOIN productos p ON p.id=m.producto_id ORDER BY m.fecha DESC,m.id DESC LIMIT 100')
    return render_template('stock.html',rows=rows,movements=movements)

def customers(): return query('SELECT * FROM clientes ORDER BY nombre_comercio')

def listing(filters=None):
    filters=filters or {}
    where, params = [], []
    if filters.get('cliente_id'):
        where.append('p.cliente_id=%s'); params.append(integer(filters['cliente_id'],'Cliente',1,MAX_INT))
    if filters.get('estado'):
        if filters['estado'] not in s.STATES: raise BusinessError('Estado inválido.')
        where.append('p.estado=%s'); params.append(filters['estado'])
    for key, operator in [('desde','>='),('hasta','<=')]:
        if filters.get(key):
            try: value=date.fromisoformat(filters[key])
            except ValueError: raise BusinessError('Fecha inválida.') from None
            where.append(f"(p.fecha AT TIME ZONE 'America/Asuncion')::date {operator} %s"); params.append(value)
    return query('''SELECT p.*,c.nombre_comercio,
        sum(d.solicitada::bigint*d.precio_unitario) AS monto_solicitado,
        sum(d.preparada::bigint*d.precio_unitario) AS monto_preparado,
        sum(d.entregada::bigint*d.precio_unitario) AS monto_entregado,
        (p.estado='Preparado' AND bool_or(d.entregada>0) AND bool_or(d.entregada<d.solicitada)) AS parcial
        FROM pedidos p JOIN clientes c ON c.id=p.cliente_id JOIN detalle_pedidos d ON d.pedido_id=p.id '''+
        ('WHERE '+' AND '.join(where) if where else '')+' GROUP BY p.id,c.nombre_comercio ORDER BY p.fecha DESC,p.id DESC',params)

def detail(order_id):
    rows=query('SELECT p.*,c.nombre_comercio,c.direccion,c.telefono FROM pedidos p JOIN clientes c ON c.id=p.cliente_id WHERE p.id=%s',(order_id,))
    if not rows: abort(404)
    order=rows[0]
    lines=query('SELECT d.*,p.nombre,p.codigo FROM detalle_pedidos d JOIN productos p ON p.id=d.producto_id WHERE d.pedido_id=%s ORDER BY d.producto_id',(order_id,))
    order['parcial']=order['estado']=='Preparado' and any(d['entregada'] for d in lines) and any(d['entregada']<d['solicitada'] for d in lines)
    order['entrega_previa']=any(d['entregada'] for d in lines)
    for stage in ('solicitada','preparada','entregada'): order['monto_'+stage]=sum(d[stage]*d['precio_unitario'] for d in lines)
    return order,lines

@orders.route('/pedidos/nuevo',methods=['GET','POST'])
def new():
    if request.method=='POST':
        products=request.form.getlist('producto_id'); qty=request.form.getlist('cantidad')
        if len(products)!=len(qty): raise BusinessError('Detalle incompleto.')
        oid=s.create_order(request.form.get('cliente_id'),request.form.get('vendedor'),list(zip(products,qty)),request.form.get('observaciones'),form_key())
        return done('orders.view',order_id=oid)
    products=query('SELECT p.*,s.cantidad_actual FROM productos p JOIN stock s ON s.producto_id=p.id WHERE p.activo ORDER BY p.nombre')
    return render_template('nuevo_pedido.html',clients=[c for c in customers() if c['activo']],products=products)

@orders.get('/pedidos')
def index(): return render_template('pedidos.html',rows=listing(request.args),clients=customers(),states=s.STATES)

@orders.get('/pedidos/<int:order_id>')
def view(order_id):
    order,lines=detail(order_id)
    return render_template('detalle.html',order=order,lines=lines)

@orders.post('/pedidos/<int:order_id>/editar')
def edit(order_id):
    s.edit_order(order_id,request.form.get('vendedor'),request.form.get('observaciones'))
    return done('orders.view',order_id=order_id)

@orders.post('/pedidos/<int:order_id>/cancelar')
def cancel(order_id):
    s.cancel(order_id)
    return done('orders.view',order_id=order_id)

def totals():
    keys=[k for k in request.form if k.startswith('total_')]
    if any(len(request.form.getlist(k))!=1 for k in keys): raise BusinessError('Cantidades duplicadas.')
    return {k[6:]:request.form[k] for k in keys}

def consolidated():
    return query("""SELECT p.id,p.codigo,p.nombre,sum(d.solicitada-d.preparada) AS faltante,s.cantidad_actual
    FROM detalle_pedidos d JOIN pedidos pe ON pe.id=d.pedido_id JOIN productos p ON p.id=d.producto_id
    JOIN stock s ON s.producto_id=p.id WHERE pe.estado IN ('Pendiente','En preparación')
    GROUP BY p.id,s.cantidad_actual HAVING sum(d.solicitada-d.preparada)>0 ORDER BY p.nombre""")

@orders.get('/deposito')
def warehouse():
    selected=request.args.get('pedido_id')
    order,lines=detail(integer(selected,'Pedido',1,MAX_INT)) if selected else (None,[])
    return render_template('deposito.html',rows=[p for p in listing() if p['estado'] in ('Pendiente','En preparación')],consolidated=consolidated(),order=order,lines=lines)

@orders.post('/pedidos/<int:order_id>/preparar')
def prepare(order_id):
    s.prepare(order_id,totals())
    return done('orders.view',order_id=order_id)

@orders.route('/pedidos/<int:order_id>/entrega',methods=['GET','POST'])
def delivery(order_id):
    if request.method=='POST':
        s.deliver(order_id,totals()); return done('orders.view',order_id=order_id)
    order,lines=detail(order_id)
    if order['estado']!='Preparado': raise BusinessError('El pedido debe estar Preparado.')
    return render_template('entrega.html',order=order,lines=lines)

@reports.get('/')
def summary():
    rows=listing()
    return render_template('resumen.html',rows=rows[:8],counts={state:sum(p['estado']==state for p in rows) for state in s.STATES},
        active=query('SELECT count(*) AS n FROM clientes WHERE activo')[0]['n'],
        low=query('SELECT p.nombre,s.* FROM stock s JOIN productos p ON p.id=s.producto_id WHERE s.cantidad_actual<s.stock_minimo ORDER BY p.nombre'))

@reports.get('/reportes')
def history():
    cid=request.args.get('cliente_id')
    rows=listing({'cliente_id':cid}) if cid else []
    lines=query('''SELECT pe.id AS pedido_id,pe.estado,p.nombre,d.* FROM pedidos pe
      JOIN detalle_pedidos d ON d.pedido_id=pe.id JOIN productos p ON p.id=d.producto_id
      WHERE pe.cliente_id=%s ORDER BY pe.fecha DESC,p.nombre''',(integer(cid,'Cliente',1,MAX_INT),)) if cid else []
    return render_template('reporte.html',clients=customers(),rows=rows,lines=lines)
