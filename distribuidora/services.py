"""Reglas de negocio compartidas por interfaz, demo y pruebas reales."""
import hashlib
import json
from .database import transaction
from .validation import BusinessError, integer, text, token, MAX_INT, MAX_PRICE, MAX_TOTAL

STATES = ('Pendiente', 'En preparación', 'Preparado', 'Entregado', 'Cancelado')
TERMINAL = ('Entregado', 'Cancelado')

def claim(conn, key, action, payload):
    key = token(key)
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    row = conn.execute('INSERT INTO operaciones(clave,accion,huella) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING RETURNING clave', (key, action, digest)).fetchone()
    if row:
        return None
    old = conn.execute('SELECT * FROM operaciones WHERE clave=%s', (key,)).fetchone()
    if old['accion'] != action or old['huella'] != digest:
        raise BusinessError('Este formulario ya se utilizó con otros datos. Abrí uno nuevo.')
    return old['resultado_id']

def finish(conn, key, result):
    conn.execute('UPDATE operaciones SET resultado_id=%s WHERE clave=%s', (result, key))
    return result

def save_client(data, key=None, client_id=None):
    values = [text(data.get(k), label, size) for k, label, size in (
        ('nombre_comercio','Comercio',160), ('contacto','Contacto',160),
        ('telefono','Teléfono',60), ('direccion','Dirección',300))]
    with transaction() as conn:
        if client_id:
            row = conn.execute('UPDATE clientes SET nombre_comercio=%s,contacto=%s,telefono=%s,direccion=%s WHERE id=%s RETURNING id', (*values, client_id)).fetchone()
            if not row: raise BusinessError('Cliente no encontrado.')
            return row['id']
        old = claim(conn, key, 'cliente', values)
        if old is not None: return old
        result = conn.execute('INSERT INTO clientes(nombre_comercio,contacto,telefono,direccion) VALUES (%s,%s,%s,%s) RETURNING id', values).fetchone()['id']
        return finish(conn, key, result)

def save_product(data, key=None, product_id=None):
    values = [text(data.get('codigo'),'Código',40).upper(), text(data.get('nombre'),'Nombre'),
              text(data.get('descripcion'),'Descripción',1000,False),
              integer(data.get('precio_unitario'),'Precio',1,MAX_PRICE)]
    minimum = integer(data.get('stock_minimo',0),'Mínimo')
    with transaction() as conn:
        if product_id:
            row = conn.execute('UPDATE productos SET codigo=%s,nombre=%s,descripcion=%s,precio_unitario=%s WHERE id=%s RETURNING id', (*values,product_id)).fetchone()
            if not row: raise BusinessError('Producto no encontrado.')
            conn.execute('UPDATE stock SET stock_minimo=%s WHERE producto_id=%s', (minimum,product_id))
            return row['id']
        old = claim(conn,key,'producto',values+[minimum])
        if old is not None: return old
        result = conn.execute('INSERT INTO productos(codigo,nombre,descripcion,precio_unitario) VALUES (%s,%s,%s,%s) RETURNING id', values).fetchone()['id']
        conn.execute('INSERT INTO stock(producto_id,stock_minimo) VALUES (%s,%s)',(result,minimum))
        return finish(conn,key,result)

def deactivate(kind, entity_id):
    statement = {'clientes':'UPDATE clientes SET activo=false WHERE id=%s RETURNING id',
                 'productos':'UPDATE productos SET activo=false WHERE id=%s RETURNING id'}[kind]
    with transaction() as conn:
        if not conn.execute(statement,(entity_id,)).fetchone():
            raise BusinessError('Registro no encontrado.')

def movement(conn, product_id, kind, qty, order_id=None):
    conn.execute('INSERT INTO movimientos_stock(producto_id,tipo,cantidad,referencia_pedido_id) VALUES (%s,%s,%s,%s)', (product_id,kind,qty,order_id))

def receive(product_id, qty, key):
    product_id = integer(product_id,'Producto',1,MAX_INT)
    qty = integer(qty,'Ingreso',1)
    with transaction() as conn:
        old = claim(conn,key,'ingreso',[product_id,qty])
        if old is not None: return old
        row = conn.execute('SELECT * FROM stock WHERE producto_id=%s FOR UPDATE',(product_id,)).fetchone()
        if not row: raise BusinessError('Producto no encontrado.')
        if row['cantidad_actual'] + qty > MAX_INT: raise BusinessError('El ingreso supera el límite de stock.')
        conn.execute('UPDATE stock SET cantidad_actual=cantidad_actual+%s WHERE producto_id=%s',(qty,product_id))
        movement(conn,product_id,'ingreso',qty)
        return finish(conn,key,product_id)

