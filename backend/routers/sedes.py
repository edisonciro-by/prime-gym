"""CRUD de sedes del gimnasio."""
from fastapi import APIRouter, HTTPException
from pymongo.errors import DuplicateKeyError

from database import clases, entrenadores, sedes, socios
from schemas import SedeIn
from utils import buscar_o_404, oid, regex_busqueda, serializar

router = APIRouter(prefix="/api/sedes", tags=["Sedes"])


@router.get("")
def listar(q: str = "", ciudad: str = "", solo_activas: bool = False):
    filtro = {}
    if q:
        filtro["nombre"] = regex_busqueda(q)
    if ciudad:
        filtro["ciudad"] = ciudad
    if solo_activas:
        filtro["activa"] = True
    # Agregamos cuántos socios tiene cada sede para mostrarlo en la tabla
    pipeline = [
        {"$match": filtro},
        {"$lookup": {"from": "socios", "localField": "_id", "foreignField": "sede_id", "as": "s"}},
        {"$addFields": {"total_socios": {"$size": "$s"}}},
        {"$project": {"s": 0}},
        {"$sort": {"nombre": 1}},
    ]
    return serializar(list(sedes.aggregate(pipeline)))


@router.get("/{id}")
def obtener(id: str):
    return serializar(buscar_o_404(sedes, oid(id), "Sede"))


@router.post("", status_code=201)
def crear(data: SedeIn):
    try:
        r = sedes.insert_one(data.model_dump())
    except DuplicateKeyError:
        raise HTTPException(409, "Ya existe una sede con ese nombre")
    return obtener(str(r.inserted_id))


@router.put("/{id}")
def actualizar(id: str, data: SedeIn):
    _id = oid(id)
    buscar_o_404(sedes, _id, "Sede")
    # Regla: no se puede reducir la capacidad por debajo de los socios registrados
    n = socios.count_documents({"sede_id": _id})
    if data.capacidad_maxima < n:
        raise HTTPException(409, f"La sede tiene {n} socios; la capacidad no puede ser menor")
    try:
        sedes.update_one({"_id": _id}, {"$set": data.model_dump()})
    except DuplicateKeyError:
        raise HTTPException(409, "Ya existe una sede con ese nombre")
    return obtener(id)


@router.delete("/{id}")
def eliminar(id: str):
    _id = oid(id)
    buscar_o_404(sedes, _id, "Sede")
    # Regla de integridad referencial: no borrar una sede que está en uso
    uso = {
        "socios": socios.count_documents({"sede_id": _id}),
        "entrenadores": entrenadores.count_documents({"sede_id": _id}),
        "clases": clases.count_documents({"sede_id": _id}),
    }
    en_uso = {k: v for k, v in uso.items() if v}
    if en_uso:
        detalle = ", ".join(f"{v} {k}" for k, v in en_uso.items())
        raise HTTPException(409, f"No se puede eliminar: la sede tiene {detalle}. Puede marcarla como inactiva.")
    sedes.delete_one({"_id": _id})
    return {"mensaje": "Sede eliminada"}
