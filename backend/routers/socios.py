"""CRUD de socios, incluyendo sus evaluaciones físicas (array embebido)."""
from bson import ObjectId
from fastapi import APIRouter, HTTPException
from pymongo.errors import DuplicateKeyError

from database import asistencias, clases, membresias, sedes, socios
from schemas import EvaluacionIn, SocioIn
from services import actualizar_estados_membresias
from utils import a_datetime, buscar_o_404, hoy, oid, regex_busqueda, serializar

router = APIRouter(prefix="/api/socios", tags=["Socios"])


@router.get("")
def listar(q: str = "", sede_id: str = "", estado: str = "", pagina: int = 1, por_pagina: int = 20):
    """
    Lista paginada con búsqueda (nombre, apellido o documento), filtro por sede y
    filtro por estado de membresía ('activa' / 'sin_membresia').
    """
    actualizar_estados_membresias()
    filtro = {}
    if q:
        filtro["$or"] = [
            {"nombre": regex_busqueda(q)},
            {"apellido": regex_busqueda(q)},
            {"documento": regex_busqueda(q)},
        ]
    if sede_id:
        filtro["sede_id"] = oid(sede_id, "sede_id")

    pipeline = [
        {"$match": filtro},
        {"$lookup": {"from": "sedes", "localField": "sede_id", "foreignField": "_id", "as": "sede"}},
        {"$unwind": {"path": "$sede", "preserveNullAndEmptyArrays": True}},
        # $lookup trae todas las membresías del socio y $filter deja solo la activa
        {"$lookup": {"from": "membresias", "localField": "_id", "foreignField": "socio_id", "as": "ms"}},
        {
            "$addFields": {
                "membresia_activa": {
                    "$filter": {"input": "$ms", "as": "m", "cond": {"$eq": ["$$m.estado", "activa"]}}
                }
            }
        },
        {"$unwind": {"path": "$membresia_activa", "preserveNullAndEmptyArrays": True}},
    ]
    if estado == "activa":
        pipeline.append({"$match": {"membresia_activa": {"$exists": True}}})
    elif estado == "sin_membresia":
        pipeline.append({"$match": {"membresia_activa": {"$exists": False}}})
    # Dejamos solo los datos de la membresía que muestra la tabla (o null)
    pipeline.append({
        "$addFields": {
            "membresia_activa": {
                "$cond": [
                    {"$ifNull": ["$membresia_activa._id", False]},
                    {
                        "plan": "$membresia_activa.plan_snapshot.nombre",
                        "fecha_fin": "$membresia_activa.fecha_fin",
                        "saldo_pendiente": "$membresia_activa.saldo_pendiente",
                    },
                    None,
                ]
            }
        }
    })

    pipeline += [
        {
            "$project": {
                "documento": 1, "nombre": 1, "apellido": 1, "email": 1, "telefono": 1,
                "sede_id": 1, "sede_nombre": "$sede.nombre", "membresia_activa": 1,
            }
        },
        {"$sort": {"apellido": 1, "nombre": 1}},
        # $facet: en una sola consulta obtenemos el total y la página pedida
        {
            "$facet": {
                "total": [{"$count": "n"}],
                "datos": [{"$skip": (max(pagina, 1) - 1) * por_pagina}, {"$limit": por_pagina}],
            }
        },
    ]
    r = list(socios.aggregate(pipeline))[0]
    total = r["total"][0]["n"] if r["total"] else 0
    return {"total": total, "pagina": pagina, "por_pagina": por_pagina, "datos": serializar(r["datos"])}


@router.get("/{id}")
def obtener(id: str):
    """Ficha completa: datos, sede, historial de membresías y clases inscritas."""
    _id = oid(id)
    actualizar_estados_membresias()
    pipeline = [
        {"$match": {"_id": _id}},
        {"$lookup": {"from": "sedes", "localField": "sede_id", "foreignField": "_id", "as": "sede"}},
        {"$unwind": {"path": "$sede", "preserveNullAndEmptyArrays": True}},
        {
            "$lookup": {
                "from": "membresias", "localField": "_id", "foreignField": "socio_id", "as": "membresias",
            }
        },
        {
            "$lookup": {
                "from": "clases", "localField": "_id", "foreignField": "inscritos.socio_id", "as": "clases",
            }
        },
        {
            "$project": {
                "documento": 1, "nombre": 1, "apellido": 1, "fecha_nacimiento": 1, "genero": 1,
                "email": 1, "telefono": 1, "sede_id": 1, "fecha_registro": 1,
                "contacto_emergencia": 1, "evaluaciones": 1,
                "sede_nombre": "$sede.nombre",
                "membresias": {
                    "$map": {
                        "input": "$membresias", "as": "m",
                        "in": {
                            "_id": "$$m._id", "plan": "$$m.plan_snapshot.nombre", "estado": "$$m.estado",
                            "fecha_inicio": "$$m.fecha_inicio", "fecha_fin": "$$m.fecha_fin",
                            "precio_total": "$$m.precio_total", "saldo_pendiente": "$$m.saldo_pendiente",
                        },
                    }
                },
                "clases": {
                    "$map": {
                        "input": "$clases", "as": "c",
                        "in": {
                            "_id": "$$c._id", "nombre": "$$c.nombre", "dia_semana": "$$c.dia_semana",
                            "hora_inicio": "$$c.hora_inicio", "hora_fin": "$$c.hora_fin",
                        },
                    }
                },
            }
        },
    ]
    r = list(socios.aggregate(pipeline))
    if not r:
        raise HTTPException(404, "Socio no encontrado")
    socio = r[0]
    socio["membresias"].sort(key=lambda m: m["fecha_inicio"], reverse=True)
    return serializar(socio)