def create_order(client_id, seller, items, notes, key):
    client_id = integer(client_id,'Cliente',1,MAX_INT)
    seller = text(seller,'Vendedor')
    notes = text(notes,'Observaciones',2000,False)
    if not items or len(items)>100: raise BusinessError('Agregá entre 1 y 100 productos.')
    lines = [(integer(p,'Producto',1,MAX_INT),integer(q,'Cantidad',1)) for p,q in items]
    if len({p for p,q in lines}) != len(lines): raise BusinessError('No se permite repetir productos.')
    lines.sort()
    with transaction() as conn:
        old = claim(conn,key,'pedido',[client_id,seller,lines,notes])
        if old is not None: return old
        if not conn.execute('SELECT id FROM clientes WHERE id=%s AND activo FOR SHARE',(client_id,)).fetchone():
            raise BusinessError('Seleccioná un cliente activo.')
        details, total = [], 0
        for p,q in lines:
            product = conn.execute('SELECT * FROM productos WHERE id=%s AND activo FOR SHARE',(p,)).fetchone()
            if not product: raise BusinessError('Seleccioná productos activos.')
            available = conn.execute('SELECT cantidad_actual FROM stock WHERE producto_id=%s',(p,)).fetchone()
            if not available or q>available['cantidad_actual']: raise BusinessError(f'Stock insuficiente: {product["nombre"]}.')
            total += q*product['precio_unitario']
            details.append((p,q,product['precio_unitario']))
        if total>MAX_TOTAL: raise BusinessError('El total supera el límite permitido.')
        order_id = conn.execute('INSERT INTO pedidos(cliente_id,vendedor,observaciones) VALUES (%s,%s,%s) RETURNING id',(client_id,seller,notes)).fetchone()['id']
        for p,q,price in details:
            conn.execute('INSERT INTO detalle_pedidos(pedido_id,producto_id,solicitada,precio_unitario) VALUES (%s,%s,%s,%s)',(order_id,p,q,price))
        return finish(conn,key,order_id)

def lock_order(conn, order_id):
    order = conn.execute('SELECT * FROM pedidos WHERE id=%s FOR UPDATE',(order_id,)).fetchone()
    if not order: raise BusinessError('Pedido no encontrado.')
    if order['estado'] in TERMINAL: raise BusinessError('El pedido está cerrado y no admite cambios.')
    details = conn.execute('SELECT * FROM detalle_pedidos WHERE pedido_id=%s ORDER BY producto_id FOR UPDATE',(order_id,)).fetchall()
    return order, details

def edit_order(order_id, seller, notes):
    seller, notes = text(seller,'Vendedor'), text(notes,'Observaciones',2000,False)
    with transaction() as conn:
        lock_order(conn,order_id)
        conn.execute('UPDATE pedidos SET vendedor=%s,observaciones=%s WHERE id=%s',(seller,notes,order_id))

def accumulated(details, totals, column):
    normalized = {integer(k,'Producto',1,MAX_INT): integer(v) for k,v in totals.items()}
    if set(normalized) != {d['producto_id'] for d in details}:
        raise BusinessError('El formulario debe incluir todos los productos del pedido.')
    for d in details:
        n = normalized[d['producto_id']]
        limit = d['solicitada'] if column=='preparada' else d['preparada']
        if n<d[column] or n>limit:
            raise BusinessError('El acumulado no puede disminuir ni superar la cantidad permitida.')
    return normalized

def prepare(order_id, totals):
    with transaction() as conn:
        order, details = lock_order(conn,order_id)
        if order['estado'] not in ('Pendiente','En preparación','Preparado'):
            raise BusinessError('Estado no válido para preparar.')
        numbers = accumulated(details,totals,'preparada')
        stocks = {}
        # Bloqueos en orden estable, incluso con pedidos cuyos ítems difieren.
        for d in details:
            pid = d['producto_id']
            stocks[pid] = conn.execute('SELECT cantidad_actual FROM stock WHERE producto_id=%s FOR UPDATE',(pid,)).fetchone()['cantidad_actual']
        for d in details:
            pid = d['producto_id']
            delta = numbers[pid]-d['preparada']
            if delta>stocks[pid]: raise BusinessError('Stock insuficiente para preparar. Actualizá la consulta.')
            if delta:
                conn.execute('UPDATE stock SET cantidad_actual=cantidad_actual-%s WHERE producto_id=%s',(delta,pid))
                movement(conn,pid,'egreso',delta,order_id)
                conn.execute('UPDATE detalle_pedidos SET preparada=%s WHERE id=%s',(numbers[pid],d['id']))
        state = 'Preparado' if all(numbers[d['producto_id']]==d['solicitada'] for d in details) else ('En preparación' if any(numbers.values()) else 'Pendiente')
        conn.execute('UPDATE pedidos SET estado=%s WHERE id=%s',(state,order_id))

def deliver(order_id, totals):
    with transaction() as conn:
        order, details = lock_order(conn,order_id)
        if order['estado']!='Preparado': raise BusinessError('Sólo se puede entregar un pedido Preparado.')
        numbers = accumulated(details,totals,'entregada')
        for d in details:
            conn.execute('UPDATE detalle_pedidos SET entregada=%s WHERE id=%s',(numbers[d['producto_id']],d['id']))
        if all(numbers[d['producto_id']]==d['solicitada'] for d in details):
            conn.execute("UPDATE pedidos SET estado='Entregado' WHERE id=%s",(order_id,))

def cancel(order_id):
    with transaction() as conn:
        order, details = lock_order(conn,order_id)
        for d in details:
            pid = d['producto_id']
            stock = conn.execute('SELECT cantidad_actual FROM stock WHERE producto_id=%s FOR UPDATE',(pid,)).fetchone()['cantidad_actual']
            delta = d['preparada']-d['entregada']
            if stock+delta>MAX_INT: raise BusinessError('La devolución supera el límite de stock.')
            if delta:
                conn.execute('UPDATE stock SET cantidad_actual=cantidad_actual+%s WHERE producto_id=%s',(delta,pid))
                movement(conn,pid,'devolucion',delta,order_id)
        conn.execute("UPDATE pedidos SET estado='Cancelado' WHERE id=%s",(order_id,))
