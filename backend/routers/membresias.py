"""
Membresías: venta de planes a socios.
Los pagos se guardan EMBEBIDOS dentro de la membresía (pertenecen a ella y
siempre se consultan juntos), y el plan se referencia con plan_id + una copia
parcial (plan_snapshot) para conservar las condiciones con las que se vendió.
"""
from datetime import timedelta

from bson import ObjectId
from fastapi import APIRouter, HTTPException

from database import clases, membresias, planes, socios
from schemas import MembresiaIn, PagoIn
from services import actualizar_estados_membresias
from utils import pesos, a_datetime, ahora, buscar_o_404, hoy, oid, regex_busqueda, serializar

router = APIRouter(prefix="/api/membresias", tags=["Membresías"])


def _pipeline(filtro):
    return [
        {"$match": filtro},
        {"$lookup": {"from": "socios", "localField": "socio_id", "foreignField": "_id", "as": "socio"}},
        {"$unwind": "$socio"},
        {"$lookup": {"from": "sedes", "localField": "socio.sede_id", "foreignField": "_id", "as": "sede"}},
        {"$unwind": {"path": "$sede", "preserveNullAndEmptyArrays": True}},
        {
            "$addFields": {
                "socio_nombre": {"$concat": ["$socio.nombre", " ", "$socio.apellido"]},
                "socio_documento": "$socio.documento",
                "sede_nombre": "$sede.nombre",
                "plan_nombre": "$plan_snapshot.nombre",
                "total_pagado": {"$sum": "$pagos.valor"},
            }
        },
        {"$project": {"socio": 0, "sede": 0}},
        {"$sort": {"fecha_inicio": -1}},
    ]


@router.get("")
def listar(estado: str = "", plan_id: str = "", q: str = "", con_saldo: bool = False, limite: int = 200):
    actualizar_estados_membresias()
    filtro = {}
    if estado:
        filtro["estado"] = estado
    if plan_id:
        filtro["plan_id"] = oid(plan_id, "plan_id")
    if con_saldo:
        filtro["saldo_pendiente"] = {"$gt": 0}
    pipeline = _pipeline(filtro)
    if q:  # búsqueda por nombre o documento del socio (después del $lookup)
        pipeline.insert(-1, {"$match": {"$or": [{"socio_nombre": regex_busqueda(q)}, {"socio_documento": regex_busqueda(q)}]}})
    pipeline.append({"$limit": limite})
    return serializar(list(membresias.aggregate(pipeline)))


@router.get("/{id}")
def obtener(id: str):
    actualizar_estados_membresias()
    r = list(membresias.aggregate(_pipeline({"_id": oid(id)})))
    if not r:
        raise HTTPException(404, "Membresía no encontrada")
    return serializar(r[0])


@router.post("", status_code=201)
def crear(data: MembresiaIn):
    actualizar_estados_membresias()
    socio_id = oid(data.socio_id, "socio_id")
    plan_id = oid(data.plan_id, "plan_id")
    buscar_o_404(socios, socio_id, "Socio")
    plan = buscar_o_404(planes, plan_id, "Plan")

    if not plan.get("activo", True):
        raise HTTPException(409, "El plan seleccionado no está activo")

    inicio = a_datetime(data.fecha_inicio)
    if inicio < hoy() - timedelta(days=7):
        raise HTTPException(400, "La fecha de inicio no puede ser anterior a 7 días")
    if inicio > hoy() + timedelta(days=60):
        raise HTTPException(400, "Solo se pueden vender membresías que inicien en los próximos 60 días")

    # La fecha de fin la calcula el sistema a partir de la duración del plan
    fin = inicio + timedelta(days=plan["duracion_dias"] - 1)

    # Regla: un socio no puede tener dos membresías activas que se crucen
    cruce = membresias.find_one(
        {"socio_id": socio_id, "estado": "activa", "fecha_inicio": {"$lte": fin}, "fecha_fin": {"$gte": inicio}}
    )
    if cruce:
        raise HTTPException(
            409,
            f"El socio ya tiene una membresía activa hasta {cruce['fecha_fin']:%Y-%m-%d}. "
            "Programe la nueva para después de esa fecha.",
        )

    pagos = []
    if data.pago_inicial:
        if data.pago_inicial.valor > plan["precio"]:
            raise HTTPException(400, "El pago inicial no puede superar el precio del plan")
        pagos.append({"_id": ObjectId(), "fecha": ahora(), **data.pago_inicial.model_dump()})

    doc = {
        "socio_id": socio_id,
        "plan_id": plan_id,
        "plan_snapshot": {  # patrón "referencia extendida"
            "nombre": plan["nombre"],
            "duracion_dias": plan["duracion_dias"],
            "incluye_clases": plan["incluye_clases"],
            "acceso_todas_sedes": plan["acceso_todas_sedes"],
        },
        "fecha_inicio": inicio,
        "fecha_fin": fin,
        "precio_total": plan["precio"],
        "pagos": pagos,
        "saldo_pendiente": plan["precio"] - sum(p["valor"] for p in pagos),
        "estado": "activa",
        "fecha_creacion": ahora(),
    }
    r = membresias.insert_one(doc)
    return obtener(str(r.inserted_id))


@router.post("/{id}/pagos", status_code=201)
def registrar_pago(id: str, pago: PagoIn):
    _id = oid(id)
    m = buscar_o_404(membresias, _id, "Membresía")
    if m["estado"] == "cancelada":
        raise HTTPException(409, "No se pueden registrar pagos en una membresía cancelada")
    if m["saldo_pendiente"] <= 0:
        raise HTTPException(409, "La membresía ya está totalmente paga")
    if pago.valor > m["saldo_pendiente"]:
        raise HTTPException(400, f"El pago supera el saldo pendiente (${pesos(m['saldo_pendiente'])})")
    nuevo = {"_id": ObjectId(), "fecha": ahora(), **pago.model_dump()}
    # $push agrega el pago al array embebido y $inc descuenta el saldo, en una
    # sola operación atómica sobre el documento.
    membresias.update_one({"_id": _id}, {"$push": {"pagos": nuevo}, "$inc": {"saldo_pendiente": -pago.valor}})
    return obtener(id)


@router.put("/{id}/cancelar")
def cancelar(id: str):
    _id = oid(id)
    m = buscar_o_404(membresias, _id, "Membresía")
    if m["estado"] != "activa":
        raise HTTPException(409, f"Solo se pueden cancelar membresías activas (estado actual: {m['estado']})")
    membresias.update_one({"_id": _id}, {"$set": {"estado": "cancelada", "fecha_cancelacion": ahora()}})
    # Al cancelar, el socio pierde sus cupos en las clases
    clases.update_many({"inscritos.socio_id": m["socio_id"]}, {"$pull": {"inscritos": {"socio_id": m["socio_id"]}}})
    return obtener(id)


@router.delete("/{id}")
def eliminar(id: str):
    _id = oid(id)
    m = buscar_o_404(membresias, _id, "Membresía")
    # Regla: una membresía con pagos es un registro contable; no se borra, se cancela
    if m["pagos"]:
        raise HTTPException(409, "La membresía tiene pagos registrados; no se puede eliminar. Use 'Cancelar'.")
    membresias.delete_one({"_id": _id})
    return {"mensaje": "Membresía eliminada"}
