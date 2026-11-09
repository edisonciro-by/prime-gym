"""CRUD de planes de membresía."""
from fastapi import APIRouter, HTTPException
from pymongo.errors import DuplicateKeyError

from database import membresias, planes
from schemas import PlanIn
from utils import buscar_o_404, oid, regex_busqueda, serializar

router = APIRouter(prefix="/api/planes", tags=["Planes"])


@router.get("")
def listar(q: str = "", solo_activos: bool = False, precio_max: int | None = None):
    filtro = {}
    if q:
        filtro["nombre"] = regex_busqueda(q)
    if solo_activos:
        filtro["activo"] = True
    if precio_max:
        filtro["precio"] = {"$lte": precio_max}
    return serializar(list(planes.find(filtro).sort("precio", 1)))


@router.get("/{id}")
def obtener(id: str):
    return serializar(buscar_o_404(planes, oid(id), "Plan"))


@router.post("", status_code=201)
def crear(data: PlanIn):
    try:
        r = planes.insert_one(data.model_dump())
    except DuplicateKeyError:
        raise HTTPException(409, "Ya existe un plan con ese nombre")
    return obtener(str(r.inserted_id))


@router.put("/{id}")
def actualizar(id: str, data: PlanIn):
    _id = oid(id)
    buscar_o_404(planes, _id, "Plan")
    # Nota: cambiar el precio NO altera membresías ya vendidas, porque cada
    # membresía guarda su propio precio_total y una copia (snapshot) del plan.
    try:
        planes.update_one({"_id": _id}, {"$set": data.model_dump()})
    except DuplicateKeyError:
        raise HTTPException(409, "Ya existe un plan con ese nombre")
    return obtener(id)


@router.delete("/{id}")
def eliminar(id: str):
    _id = oid(id)
    buscar_o_404(planes, _id, "Plan")
    if membresias.count_documents({"plan_id": _id}):
        raise HTTPException(
            409, "No se puede eliminar: hay membresías vendidas con este plan. Márquelo como inactivo."
        )
    planes.delete_one({"_id": _id})
    return {"mensaje": "Plan eliminado"}
