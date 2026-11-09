"""
Clases grupales. La lista de inscritos se guarda EMBEBIDA dentro de la clase
(array acotado por el cupo máximo, ≤ 50), y cada inscrito REFERENCIA al socio
mediante socio_id.
"""
from fastapi import APIRouter, HTTPException

from database import clases, entrenadores, sedes, socios
from schemas import ClaseIn, InscripcionIn
from services import membresia_vigente
from utils import DIAS_SEMANA, ahora, buscar_o_404, oid, regex_busqueda, se_cruzan, serializar

router = APIRouter(prefix="/api/clases", tags=["Clases"])


def _pipeline(filtro):
    # Múltiples $lookup: entrenador, sede y los socios inscritos
    return [
        {"$match": filtro},
        {"$lookup": {"from": "entrenadores", "localField": "entrenador_id", "foreignField": "_id", "as": "ent"}},
        {"$lookup": {"from": "sedes", "localField": "sede_id", "foreignField": "_id", "as": "sede"}},
        # Lista de _id de los inscritos (array embebido) para traer sus datos
        {"$addFields": {"ids_inscritos": "$inscritos.socio_id"}},
        {"$lookup": {"from": "socios", "localField": "ids_inscritos", "foreignField": "_id", "as": "socios_ins"}},
        {
            "$addFields": {
                "entrenador_nombre": {"$arrayElemAt": ["$ent.nombre", 0]},
                "sede_nombre": {"$arrayElemAt": ["$sede.nombre", 0]},
                "total_inscritos": {"$size": "$inscritos"},
                "cupos_disponibles": {"$subtract": ["$cupo_maximo", {"$size": "$inscritos"}]},
                "inscritos_detalle": {
                    "$map": {
                        "input": "$socios_ins", "as": "s",
                        "in": {
                            "socio_id": "$$s._id",
                            "nombre": {"$concat": ["$$s.nombre", " ", "$$s.apellido"]},
                            "documento": "$$s.documento",
                        },
                    }
                },
            }
        },
        {"$project": {"ent": 0, "sede": 0, "socios_ins": 0, "ids_inscritos": 0}},
    ]


def _ordenar(lista):
    lista.sort(key=lambda c: (DIAS_SEMANA.index(c["dia_semana"]), c["hora_inicio"]))
    return lista


@router.get("")
def listar(q: str = "", sede_id: str = "", dia: str = "", tipo: str = "", entrenador_id: str = "",
           con_cupo: bool = False):
    filtro = {}
    if q:
        filtro["nombre"] = regex_busqueda(q)
    if sede_id:
        filtro["sede_id"] = oid(sede_id, "sede_id")
    if dia:
        filtro["dia_semana"] = dia
    if tipo:
        filtro["tipo"] = tipo
    if entrenador_id:
        filtro["entrenador_id"] = oid(entrenador_id, "entrenador_id")
    if con_cupo:
        # $expr permite comparar dos campos del mismo documento
        filtro["$expr"] = {"$lt": [{"$size": "$inscritos"}, "$cupo_maximo"]}
    return serializar(_ordenar(list(clases.aggregate(_pipeline(filtro)))))


@router.get("/{id}")
def obtener(id: str):
    r = list(clases.aggregate(_pipeline({"_id": oid(id)})))
    if not r:
        raise HTTPException(404, "Clase no encontrada")
    return serializar(r[0])


def _validar(data: ClaseIn, excluir_id=None) -> dict:
    doc = data.model_dump()
    doc["entrenador_id"] = oid(data.entrenador_id, "entrenador_id")
    doc["sede_id"] = oid(data.sede_id, "sede_id")
    ent = buscar_o_404(entrenadores, doc["entrenador_id"], "Entrenador")
    sede = buscar_o_404(sedes, doc["sede_id"], "Sede")

    if not sede.get("activa", True):
        raise HTTPException(409, "La sede está inactiva")
    if not ent.get("activo", True):
        raise HTTPException(409, "El entrenador está inactivo")
    # Regla: el entrenador debe pertenecer a la sede donde se dicta la clase
    if ent["sede_id"] != doc["sede_id"]:
        raise HTTPException(409, f"{ent['nombre']} no trabaja en la sede {sede['nombre']}")
    # Regla: el entrenador debe tener la especialidad de la clase
    if data.tipo not in ent["especialidades"]:
        raise HTTPException(409, f"{ent['nombre']} no tiene la especialidad '{data.tipo}'")
    # Regla: el entrenador no puede tener dos clases al mismo tiempo
    filtro = {"entrenador_id": doc["entrenador_id"], "dia_semana": data.dia_semana, "activa": True}
    if excluir_id:
        filtro["_id"] = {"$ne": excluir_id}
    for otra in clases.find(filtro):
        if se_cruzan(data.hora_inicio, data.hora_fin, otra["hora_inicio"], otra["hora_fin"]):
            raise HTTPException(
                409, f"{ent['nombre']} ya dicta '{otra['nombre']}' el {data.dia_semana} "
                     f"de {otra['hora_inicio']} a {otra['hora_fin']}"
            )
    return doc


