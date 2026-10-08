"""Demo manual repetible: python -m scripts.seed --confirm-demo."""
import argparse
from uuid import uuid5, NAMESPACE_URL
from dotenv import load_dotenv
load_dotenv()
from distribuidora import services as s
from distribuidora.database import query

def key(value): return str(uuid5(NAMESPACE_URL,'comercial-norte/demo-v1/'+value))

def seed():
    names=['Almacén Los Lapachos','Despensa San Miguel','Minimercado Aurora','Comercial Las Palmas',
           'Autoservicio Primavera','Despensa El Encuentro','Almacén Santa Rosa','Comercio Yvoty']
    clients=[s.save_client(dict(nombre_comercio=name,contacto=f'Contacto ficticio {i+1}',telefono=f'000-000-{i+1:03}',direccion=f'Calle Demo {i+1}, Asunción (ficticia)'),key('cliente'+str(i))) for i,name in enumerate(names)]
    catalog=['Arroz 1 kg','Azúcar 1 kg','Aceite 900 ml','Yerba 500 g','Harina 1 kg','Fideos 400 g','Sal 1 kg',
             'Leche 1 l','Café 100 g','Té 25 sobres','Galletitas 200 g','Jabón 200 g','Detergente 500 ml',
             'Lavandina 1 l','Papel higiénico 4 u','Atún 170 g','Tomate 500 g','Poroto 1 kg','Maíz 500 g','Avena 400 g']
    products=[]
    for i,name in enumerate(catalog):
        p=s.save_product(dict(codigo=f'DEMO-{i+1:03}',nombre=name,descripcion='Producto ficticio para demostración',precio_unitario=8000+i*700,stock_minimo=10),key('producto'+str(i)))
        products.append(p)
        s.receive(p,2 if i>=18 else 100,key('ingreso'+str(i)))
    for i in range(10):
        operation=key('pedido'+str(i))
        if query('SELECT 1 FROM operaciones WHERE clave=%s',(operation,)): continue
        pid=products[i]
        oid=s.create_order(clients[i%8],'Vendedor Demo',[(pid,5)],'DEMO v1 · datos ficticios',operation)
        if i in (1,6): s.prepare(oid,{pid:2})
        elif i in (2,3,4,7,8,9):
            s.prepare(oid,{pid:5})
            if i in (3,7,9): s.deliver(oid,{pid:3})
            elif i==4: s.deliver(oid,{pid:5})
            if i in (8,9): s.cancel(oid)
        elif i==5: s.cancel(oid)
    print('Demo verificada: 8 clientes, 20 productos y 10 pedidos identificados por claves estables.')
    print(query('SELECT estado,count(*) AS cantidad FROM pedidos GROUP BY estado ORDER BY estado'))
    mismatches=query("""SELECT s.producto_id FROM stock s LEFT JOIN movimientos_stock m ON m.producto_id=s.producto_id
      GROUP BY s.producto_id,s.cantidad_actual HAVING s.cantidad_actual<>COALESCE(sum(CASE WHEN m.tipo='egreso' THEN -m.cantidad::bigint ELSE m.cantidad::bigint END),0)""")
    if mismatches: raise RuntimeError('Inventario no conciliado.')
    print('Existencias conciliadas con movimientos.')

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--confirm-demo',action='store_true'); args=parser.parse_args()
    if not args.confirm_demo: parser.error('Confirmá el uso de datos ficticios con --confirm-demo.')
    seed()
