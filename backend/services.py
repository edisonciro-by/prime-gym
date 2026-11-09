"""
Lógica de negocio reutilizada por varios routers.
"""
from bson import ObjectId

from database import membresias
from utils import hoy


def actualizar_estados_membresias():
    """
    Regla: una membresía 'activa' cuya fecha_fin ya pasó queda 'vencida'.
    Se ejecuta antes de las operaciones que dependen del estado, así la base
    de datos siempre refleja la realidad sin necesidad de un proceso aparte.
    """
    membresias.update_many(
        {"estado": "activa", "fecha_fin": {"$lt": hoy()}},
        {"$set": {"estado": "vencida"}},
    )


def membresia_vigente(socio_id: ObjectId):
    """Devuelve la membresía activa y vigente HOY de un socio (o None)."""
    actualizar_estados_membresias()
    h = hoy()
    return membresias.find_one(
        {"socio_id": socio_id, "estado": "activa", "fecha_inicio": {"$lte": h}, "fecha_fin": {"$gte": h}}
    )