def _validar(data: SocioIn) -> dict:
    doc = data.model_dump()
    doc["fecha_nacimiento"] = a_datetime(data.fecha_nacimiento)
    doc["email"] = doc["email"].lower()
    doc["sede_id"] = oid(data.sede_id, "sede_id")
    sede = buscar_o_404(sedes, doc["sede_id"], "Sede")
    if not sede.get("activa", True):
        raise HTTPException(409, "La sede seleccionada está inactiva")
    return doc, sede


def _duplicado(e: DuplicateKeyError):
    campo = "documento" if "documento" in str(e) else "correo"
    raise HTTPException(409, f"Ya existe un socio con ese {campo}")


@router.post("", status_code=201)
def crear(data: SocioIn):
    doc, sede = _validar(data)
    # Regla: la sede no puede superar su capacidad máxima de socios
    if socios.count_documents({"sede_id": doc["sede_id"]}) >= sede["capacidad_maxima"]:
        raise HTTPException(409, f"La sede {sede['nombre']} alcanzó su capacidad máxima de socios")
    doc["fecha_registro"] = hoy()
    doc["evaluaciones"] = []
    try:
        r = socios.insert_one(doc)
    except DuplicateKeyError as e:
        _duplicado(e)
    return obtener(str(r.inserted_id))


@router.put("/{id}")
def actualizar(id: str, data: SocioIn):
    _id = oid(id)
    actual = buscar_o_404(socios, _id, "Socio")
    doc, sede = _validar(data)
    if doc["sede_id"] != actual["sede_id"]:
        if socios.count_documents({"sede_id": doc["sede_id"]}) >= sede["capacidad_maxima"]:
            raise HTTPException(409, f"La sede {sede['nombre']} alcanzó su capacidad máxima de socios")
    try:
        socios.update_one({"_id": _id}, {"$set": doc})
    except DuplicateKeyError as e:
        _duplicado(e)
    return obtener(id)


@router.delete("/{id}")
def eliminar(id: str):
    _id = oid(id)
    buscar_o_404(socios, _id, "Socio")
    actualizar_estados_membresias()
    # Regla: no se elimina un socio con membresía activa (cancélela primero)
    if membresias.count_documents({"socio_id": _id, "estado": "activa"}):
        raise HTTPException(409, "El socio tiene una membresía activa. Cancélela antes de eliminarlo.")
    # Eliminación en cascada para no dejar referencias huérfanas
    clases.update_many({"inscritos.socio_id": _id}, {"$pull": {"inscritos": {"socio_id": _id}}})
    m = membresias.delete_many({"socio_id": _id}).deleted_count
    a = asistencias.delete_many({"socio_id": _id}).deleted_count
    socios.delete_one({"_id": _id})
    return {"mensaje": f"Socio eliminado junto con {m} membresías y {a} asistencias de su historial"}


# --------- Evaluaciones físicas (array embebido dentro del socio) ---------
@router.post("/{id}/evaluaciones", status_code=201)
def agregar_evaluacion(id: str, data: EvaluacionIn):
    _id = oid(id)
    buscar_o_404(socios, _id, "Socio")
    fecha = a_datetime(data.fecha) if data.fecha else hoy()
    if fecha > hoy():
        raise HTTPException(400, "La fecha de la evaluación no puede ser futura")
    estatura_m = data.estatura_cm / 100
    evaluacion = {
        "_id": ObjectId(),
        "fecha": fecha,
        "peso_kg": data.peso_kg,
        "estatura_cm": data.estatura_cm,
        # Dato derivado: el IMC lo calcula el backend, no el usuario
        "imc": round(data.peso_kg / (estatura_m ** 2), 1),
        "porcentaje_grasa": data.porcentaje_grasa,
        "observaciones": data.observaciones,
    }
    socios.update_one({"_id": _id}, {"$push": {"evaluaciones": evaluacion}})
    return serializar(evaluacion)


@router.delete("/{id}/evaluaciones/{eval_id}")
def eliminar_evaluacion(id: str, eval_id: str):
    r = socios.update_one({"_id": oid(id)}, {"$pull": {"evaluaciones": {"_id": oid(eval_id)}}})
    if r.modified_count == 0:
        raise HTTPException(404, "Evaluación no encontrada")
    return {"mensaje": "Evaluación eliminada"}
