"""Punto de entrada de la Pre-entrega 8: ejecución automatizada del ETL."""
from pathlib import Path
import argparse
import sys

from src.pipeline import ejecutar_pipeline

BASE = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pipeline de ventas CSV a SQLite")
    parser.add_argument("--origen", type=Path, default=BASE / "datos" / "ventas_transaccionales.csv")
    parser.add_argument("--db", type=Path, default=BASE / "salidas" / "analytics.db")
    parser.add_argument("--ddl", type=Path, default=BASE / "schema.sql")
    parser.add_argument("--reporte", type=Path, default=BASE / "salidas" / "reporte_etl.json")
    args = parser.parse_args(argv)

    try:
        datos = ejecutar_pipeline(args.origen, args.db, args.ddl, args.reporte)
    except (ValueError, OSError, RuntimeError) as error:
        print(f"ETL DETENIDO: {error}", file=sys.stderr)
        return 1
    calidad, carga = datos["calidad"], datos["carga"]
    print("PRE-ENTREGA 8 — ETL CSV A SQLITE")
    print(f"Filas leídas: {calidad['filas_origen']}")
    print(f"Duplicados exactos: {calidad['duplicados_identicos']}")
    print(f"No confirmadas: {calidad['no_confirmadas']}")
    print(f"Inválidas: {calidad['filas_invalidas']}")
    print(f"Ventas válidas: {calidad['ventas_validas']}")
    print(f"Insertadas: {carga['insertadas']} | Actualizadas: {carga['actualizadas']} | Sin cambios: {carga['sin_cambios']}")
    print(f"Filas en SQLite: {carga['filas_en_sqlite']}")
    print(f"Ingresos en SQLite (centavos): {carga['ingresos_centavos_en_sqlite']}")
    print(f"Base generada: {args.db}")
    print(f"Reporte generado: {args.reporte}")
    print("ETL FINALIZADO: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
