"""
Componente analítico: consultas con Aggregation Pipeline que responden
preguntas reales de la administración del gimnasio.
Cada función documenta: PREGUNTA, DECISIÓN que apoya y ETAPAS del pipeline.
"""
from datetime import datetime, timedelta

from fastapi import APIRouter

from database import asistencias, clases, entrenadores, membresias, socios
from services import actualizar_estados_membresias
from utils import hoy, oid, serializar

router = APIRouter(prefix="/api/reportes", tags=["Reportes"])

MESES = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
DIAS = ["", "Domingo", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]  # $dayOfWeek: 1=domingo


@router.get("/resumen")
def resumen():
    """Indicadores (KPI) principales del tablero."""
    actualizar_estados_membresias()
    h = hoy()
    inicio_mes = datetime(h.year, h.month, 1)

    ingresos_mes = list(membresias.aggregate([
        {"$unwind": "$pagos"},
        {"$match": {"pagos.fecha": {"$gte": inicio_mes}}},
        {"$group": {"_id": None, "total": {"$sum": "$pagos.valor"}}},
    ]))
    cartera = list(membresias.aggregate([
        {"$match": {"estado": "activa", "saldo_pendiente": {"$gt": 0}}},
        {"$group": {"_id": None, "total": {"$sum": "$saldo_pendiente"}, "n": {"$sum": 1}}},
    ]))
    ocupacion = list(clases.aggregate([
        {"$match": {"activa": True}},
        {"$group": {"_id": None, "inscritos": {"$sum": {"$size": "$inscritos"}}, "cupos": {"$sum": "$cupo_maximo"}}},
    ]))
    total_socios = socios.count_documents({})
    activas = membresias.count_documents({"estado": "activa"})
    return {
        "total_socios": total_socios,
        "membresias_activas": activas,
        "tasa_retencion": round(activas / total_socios * 100, 1) if total_socios else 0,
        "ingresos_mes": ingresos_mes[0]["total"] if ingresos_mes else 0,
        "cartera_pendiente": cartera[0]["total"] if cartera else 0,
        "membresias_con_saldo": cartera[0]["n"] if cartera else 0,
        "ocupacion_clases": round(ocupacion[0]["inscritos"] / ocupacion[0]["cupos"] * 100, 1) if ocupacion and ocupacion[0]["cupos"] else 0,
        "asistencias_hoy": asistencias.count_documents({"fecha_hora": {"$gte": h}}),
        "entrenadores_activos": entrenadores.count_documents({"activo": True}),
    }


@router.get("/ingresos-mensuales")
def ingresos_mensuales(meses: int = 12):
    """
    PREGUNTA: ¿Cuánto dinero entra cada mes y por qué medio de pago?
    DECISIÓN: detectar temporadas bajas para lanzar promociones; planear flujo de caja.
    PIPELINE: $unwind (abre el array de pagos) → $match (últimos N meses)
              → $group (año, mes) → $sort.
    """
    desde = hoy().replace(day=1) - timedelta(days=31 * (meses - 1))
    desde = desde.replace(day=1)
    r = list(membresias.aggregate([
        {"$unwind": "$pagos"},
        {"$match": {"pagos.fecha": {"$gte": desde}}},
        {"$group": {
            "_id": {"anio": {"$year": "$pagos.fecha"}, "mes": {"$month": "$pagos.fecha"}},
            "total": {"$sum": "$pagos.valor"},
            "num_pagos": {"$sum": 1},
            "efectivo": {"$sum": {"$cond": [{"$eq": ["$pagos.metodo", "efectivo"]}, "$pagos.valor", 0]}},
            "tarjeta": {"$sum": {"$cond": [{"$eq": ["$pagos.metodo", "tarjeta"]}, "$pagos.valor", 0]}},
            "transferencia": {"$sum": {"$cond": [{"$eq": ["$pagos.metodo", "transferencia"]}, "$pagos.valor", 0]}},
            "nequi": {"$sum": {"$cond": [{"$eq": ["$pagos.metodo", "nequi"]}, "$pagos.valor", 0]}},
        }},
        {"$sort": {"_id.anio": 1, "_id.mes": 1}},
    ]))
    for x in r:
        x["periodo"] = f"{MESES[x['_id']['mes']]} {x['_id']['anio']}"
    return serializar(r)


