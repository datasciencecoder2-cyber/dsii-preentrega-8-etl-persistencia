"""L: cargar idempotentemente en SQLite, con transacción y rollback ante fallos."""
from contextlib import closing
from dataclasses import astuple
from pathlib import Path
import sqlite3
from .transformar import Venta

CAMPOS = (
    "id_venta", "fecha", "mes", "cliente_id", "producto", "categoria",
    "cantidad", "precio_unitario_centavos", "total_centavos"
)
COLUMNAS_ACTUALIZABLES = CAMPOS[1:]
SQL_UPSERT = f"""
INSERT INTO ventas_analiticas ({', '.join(CAMPOS)})
VALUES ({', '.join('?' for _ in CAMPOS)})
ON CONFLICT(id_venta) DO UPDATE SET
{', '.join(f'{col} = excluded.{col}' for col in COLUMNAS_ACTUALIZABLES)}
WHERE { ' OR '.join(f'ventas_analiticas.{col} IS NOT excluded.{col}' for col in COLUMNAS_ACTUALIZABLES) };
"""


def cargar_ventas(
    ventas: list[Venta], destino: Path, esquema: Path, simular_fallo: bool = False
) -> dict:
    """La actualización por clave evita duplicados y refleja correcciones del CSV."""
    destino = Path(destino)
    esquema = Path(esquema)
    if not esquema.is_file():
        raise FileNotFoundError(f"No existe el DDL: {esquema}")
    destino.parent.mkdir(parents=True, exist_ok=True)

    with closing(sqlite3.connect(destino, timeout=10)) as conexion:
        # DDL idempotente, ejecutado antes de la transacción de datos.
        conexion.executescript(esquema.read_text(encoding="utf-8"))
        conexion.execute("BEGIN IMMEDIATE")
        insertadas = actualizadas = sin_cambios = 0
        try:
            for i, venta in enumerate(ventas):
                datos = astuple(venta)
                anterior = conexion.execute(
                    "SELECT " + ", ".join(COLUMNAS_ACTUALIZABLES)
                    + " FROM ventas_analiticas WHERE id_venta = ?",
                    (venta.id_venta,)
                ).fetchone()
                if anterior is None:
                    insertadas += 1
                elif anterior == datos[1:]:
                    sin_cambios += 1
                else:
                    actualizadas += 1
                conexion.execute(SQL_UPSERT, datos)
                if simular_fallo and i == 0:
                    raise RuntimeError("Fallo simulado para demostrar rollback atómico")
            conexion.commit()
        except Exception:
            conexion.rollback()
            raise
        total_filas, total_centavos = conexion.execute(
            "SELECT COUNT(*), COALESCE(SUM(total_centavos),0) FROM ventas_analiticas"
        ).fetchone()
        resumen = conexion.execute(
            "SELECT mes, categoria, cantidad_ventas, unidades, ingresos_centavos "
            "FROM resumen_mensual ORDER BY mes, categoria"
        ).fetchall()
    return {
        "insertadas": insertadas, "actualizadas": actualizadas,
        "sin_cambios": sin_cambios,
        "filas_en_sqlite": total_filas,
        "ingresos_centavos_en_sqlite": total_centavos,
        "resumen_mensual": [
            dict(zip(("mes", "categoria", "cantidad_ventas", "unidades", "ingresos_centavos"), fila))
            for fila in resumen
        ]
    }
