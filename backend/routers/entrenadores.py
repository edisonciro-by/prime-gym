"""CRUD de entrenadores."""
from fastapi import APIRouter, HTTPException
from pymongo.errors import DuplicateKeyError

from database import clases, entrenadores, sedes
from schemas import EntrenadorIn
from utils import buscar_o_404, hoy, oid, regex_busqueda, serializar

router = APIRouter(prefix="/api/entrenadores", tags=["Entrenadores"])


def _pipeline(filtro):
    # $lookup para mostrar el NOMBRE de la sede y no solo su _id
    return [
        {"$match": filtro},
        {"$lookup": {"from": "sedes", "localField": "sede_id", "foreignField": "_id", "as": "sede"}},
        {"$unwind": {"path": "$sede", "preserveNullAndEmptyArrays": True}},
        {"$lookup": {"from": "clases", "localField": "_id", "foreignField": "entrenador_id", "as": "c"}},
        {"$addFields": {"sede_nombre": "$sede.nombre", "total_clases": {"$size": "$c"}}},
        {"$project": {"sede": 0, "c": 0}},
        {"$sort": {"nombre": 1}},
    ]


@router.get("")
def listar(q: str = "", sede_id: str = "", especialidad: str = "", solo_activos: bool = False):
    filtro = {}
    if q:
        filtro["$or"] = [{"nombre": regex_busqueda(q)}, {"documento": regex_busqueda(q)}]
    if sede_id:
        filtro["sede_id"] = oid(sede_id, "sede_id")
    if especialidad:
        filtro["especialidades"] = especialidad  # busca dentro del array
    if solo_activos:
        filtro["activo"] = True
    return serializar(list(entrenadores.aggregate(_pipeline(filtro))))


@router.get("/{id}")
def obtener(id: str):
    r = list(entrenadores.aggregate(_pipeline({"_id": oid(id)})))
    if not r:
        raise HTTPException(404, "Entrenador no encontrado")
    return serializar(r[0])


def _validar(data: EntrenadorIn) -> dict:
    doc = data.model_dump()
    doc["sede_id"] = oid(data.sede_id, "sede_id")
    sede = buscar_o_404(sedes, doc["sede_id"], "Sede")
    if not sede.get("activa", True):
        raise HTTPException(409, "No se puede asignar un entrenador a una sede inactiva")
    return doc


@router.post("", status_code=201)
def crear(data: EntrenadorIn):
    doc = _validar(data)
    doc["fecha_ingreso"] = hoy()
    try:
        r = entrenadores.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "Ya existe un entrenador con ese documento")
    return obtener(str(r.inserted_id))


@router.put("/{id}")
def actualizar(id: str, data: EntrenadorIn):
    _id = oid(id)
    actual = buscar_o_404(entrenadores, _id, "Entrenador")
    doc = _validar(data)
    activas = clases.count_documents({"entrenador_id": _id, "activa": True})
    # Regla: si tiene clases activas no puede cambiar de sede ni desactivarse
    if activas and doc["sede_id"] != actual["sede_id"]:
        raise HTTPException(409, f"El entrenador tiene {activas} clases activas en su sede actual; reasígnelas primero")
    if activas and not doc["activo"]:
        raise HTTPException(409, f"El entrenador tiene {activas} clases activas; no se puede desactivar")
    # Regla: no puede quitar una especialidad que está dictando
    tipos_dictados = clases.distinct("tipo", {"entrenador_id": _id, "activa": True})
    faltan = set(tipos_dictados) - set(doc["especialidades"])
    if faltan:
        raise HTTPException(409, f"El entrenador dicta clases de {', '.join(faltan)}; no puede quitar esa especialidad")
    try:
        entrenadores.update_one({"_id": _id}, {"$set": doc})
    except DuplicateKeyError:
        raise HTTPException(409, "Ya existe un entrenador con ese documento")
    return obtener(id)


@router.delete("/{id}")
def eliminar(id: str):
    _id = oid(id)
    buscar_o_404(entrenadores, _id, "Entrenador")
    n = clases.count_documents({"entrenador_id": _id})
    if n:
        raise HTTPException(409, f"No se puede eliminar: el entrenador tiene {n} clases asignadas")
    entrenadores.delete_one({"_id": _id})
    return {"mensaje": "Entrenador eliminado"}
