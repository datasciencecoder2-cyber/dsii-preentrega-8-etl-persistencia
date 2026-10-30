"""Orquestador de extracción, transformación, carga y reporte reproducible."""
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import tempfile

from .extraer import extraer_ventas
from .transformar import transformar_ventas
from .cargar import cargar_ventas


def _escribir_reporte_atomico(reporte: dict, ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=ruta.parent, suffix=".tmp", delete=False
        ) as archivo:
            temporal = Path(archivo.name)
            json.dump(reporte, archivo, ensure_ascii=False, indent=2)
            archivo.write("\n")
        os.replace(temporal, ruta)
    finally:
        if temporal is not None and temporal.exists():
            temporal.unlink()


def ejecutar_pipeline(origen: Path, destino: Path, esquema: Path, reporte: Path) -> dict:
    crudas = extraer_ventas(origen)
    limpias, calidad = transformar_ventas(crudas)
    carga = cargar_ventas(limpias, destino, esquema)
    resultado = {
        "ejecutado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fuente": Path(origen).name,
        "destino": Path(destino).name,
        "calidad": calidad,
        "carga": carga,
    }
    # Nunca generar un reporte de éxito si la carga falla.
    _escribir_reporte_atomico(resultado, Path(reporte))
    return resultado
