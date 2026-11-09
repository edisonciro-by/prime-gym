"""
Registro de ingresos al gimnasio (control de acceso en la recepción).
Es una colección separada y REFERENCIADA porque crece sin límite: un socio
puede acumular cientos de ingresos y embeberlos haría crecer su documento
indefinidamente (MongoDB limita cada documento a 16 MB).
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException

from database import asistencias, sedes, socios
from schemas import AsistenciaIn
from services import membresia_vigente
from utils import pesos, ahora, buscar_o_404, oid, serializar

router = APIRouter(prefix="/api/asistencias", tags=["Asistencias"])


@router.get("")
def listar(sede_id: str = "", fecha: str = "", limite: int = 100):
    filtro = {}
    if sede_id:
        filtro["sede_id"] = oid(sede_id, "sede_id")
    if fecha:  # yyyy-mm-dd
        d = datetime.strptime(fecha, "%Y-%m-%d")
        filtro["fecha_hora"] = {"$gte": d, "$lt": d + timedelta(days=1)}
    pipeline = [
        {"$match": filtro},
        {"$sort": {"fecha_hora": -1}},
        {"$limit": limite},
        {"$lookup": {"from": "socios", "localField": "socio_id", "foreignField": "_id", "as": "s"}},
        {"$lookup": {"from": "sedes", "localField": "sede_id", "foreignField": "_id", "as": "sd"}},
        {
            "$project": {
                "fecha_hora": 1, "socio_id": 1, "sede_id": 1,
                "socio_nombre": {"$concat": [{"$arrayElemAt": ["$s.nombre", 0]}, " ", {"$arrayElemAt": ["$s.apellido", 0]}]},
                "socio_documento": {"$arrayElemAt": ["$s.documento", 0]},
                "sede_nombre": {"$arrayElemAt": ["$sd.nombre", 0]},
            }
        },
    ]
    return serializar(list(asistencias.aggregate(pipeline)))


@router.post("", status_code=201)
def registrar(data: AsistenciaIn):
    socio_id = oid(data.socio_id, "socio_id")
    sede_id = oid(data.sede_id, "sede_id")
    socio = buscar_o_404(socios, socio_id, "Socio")
    sede = buscar_o_404(sedes, sede_id, "Sede")

    # Regla: solo ingresan socios con membresía vigente
    m = membresia_vigente(socio_id)
    if not m:
        raise HTTPException(403, f"Acceso denegado: {socio['nombre']} no tiene membresía vigente")
    # Regla: el plan define si puede usar cualquier sede o solo la suya
    if not m["plan_snapshot"]["acceso_todas_sedes"] and socio["sede_id"] != sede_id:
        raise HTTPException(403, f"Acceso denegado: su plan solo permite ingresar a su sede principal")
    # Regla: evitar doble registro (máximo un ingreso cada 2 horas)
    if asistencias.find_one({"socio_id": socio_id, "fecha_hora": {"$gte": ahora() - timedelta(hours=2)}}):
        raise HTTPException(409, "El socio ya registró un ingreso en las últimas 2 horas")
    # Advertencia (no bloquea): saldo pendiente
    aviso = f"Tiene un saldo pendiente de ${pesos(m['saldo_pendiente'])}" if m["saldo_pendiente"] > 0 else None

    doc = {"socio_id": socio_id, "sede_id": sede_id, "fecha_hora": ahora()}
    asistencias.insert_one(doc)
    return {
        "mensaje": f"Bienvenido(a) {socio['nombre']} a {sede['nombre']}",
        "vence": m["fecha_fin"].strftime("%Y-%m-%d"),
        "aviso": aviso,
    }
