-- Modelo analítico de ventas: una fila por transacción confirmada.
-- Se almacenan importes enteros en centavos para evitar errores de coma flotante.
CREATE TABLE IF NOT EXISTS ventas_analiticas (
    id_venta                 INTEGER PRIMARY KEY,
    fecha                    TEXT NOT NULL CHECK (length(fecha) = 10),
    mes                      TEXT NOT NULL CHECK (length(mes) = 7),
    cliente_id               INTEGER NOT NULL CHECK (cliente_id > 0),
    producto                 TEXT NOT NULL CHECK (length(trim(producto)) > 0),
    categoria                TEXT NOT NULL CHECK (categoria IN ('Alimentos','Hogar','Tecnologia')),
    cantidad                 INTEGER NOT NULL CHECK (cantidad > 0),
    precio_unitario_centavos INTEGER NOT NULL CHECK (precio_unitario_centavos > 0),
    total_centavos           INTEGER NOT NULL CHECK (
        total_centavos = cantidad * precio_unitario_centavos
    )
);

CREATE INDEX IF NOT EXISTS ix_ventas_mes_categoria
ON ventas_analiticas (mes, categoria);

-- Resumen analítico sin perder datos de transacciones en la tabla principal.
CREATE VIEW IF NOT EXISTS resumen_mensual AS
SELECT
    mes,
    categoria,
    COUNT(*) AS cantidad_ventas,
    SUM(cantidad) AS unidades,
    SUM(total_centavos) AS ingresos_centavos
FROM ventas_analiticas
GROUP BY mes, categoria;