@router.get("/planes-populares")
def planes_populares():
    """
    PREGUNTA: ¿Qué planes se venden más y cuáles generan más ingresos?
    DECISIÓN: ajustar precios, retirar planes poco vendidos, enfocar publicidad.
    PIPELINE: $group por plan_id → $lookup a planes (precio y estado actuales)
              → $unwind → $project (ticket promedio) → $sort.
    """
    return serializar(list(membresias.aggregate([
        {"$match": {"estado": {"$ne": "cancelada"}}},
        {"$group": {
            "_id": "$plan_id",
            "vendidas": {"$sum": 1},
            "activas": {"$sum": {"$cond": [{"$eq": ["$estado", "activa"]}, 1, 0]}},
            "facturado": {"$sum": "$precio_total"},
            "recaudado": {"$sum": {"$subtract": ["$precio_total", "$saldo_pendiente"]}},
        }},
        {"$lookup": {"from": "planes", "localField": "_id", "foreignField": "_id", "as": "plan"}},
        {"$unwind": "$plan"},
        {"$project": {
            "_id": 0, "plan": "$plan.nombre", "precio_actual": "$plan.precio",
            "vendidas": 1, "activas": 1, "facturado": 1, "recaudado": 1,
        }},
        {"$sort": {"vendidas": -1}},
    ])))


@router.get("/ocupacion-clases")
def ocupacion_clases(limite: int = 15):
    """
    PREGUNTA: ¿Qué clases están llenas y cuáles casi vacías?
    DECISIÓN: abrir nuevos horarios de las más demandadas; cerrar o mover las vacías.
    PIPELINE: $match → $project ($size, $divide para % ocupación)
              → $lookup entrenadores → $lookup sedes (múltiples $lookup) → $sort → $limit.
    """
    return serializar(list(clases.aggregate([
        {"$match": {"activa": True}},
        {"$project": {
            "nombre": 1, "tipo": 1, "dia_semana": 1, "hora_inicio": 1, "cupo_maximo": 1,
            "entrenador_id": 1, "sede_id": 1,
            "inscritos": {"$size": "$inscritos"},
            "ocupacion": {"$round": [{"$multiply": [{"$divide": [{"$size": "$inscritos"}, "$cupo_maximo"]}, 100]}, 1]},
        }},
        {"$lookup": {"from": "entrenadores", "localField": "entrenador_id", "foreignField": "_id", "as": "e"}},
        {"$lookup": {"from": "sedes", "localField": "sede_id", "foreignField": "_id", "as": "s"}},
        {"$project": {
            "_id": 0, "nombre": 1, "tipo": 1, "dia_semana": 1, "hora_inicio": 1, "cupo_maximo": 1,
            "inscritos": 1, "ocupacion": 1,
            "entrenador": {"$arrayElemAt": ["$e.nombre", 0]},
            "sede": {"$arrayElemAt": ["$s.nombre", 0]},
        }},
        {"$sort": {"ocupacion": -1, "inscritos": -1}},
        {"$limit": limite},
    ])))


@router.get("/por-vencer")
def por_vencer(dias: int = 7):
    """
    PREGUNTA: ¿Qué socios se quedan sin membresía en los próximos N días?
    DECISIÓN: llamarlos o escribirles para que renueven (retención de clientes).
    PIPELINE: $match (activa y fecha_fin en rango) → $lookup socios → $unwind
              → $lookup sedes → $project (días restantes con $dateDiff) → $sort.
    """
    actualizar_estados_membresias()
    h = hoy()
    return serializar(list(membresias.aggregate([
        {"$match": {"estado": "activa", "fecha_fin": {"$gte": h, "$lte": h + timedelta(days=dias)}}},
        {"$lookup": {"from": "socios", "localField": "socio_id", "foreignField": "_id", "as": "socio"}},
        {"$unwind": "$socio"},
        {"$lookup": {"from": "sedes", "localField": "socio.sede_id", "foreignField": "_id", "as": "sede"}},
        {"$project": {
            "_id": 0,
            "socio": {"$concat": ["$socio.nombre", " ", "$socio.apellido"]},
            "telefono": "$socio.telefono", "email": "$socio.email",
            "sede": {"$arrayElemAt": ["$sede.nombre", 0]},
            "plan": "$plan_snapshot.nombre", "fecha_fin": 1, "saldo_pendiente": 1,
            "dias_restantes": {"$dateDiff": {"startDate": h, "endDate": "$fecha_fin", "unit": "day"}},
        }},
        {"$sort": {"fecha_fin": 1}},
    ])))


@router.get("/cartera")
def cartera(limite: int = 20):
    """
    PREGUNTA: ¿Quiénes deben dinero y cuánto?
    DECISIÓN: gestión de cobro; decidir si se restringe el acceso a morosos.
    PIPELINE: $match (saldo > 0) → $lookup socios → $unwind → $project → $sort → $limit.
    """
    return serializar(list(membresias.aggregate([
        {"$match": {"saldo_pendiente": {"$gt": 0}, "estado": {"$ne": "cancelada"}}},
        {"$lookup": {"from": "socios", "localField": "socio_id", "foreignField": "_id", "as": "socio"}},
        {"$unwind": "$socio"},
        {"$project": {
            "_id": 0,
            "socio": {"$concat": ["$socio.nombre", " ", "$socio.apellido"]},
            "documento": "$socio.documento", "telefono": "$socio.telefono",
            "plan": "$plan_snapshot.nombre", "estado": 1, "precio_total": 1, "saldo_pendiente": 1,
            "porcentaje_pagado": {"$round": [{"$multiply": [
                {"$divide": [{"$subtract": ["$precio_total", "$saldo_pendiente"]}, "$precio_total"]}, 100]}, 0]},
        }},
        {"$sort": {"saldo_pendiente": -1}},
        {"$limit": limite},
    ])))


