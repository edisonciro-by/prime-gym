"""Funciones auxiliares compartidas por todos los routers."""
import re
from datetime import date, datetime, timedelta, timezone

# Colombia no tiene horario de verano: UTC-5 fijo. Guardamos hora local.
ZONA_CO = timezone(timedelta(hours=-5))

from bson import ObjectId
from fastapi import HTTPException

DIAS_SEMANA = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]


def oid(valor: str, campo: str = "id") -> ObjectId:
    """Convierte un texto en ObjectId o responde 400 si no es válido."""
    if not ObjectId.is_valid(valor):
        raise HTTPException(status_code=400, detail=f"El {campo} '{valor}' no es un identificador válido")
    return ObjectId(valor)


def serializar(dato):
    """Convierte ObjectId y fechas en texto para poder enviarlos como JSON."""
    if isinstance(dato, list):
        return [serializar(x) for x in dato]
    if isinstance(dato, dict):
        return {("id" if k == "_id" else k): serializar(v) for k, v in dato.items()}
    if isinstance(dato, ObjectId):
        return str(dato)
    if isinstance(dato, datetime):
        return dato.isoformat()
    return dato


def a_datetime(d: date) -> datetime:
    """MongoDB guarda fechas como datetime; convertimos los date de Pydantic."""
    if isinstance(d, datetime):
        return d
    return datetime(d.year, d.month, d.day)


def ahora() -> datetime:
    return datetime.now(ZONA_CO).replace(tzinfo=None)


def hoy() -> datetime:
    n = ahora()
    return datetime(n.year, n.month, n.day)


def buscar_o_404(coleccion, _id: ObjectId, nombre: str):
    doc = coleccion.find_one({"_id": _id})
    if not doc:
        raise HTTPException(status_code=404, detail=f"{nombre} no encontrado(a)")
    return doc


def regex_busqueda(texto: str):
    """Búsqueda parcial sin distinguir mayúsculas (escapando caracteres especiales)."""
    return {"$regex": re.escape(texto.strip()), "$options": "i"}


def minutos(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def se_cruzan(inicio1: str, fin1: str, inicio2: str, fin2: str) -> bool:
    """Dos franjas horarias se cruzan si una empieza antes de que termine la otra."""
    return minutos(inicio1) < minutos(fin2) and minutos(inicio2) < minutos(fin1)


def pesos(valor: int) -> str:
    """Formato de moneda colombiana: 79000 -> 79.000"""
    return f"{valor:,}".replace(",", ".")