@router.post("", status_code=201)
def crear(data: ClaseIn):
    doc = _validar(data)
    doc["inscritos"] = []
    r = clases.insert_one(doc)
    return obtener(str(r.inserted_id))


@router.put("/{id}")
def actualizar(id: str, data: ClaseIn):
    _id = oid(id)
    actual = buscar_o_404(clases, _id, "Clase")
    doc = _validar(data, excluir_id=_id)
    if data.cupo_maximo < len(actual["inscritos"]):
        raise HTTPException(409, f"La clase ya tiene {len(actual['inscritos'])} inscritos; el cupo no puede ser menor")
    clases.update_one({"_id": _id}, {"$set": doc})  # no toca 'inscritos'
    return obtener(id)


@router.delete("/{id}")
def eliminar(id: str):
    _id = oid(id)
    c = buscar_o_404(clases, _id, "Clase")
    if c["inscritos"]:
        raise HTTPException(409, f"La clase tiene {len(c['inscritos'])} socios inscritos. Retírelos o desactívela.")
    clases.delete_one({"_id": _id})
    return {"mensaje": "Clase eliminada"}


# --------------------------- Inscripciones ---------------------------
@router.post("/{id}/inscripciones", status_code=201)
def inscribir(id: str, data: InscripcionIn):
    _id = oid(id)
    socio_id = oid(data.socio_id, "socio_id")
    clase = buscar_o_404(clases, _id, "Clase")
    socio = buscar_o_404(socios, socio_id, "Socio")

    if not clase.get("activa", True):
        raise HTTPException(409, "La clase no está activa")
    if any(i["socio_id"] == socio_id for i in clase["inscritos"]):
        raise HTTPException(409, "El socio ya está inscrito en esta clase")

    # Regla: membresía vigente cuyo plan incluya clases grupales
    m = membresia_vigente(socio_id)
    if not m:
        raise HTTPException(409, "El socio no tiene una membresía vigente")
    if not m["plan_snapshot"]["incluye_clases"]:
        raise HTTPException(409, f"El plan {m['plan_snapshot']['nombre']} no incluye clases grupales")
    # Regla: si el plan no da acceso a todas las sedes, solo puede inscribirse en su sede
    if not m["plan_snapshot"]["acceso_todas_sedes"] and clase["sede_id"] != socio["sede_id"]:
        raise HTTPException(409, "El plan del socio solo permite clases en su sede principal")
    # Regla: no puede inscribirse en dos clases que se cruzan
    for otra in clases.find({"inscritos.socio_id": socio_id, "dia_semana": clase["dia_semana"]}):
        if se_cruzan(clase["hora_inicio"], clase["hora_fin"], otra["hora_inicio"], otra["hora_fin"]):
            raise HTTPException(409, f"Se cruza con '{otra['nombre']}' ({otra['hora_inicio']}-{otra['hora_fin']})")

    # Regla: cupo máximo. La condición va DENTRO del update para que sea atómica:
    # si dos personas toman el último cupo a la vez, solo una lo consigue.
    r = clases.update_one(
        {"_id": _id, "$expr": {"$lt": [{"$size": "$inscritos"}, "$cupo_maximo"]}, "inscritos.socio_id": {"$ne": socio_id}},
        {"$push": {"inscritos": {"socio_id": socio_id, "fecha_inscripcion": ahora()}}},
    )
    if r.modified_count == 0:
        raise HTTPException(409, "La clase no tiene cupos disponibles")
    return obtener(id)


@router.delete("/{id}/inscripciones/{socio_id}")
def retirar(id: str, socio_id: str):
    r = clases.update_one({"_id": oid(id)}, {"$pull": {"inscritos": {"socio_id": oid(socio_id, "socio_id")}}})
    if r.modified_count == 0:
        raise HTTPException(404, "El socio no estaba inscrito en esta clase")
    return obtener(id)
