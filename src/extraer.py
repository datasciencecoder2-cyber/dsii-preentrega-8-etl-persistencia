"""E: extraer transacciones desde un CSV local sin dependencias externas."""
from pathlib import Path
import csv

COLUMNAS = (
    "id_venta", "fecha", "cliente_id", "producto", "categoria",
    "cantidad", "precio_unitario", "estado"
)


def extraer_ventas(ruta: Path) -> list[dict[str, str]]:
    ruta = Path(ruta)
    if not ruta.is_file():
        raise FileNotFoundError(f"No existe el CSV de origen: {ruta}")

    # utf-8-sig también acepta archivos UTF-8 con BOM (frecuentes en Windows).
    with ruta.open("r", encoding="utf-8-sig", newline="") as archivo:
        lector = csv.DictReader(archivo)
        if lector.fieldnames is None:
            raise ValueError("El CSV de origen no tiene encabezado")
        presentes = {campo.strip() for campo in lector.fieldnames}
        faltantes = set(COLUMNAS) - presentes
        if faltantes:
            raise ValueError("Faltan columnas obligatorias: " + ", ".join(sorted(faltantes)))
        filas = list(lector)

    if not filas:
        raise ValueError("El archivo de origen no contiene transacciones")
    return filas
