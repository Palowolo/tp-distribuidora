-- Esquemas privados: producción, preview y pruebas con roles independientes.
-- Sin DROP, sin datos demo y sin credenciales. Aplicación manual explícita.

CREATE SCHEMA comercial_norte;
CREATE ROLE cn_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
GRANT USAGE ON SCHEMA comercial_norte TO cn_app;
SET search_path TO comercial_norte, pg_catalog;
CREATE TABLE clientes (
 id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 nombre_comercio varchar(160) NOT NULL CHECK (length(trim(nombre_comercio)) > 0),
 contacto varchar(160) NOT NULL CHECK (length(trim(contacto)) > 0),
 telefono varchar(60) NOT NULL CHECK (length(trim(telefono)) > 0),
 direccion varchar(300) NOT NULL CHECK (length(trim(direccion)) > 0),
 activo boolean NOT NULL DEFAULT true
);
CREATE TABLE productos (
 id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 codigo varchar(40) UNIQUE NOT NULL CHECK (length(trim(codigo)) > 0),
 nombre varchar(160) NOT NULL CHECK (length(trim(nombre)) > 0),
 descripcion varchar(1000) NOT NULL DEFAULT '',
 precio_unitario integer NOT NULL CHECK (precio_unitario BETWEEN 1 AND 1000000000),
 activo boolean NOT NULL DEFAULT true
);
CREATE TABLE stock (
 id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 producto_id integer UNIQUE NOT NULL REFERENCES productos(id) ON DELETE RESTRICT,
 cantidad_actual integer NOT NULL DEFAULT 0 CHECK (cantidad_actual >= 0),
 stock_minimo integer NOT NULL DEFAULT 0 CHECK (stock_minimo BETWEEN 0 AND 1000000)
);
CREATE TABLE pedidos (
 id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 cliente_id integer NOT NULL REFERENCES clientes(id) ON DELETE RESTRICT,
 fecha timestamptz NOT NULL DEFAULT now(),
 vendedor varchar(160) NOT NULL CHECK (length(trim(vendedor)) > 0),
 estado varchar(20) NOT NULL DEFAULT 'Pendiente' CHECK (estado IN ('Pendiente','En preparación','Preparado','Entregado','Cancelado')),
 observaciones varchar(2000) NOT NULL DEFAULT ''
);
CREATE TABLE detalle_pedidos (
 id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 pedido_id integer NOT NULL REFERENCES pedidos(id) ON DELETE RESTRICT,
 producto_id integer NOT NULL REFERENCES productos(id) ON DELETE RESTRICT,
 solicitada integer NOT NULL CHECK (solicitada BETWEEN 1 AND 1000000),
 preparada integer NOT NULL DEFAULT 0,
 entregada integer NOT NULL DEFAULT 0,
 precio_unitario integer NOT NULL CHECK (precio_unitario BETWEEN 1 AND 1000000000),
 UNIQUE(pedido_id, producto_id),
 CHECK (0 <= entregada AND entregada <= preparada AND preparada <= solicitada)
);
CREATE TABLE movimientos_stock (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 producto_id integer NOT NULL REFERENCES productos(id) ON DELETE RESTRICT,
 tipo varchar(12) NOT NULL CHECK (tipo IN ('ingreso','egreso','devolucion')),
 cantidad integer NOT NULL CHECK (cantidad > 0),
 fecha timestamptz NOT NULL DEFAULT now(),
 referencia_pedido_id integer REFERENCES pedidos(id) ON DELETE RESTRICT,
 CHECK (tipo = 'ingreso' OR referencia_pedido_id IS NOT NULL)
);
-- Registro técnico, no una novena funcionalidad.
CREATE TABLE operaciones (
 clave uuid PRIMARY KEY,
 accion varchar(30) NOT NULL,
 huella char(64) NOT NULL,
 resultado_id bigint,
 fecha timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX pedidos_cliente_fecha_idx ON pedidos(cliente_id, fecha DESC);
CREATE INDEX pedidos_estado_fecha_idx ON pedidos(estado, fecha DESC);
CREATE INDEX detalle_producto_idx ON detalle_pedidos(producto_id);
CREATE INDEX movimientos_producto_fecha_idx ON movimientos_stock(producto_id, fecha DESC);
CREATE INDEX movimientos_pedido_idx ON movimientos_stock(referencia_pedido_id);
CREATE FUNCTION verificar_detalles() RETURNS trigger LANGUAGE plpgsql
SET search_path = comercial_norte, pg_catalog AS $$
DECLARE target_id integer;
BEGIN
 IF TG_TABLE_NAME = 'pedidos' THEN target_id := NEW.id;
 ELSE target_id := COALESCE(NEW.pedido_id, OLD.pedido_id); END IF;
 IF EXISTS (SELECT 1 FROM pedidos WHERE id = target_id)
 AND NOT EXISTS (SELECT 1 FROM detalle_pedidos WHERE pedido_id = target_id) THEN
 RAISE EXCEPTION 'El pedido debe contener detalles' USING ERRCODE = '23514';
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER pedido_con_detalles AFTER INSERT OR UPDATE ON pedidos
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION verificar_detalles();
CREATE CONSTRAINT TRIGGER detalle_no_vacio AFTER DELETE OR UPDATE ON detalle_pedidos
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION verificar_detalles();
REVOKE ALL ON FUNCTION verificar_detalles() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION verificar_detalles() TO cn_app;
REVOKE ALL ON SCHEMA comercial_norte FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL TABLES IN SCHEMA comercial_norte FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA comercial_norte TO cn_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA comercial_norte TO cn_app;
ALTER TABLE comercial_norte.clientes ENABLE ROW LEVEL SECURITY;
CREATE POLICY servidor ON comercial_norte.clientes TO cn_app USING (true) WITH CHECK (true);
ALTER TABLE comercial_norte.productos ENABLE ROW LEVEL SECURITY;
CREATE POLICY servidor ON comercial_norte.productos TO cn_app USING (true) WITH CHECK (true);
ALTER TABLE comercial_norte.stock ENABLE ROW LEVEL SECURITY;
CREATE POLICY servidor ON comercial_norte.stock TO cn_app USING (true) WITH CHECK (true);
ALTER TABLE comercial_norte.pedidos ENABLE ROW LEVEL SECURITY;
CREATE POLICY servidor ON comercial_norte.pedidos TO cn_app USING (true) WITH CHECK (true);
ALTER TABLE comercial_norte.detalle_pedidos ENABLE ROW LEVEL SECURITY;
CREATE POLICY servidor ON comercial_norte.detalle_pedidos TO cn_app USING (true) WITH CHECK (true);
ALTER TABLE comercial_norte.movimientos_stock ENABLE ROW LEVEL SECURITY;
CREATE POLICY servidor ON comercial_norte.movimientos_stock TO cn_app USING (true) WITH CHECK (true);
ALTER TABLE comercial_norte.operaciones ENABLE ROW LEVEL SECURITY;
CREATE POLICY servidor ON comercial_norte.operaciones TO cn_app USING (true) WITH CHECK (true);

CREATE SCHEMA cn_preview;
CREATE ROLE cn_preview_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
GRANT USAGE ON SCHEMA cn_preview TO cn_preview_app;
SET search_path TO cn_preview, pg_catalog;
CREATE TABLE clientes (
 id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 nombre_comercio varchar(160) NOT NULL CHECK (length(trim(nombre_comercio)) > 0),
 contacto varchar(160) NOT NULL CHECK (length(trim(contacto)) > 0),
 telefono varchar(60) NOT NULL CHECK (length(trim(telefono)) > 0),
 direccion varchar(300) NOT NULL CHECK (length(trim(direccion)) > 0),
 activo boolean NOT NULL DEFAULT true
);
CREATE TABLE productos (
 id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 codigo varchar(40) UNIQUE NOT NULL CHECK (length(trim(codigo)) > 0),
 nombre varchar(160) NOT NULL CHECK (length(trim(nombre)) > 0),
 descripcion varchar(1000) NOT NULL DEFAULT '',
 precio_unitario integer NOT NULL CHECK (precio_unitario BETWEEN 1 AND 1000000000),
 activo boolean NOT NULL DEFAULT true
);
CREATE TABLE stock (
 id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 producto_id integer UNIQUE NOT NULL REFERENCES productos(id) ON DELETE RESTRICT,
 cantidad_actual integer NOT NULL DEFAULT 0 CHECK (cantidad_actual >= 0),
 stock_minimo integer NOT NULL DEFAULT 0 CHECK (stock_minimo BETWEEN 0 AND 1000000)
);
CREATE TABLE pedidos (
 id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 cliente_id integer NOT NULL REFERENCES clientes(id) ON DELETE RESTRICT,
 fecha timestamptz NOT NULL DEFAULT now(),
 vendedor varchar(160) NOT NULL CHECK (length(trim(vendedor)) > 0),
 estado varchar(20) NOT NULL DEFAULT 'Pendiente' CHECK (estado IN ('Pendiente','En preparación','Preparado','Entregado','Cancelado')),
 observaciones varchar(2000) NOT NULL DEFAULT ''
);
CREATE TABLE detalle_pedidos (
 id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 pedido_id integer NOT NULL REFERENCES pedidos(id) ON DELETE RESTRICT,
 producto_id integer NOT NULL REFERENCES productos(id) ON DELETE RESTRICT,
 solicitada integer NOT NULL CHECK (solicitada BETWEEN 1 AND 1000000),
 preparada integer NOT NULL DEFAULT 0,
 entregada integer NOT NULL DEFAULT 0,
 precio_unitario integer NOT NULL CHECK (precio_unitario BETWEEN 1 AND 1000000000),
 UNIQUE(pedido_id, producto_id),
 CHECK (0 <= entregada AND entregada <= preparada AND preparada <= solicitada)
);
CREATE TABLE movimientos_stock (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 producto_id integer NOT NULL REFERENCES productos(id) ON DELETE RESTRICT,
 tipo varchar(12) NOT NULL CHECK (tipo IN ('ingreso','egreso','devolucion')),
 cantidad integer NOT NULL CHECK (cantidad > 0),
 fecha timestamptz NOT NULL DEFAULT now(),
 referencia_pedido_id integer REFERENCES pedidos(id) ON DELETE RESTRICT,
 CHECK (tipo = 'ingreso' OR referencia_pedido_id IS NOT NULL)
);
-- Registro técnico, no una novena funcionalidad.
CREATE TABLE operaciones (
 clave uuid PRIMARY KEY,
 accion varchar(30) NOT NULL,
 huella char(64) NOT NULL,
 resultado_id bigint,
 fecha timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX pedidos_cliente_fecha_idx ON pedidos(cliente_id, fecha DESC);
CREATE INDEX pedidos_estado_fecha_idx ON pedidos(estado, fecha DESC);
CREATE INDEX detalle_producto_idx ON detalle_pedidos(producto_id);
CREATE INDEX movimientos_producto_fecha_idx ON movimientos_stock(producto_id, fecha DESC);
CREATE INDEX movimientos_pedido_idx ON movimientos_stock(referencia_pedido_id);
CREATE FUNCTION verificar_detalles() RETURNS trigger LANGUAGE plpgsql
SET search_path = cn_preview, pg_catalog AS $$
DECLARE target_id integer;
BEGIN
 IF TG_TABLE_NAME = 'pedidos' THEN target_id := NEW.id;
 ELSE target_id := COALESCE(NEW.pedido_id, OLD.pedido_id); END IF;
 IF EXISTS (SELECT 1 FROM pedidos WHERE id = target_id)
 AND NOT EXISTS (SELECT 1 FROM detalle_pedidos WHERE pedido_id = target_id) THEN
 RAISE EXCEPTION 'El pedido debe contener detalles' USING ERRCODE = '23514';
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER pedido_con_detalles AFTER INSERT OR UPDATE ON pedidos
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION verificar_detalles();
CREATE CONSTRAINT TRIGGER detalle_no_vacio AFTER DELETE OR UPDATE ON detalle_pedidos
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION verificar_detalles();
REVOKE ALL ON FUNCTION verificar_detalles() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION verificar_detalles() TO cn_preview_app;
REVOKE ALL ON SCHEMA cn_preview FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL TABLES IN SCHEMA cn_preview FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA cn_preview TO cn_preview_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA cn_preview TO cn_preview_app;
ALTER TABLE cn_preview.clientes ENABLE ROW LEVEL SECURITY;
CREATE POLICY servidor ON cn_preview.clientes TO cn_preview_app USING (true) WITH CHECK (true);
ALTER TABLE cn_preview.productos ENABLE ROW LEVEL SECURITY;
CREATE POLICY servidor ON cn_preview.productos TO cn_preview_app USING (true) WITH CHECK (true);
ALTER TABLE cn_preview.stock ENABLE ROW LEVEL SECURITY;
CREATE POLICY servidor ON cn_preview.stock TO cn_preview_app USING (true) WITH CHECK (true);
ALTER TABLE cn_preview.pedidos ENABLE ROW LEVEL SECURITY;
CREATE POLICY servidor ON cn_preview.pedidos TO cn_preview_app USING (true) WITH CHECK (true);
ALTER TABLE cn_preview.detalle_pedidos ENABLE ROW LEVEL SECURITY;
CREATE POLICY servidor ON cn_preview.detalle_pedidos TO cn_preview_app USING (true) WITH CHECK (true);
ALTER TABLE cn_preview.movimientos_stock ENABLE ROW LEVEL SECURITY;
CREATE POLICY servidor ON cn_preview.movimientos_stock TO cn_preview_app USING (true) WITH CHECK (true);
ALTER TABLE cn_preview.operaciones ENABLE ROW LEVEL SECURITY;
CREATE POLICY servidor ON cn_preview.operaciones TO cn_preview_app USING (true) WITH CHECK (true);

CREATE SCHEMA cn_test;
CREATE ROLE cn_test_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
GRANT USAGE ON SCHEMA cn_test TO cn_test_app;
SET search_path TO cn_test, pg_catalog;
CREATE TABLE clientes (
 id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 nombre_comercio varchar(160) NOT NULL CHECK (length(trim(nombre_comercio)) > 0),
 contacto varchar(160) NOT NULL CHECK (length(trim(contacto)) > 0),
 telefono varchar(60) NOT NULL CHECK (length(trim(telefono)) > 0),
 direccion varchar(300) NOT NULL CHECK (length(trim(direccion)) > 0),
 activo boolean NOT NULL DEFAULT true
);
CREATE TABLE productos (
 id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 codigo varchar(40) UNIQUE NOT NULL CHECK (length(trim(codigo)) > 0),
 nombre varchar(160) NOT NULL CHECK (length(trim(nombre)) > 0),
 descripcion varchar(1000) NOT NULL DEFAULT '',
 precio_unitario integer NOT NULL CHECK (precio_unitario BETWEEN 1 AND 1000000000),
 activo boolean NOT NULL DEFAULT true
);
CREATE TABLE stock (
 id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 producto_id integer UNIQUE NOT NULL REFERENCES productos(id) ON DELETE RESTRICT,
 cantidad_actual integer NOT NULL DEFAULT 0 CHECK (cantidad_actual >= 0),
 stock_minimo integer NOT NULL DEFAULT 0 CHECK (stock_minimo BETWEEN 0 AND 1000000)
);
CREATE TABLE pedidos (
 id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 cliente_id integer NOT NULL REFERENCES clientes(id) ON DELETE RESTRICT,
 fecha timestamptz NOT NULL DEFAULT now(),
 vendedor varchar(160) NOT NULL CHECK (length(trim(vendedor)) > 0),
 estado varchar(20) NOT NULL DEFAULT 'Pendiente' CHECK (estado IN ('Pendiente','En preparación','Preparado','Entregado','Cancelado')),
 observaciones varchar(2000) NOT NULL DEFAULT ''
);
CREATE TABLE detalle_pedidos (
 id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 pedido_id integer NOT NULL REFERENCES pedidos(id) ON DELETE RESTRICT,
 producto_id integer NOT NULL REFERENCES productos(id) ON DELETE RESTRICT,
 solicitada integer NOT NULL CHECK (solicitada BETWEEN 1 AND 1000000),
 preparada integer NOT NULL DEFAULT 0,
 entregada integer NOT NULL DEFAULT 0,
 precio_unitario integer NOT NULL CHECK (precio_unitario BETWEEN 1 AND 1000000000),
 UNIQUE(pedido_id, producto_id),
 CHECK (0 <= entregada AND entregada <= preparada AND preparada <= solicitada)
);
CREATE TABLE movimientos_stock (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 producto_id integer NOT NULL REFERENCES productos(id) ON DELETE RESTRICT,
 tipo varchar(12) NOT NULL CHECK (tipo IN ('ingreso','egreso','devolucion')),
 cantidad integer NOT NULL CHECK (cantidad > 0),
 fecha timestamptz NOT NULL DEFAULT now(),
 referencia_pedido_id integer REFERENCES pedidos(id) ON DELETE RESTRICT,
 CHECK (tipo = 'ingreso' OR referencia_pedido_id IS NOT NULL)
);
-- Registro técnico, no una novena funcionalidad.
CREATE TABLE operaciones (
 clave uuid PRIMARY KEY,
 accion varchar(30) NOT NULL,
 huella char(64) NOT NULL,
 resultado_id bigint,
 fecha timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX pedidos_cliente_fecha_idx ON pedidos(cliente_id, fecha DESC);
CREATE INDEX pedidos_estado_fecha_idx ON pedidos(estado, fecha DESC);
CREATE INDEX detalle_producto_idx ON detalle_pedidos(producto_id);
CREATE INDEX movimientos_producto_fecha_idx ON movimientos_stock(producto_id, fecha DESC);
CREATE INDEX movimientos_pedido_idx ON movimientos_stock(referencia_pedido_id);
CREATE FUNCTION verificar_detalles() RETURNS trigger LANGUAGE plpgsql
SET search_path = cn_test, pg_catalog AS $$
DECLARE target_id integer;
BEGIN
 IF TG_TABLE_NAME = 'pedidos' THEN target_id := NEW.id;
 ELSE target_id := COALESCE(NEW.pedido_id, OLD.pedido_id); END IF;
 IF EXISTS (SELECT 1 FROM pedidos WHERE id = target_id)
 AND NOT EXISTS (SELECT 1 FROM detalle_pedidos WHERE pedido_id = target_id) THEN
 RAISE EXCEPTION 'El pedido debe contener detalles' USING ERRCODE = '23514';
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER pedido_con_detalles AFTER INSERT OR UPDATE ON pedidos
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION verificar_detalles();
CREATE CONSTRAINT TRIGGER detalle_no_vacio AFTER DELETE OR UPDATE ON detalle_pedidos
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION verificar_detalles();
REVOKE ALL ON FUNCTION verificar_detalles() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION verificar_detalles() TO cn_test_app;
REVOKE ALL ON SCHEMA cn_test FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL TABLES IN SCHEMA cn_test FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA cn_test TO cn_test_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA cn_test TO cn_test_app;
ALTER TABLE cn_test.clientes ENABLE ROW LEVEL SECURITY;
CREATE POLICY servidor ON cn_test.clientes TO cn_test_app USING (true) WITH CHECK (true);
ALTER TABLE cn_test.productos ENABLE ROW LEVEL SECURITY;
CREATE POLICY servidor ON cn_test.productos TO cn_test_app USING (true) WITH CHECK (true);
ALTER TABLE cn_test.stock ENABLE ROW LEVEL SECURITY;
CREATE POLICY servidor ON cn_test.stock TO cn_test_app USING (true) WITH CHECK (true);
ALTER TABLE cn_test.pedidos ENABLE ROW LEVEL SECURITY;
CREATE POLICY servidor ON cn_test.pedidos TO cn_test_app USING (true) WITH CHECK (true);
ALTER TABLE cn_test.detalle_pedidos ENABLE ROW LEVEL SECURITY;
CREATE POLICY servidor ON cn_test.detalle_pedidos TO cn_test_app USING (true) WITH CHECK (true);
ALTER TABLE cn_test.movimientos_stock ENABLE ROW LEVEL SECURITY;
CREATE POLICY servidor ON cn_test.movimientos_stock TO cn_test_app USING (true) WITH CHECK (true);
ALTER TABLE cn_test.operaciones ENABLE ROW LEVEL SECURITY;
CREATE POLICY servidor ON cn_test.operaciones TO cn_test_app USING (true) WITH CHECK (true);
RESET search_path;
GRANT TRUNCATE ON ALL TABLES IN SCHEMA cn_test TO cn_test_app;
