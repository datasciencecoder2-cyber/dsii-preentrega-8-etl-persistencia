"""T: validar y normalizar ventas sin duplicar identificadores de transacción."""
from dataclasses import dataclass, asdict
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import unicodedata


@dataclass(frozen=True)
class Venta:
    id_venta: int
    fecha: str
    mes: str
    cliente_id: int
    producto: str
    categoria: str
    cantidad: int
    precio_unitario_centavos: int
    total_centavos: int


def _normalizar_categoria(valor: str) -> str:
    texto = unicodedata.normalize("NFKD", (valor or "").strip().lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    equivalencias = {"alimentos": "Alimentos", "hogar": "Hogar", "tecnologia": "Tecnologia"}
    if texto not in equivalencias:
        raise ValueError("categoria desconocida")
    return equivalencias[texto]


def _entero_positivo(valor: str, nombre: str) -> int:
    try:
        numero = int((valor or "").strip())
    except (ValueError, AttributeError):
        raise ValueError(f"{nombre} no es entero") from None
    if numero <= 0:
        raise ValueError(f"{nombre} debe ser mayor a cero")
    return numero


def _precio_centavos(valor: str) -> int:
    try:
        precio = Decimal((valor or "").strip().replace(",", "."))
    except (InvalidOperation, AttributeError):
        raise ValueError("precio_unitario no es válido") from None
    if not precio.is_finite() or precio <= 0:
        raise ValueError("precio_unitario debe ser positivo y finito")
    centavos = int((precio * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if centavos <= 0:
        raise ValueError("precio_unitario menor a un centavo")
    return centavos


def transformar_ventas(filas: list[dict[str, str]]) -> tuple[list[Venta], dict]:
    """Descartar inválidas/no confirmadas; conflictos de ID abortan todo el lote."""
    mapa: dict[int, Venta] = {}
    reporte = {
        "filas_origen": len(filas),
        "duplicados_identicos": 0,
        "no_confirmadas": 0,
        "filas_invalidas": 0,
        "detalles_invalidas": []
    }
    for numero_fila, fila in enumerate(filas, start=2):
        estado = (fila.get("estado") or "").strip().casefold()
        if estado in {"cancelada", "pendiente"}:
            reporte["no_confirmadas"] += 1
            continue
        if estado != "confirmada":
            reporte["filas_invalidas"] += 1
            reporte["detalles_invalidas"].append({"fila_csv": numero_fila, "motivo": "estado no reconocido"})
            continue
        try:
            fecha = date.fromisoformat((fila.get("fecha") or "").strip()).isoformat()
            cantidad = _entero_positivo(fila.get("cantidad"), "cantidad")
            precio = _precio_centavos(fila.get("precio_unitario"))
            producto = (fila.get("producto") or "").strip()
            if not producto:
                raise ValueError("producto vacío")
            venta = Venta(
                id_venta=_entero_positivo(fila.get("id_venta"), "id_venta"),
                fecha=fecha,
                mes=fecha[:7],
                cliente_id=_entero_positivo(fila.get("cliente_id"), "cliente_id"),
                producto=producto,
                categoria=_normalizar_categoria(fila.get("categoria")),
                cantidad=cantidad,
                precio_unitario_centavos=precio,
                total_centavos=cantidad * precio,
            )
        except ValueError as error:
            reporte["filas_invalidas"] += 1
            reporte["detalles_invalidas"].append({"fila_csv": numero_fila, "motivo": str(error)})
            continue
        anterior = mapa.get(venta.id_venta)
        if anterior is not None:
            if anterior != venta:
                raise ValueError(
                    f"Conflicto en id_venta={venta.id_venta}: el CSV tiene dos transacciones diferentes "
                    "con el mismo identificador. No se carga ningún dato."
                )
            reporte["duplicados_identicos"] += 1
            continue
        mapa[venta.id_venta] = venta

    reporte["ventas_validas"] = len(mapa)
    reporte["total_centavos_en_archivo"] = sum(v.total_centavos for v in mapa.values())
    if not mapa:
        raise ValueError("No existen ventas confirmadas válidas para cargar")
    return list(mapa.values()), reporte