@router.get("/horas-pico")
def horas_pico(sede_id: str = ""):
    """
    PREGUNTA: ¿A qué horas y qué días se llena el gimnasio?
    DECISIÓN: asignar más entrenadores/personal en horas pico; programar mantenimiento en horas valle.
    PIPELINE: $match (últimos 90 días) → $group por $hour → $sort.
              Segundo pipeline: $group por $dayOfWeek.
    """
    filtro = {"fecha_hora": {"$gte": hoy() - timedelta(days=90)}}
    if sede_id:
        filtro["sede_id"] = oid(sede_id, "sede_id")
    por_hora = list(asistencias.aggregate([
        {"$match": filtro},
        {"$group": {"_id": {"$hour": "$fecha_hora"}, "ingresos": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]))
    por_dia = list(asistencias.aggregate([
        {"$match": filtro},
        {"$group": {"_id": {"$dayOfWeek": "$fecha_hora"}, "ingresos": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]))
    return {
        "por_hora": [{"hora": f"{x['_id']:02d}:00", "ingresos": x["ingresos"]} for x in por_hora],
        "por_dia": [{"dia": DIAS[x["_id"]], "ingresos": x["ingresos"]} for x in por_dia],
    }


@router.get("/ranking-entrenadores")
def ranking_entrenadores():
    """
    PREGUNTA: ¿Qué entrenadores atraen más socios a sus clases?
    DECISIÓN: reconocimientos/bonificaciones; asignar más clases a los más demandados.
    PIPELINE: $match → $group por entrenador (suma de $size inscritos, cupos)
              → $lookup entrenadores → $unwind → $lookup sedes → $project → $sort.
    """
    return serializar(list(clases.aggregate([
        {"$match": {"activa": True}},
        {"$group": {
            "_id": "$entrenador_id",
            "clases": {"$sum": 1},
            "inscritos": {"$sum": {"$size": "$inscritos"}},
            "cupos": {"$sum": "$cupo_maximo"},
            "tipos": {"$addToSet": "$tipo"},
        }},
        {"$lookup": {"from": "entrenadores", "localField": "_id", "foreignField": "_id", "as": "e"}},
        {"$unwind": "$e"},
        {"$lookup": {"from": "sedes", "localField": "e.sede_id", "foreignField": "_id", "as": "s"}},
        {"$project": {
            "_id": 0, "entrenador": "$e.nombre", "sede": {"$arrayElemAt": ["$s.nombre", 0]},
            "clases": 1, "inscritos": 1, "tipos": 1,
            "ocupacion": {"$round": [{"$multiply": [{"$divide": ["$inscritos", "$cupos"]}, 100]}, 1]},
        }},
        {"$sort": {"inscritos": -1}},
    ])))


@router.get("/sedes")
def desempeno_sedes():
    """
    PREGUNTA: ¿Cómo se comparan las sedes en socios, membresías activas e ingresos?
    DECISIÓN: dónde invertir en equipos, abrir cupos o reforzar ventas.
    PIPELINE: membresias → $lookup socios → $unwind → $group por sede del socio
              (con $unwind de pagos para sumar lo recaudado) → $lookup sedes → $sort.
    """
    actualizar_estados_membresias()
    r = list(membresias.aggregate([
        {"$lookup": {"from": "socios", "localField": "socio_id", "foreignField": "_id", "as": "socio"}},
        {"$unwind": "$socio"},
        {"$group": {
            "_id": "$socio.sede_id",
            "socios_distintos": {"$addToSet": "$socio_id"},
            "activas": {"$sum": {"$cond": [{"$eq": ["$estado", "activa"]}, 1, 0]}},
            "recaudado": {"$sum": {"$sum": "$pagos.valor"}},
        }},
        {"$lookup": {"from": "sedes", "localField": "_id", "foreignField": "_id", "as": "sede"}},
        {"$unwind": "$sede"},
        {"$project": {
            "_id": 0, "sede": "$sede.nombre", "ciudad": "$sede.ciudad",
            "socios_con_historial": {"$size": "$socios_distintos"}, "activas": 1, "recaudado": 1,
        }},
        {"$sort": {"recaudado": -1}},
    ]))
    return serializar(r)
