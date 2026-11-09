"""
Carga datos de prueba realistas en MongoDB Atlas.

Uso (desde la carpeta raíz del proyecto):
    python scripts/seed.py            -> borra y vuelve a crear todos los datos
Requiere el archivo .env con MONGO_URI.

Los datos respetan las mismas reglas de negocio de la API: membresías de un
socio que no se cruzan, inscritos sin superar el cupo, entrenadores con la
especialidad de su clase, asistencias solo con membresía vigente, etc.
"""
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

from bson import ObjectId
from faker import Faker

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from database import (asistencias, clases, crear_indices, entrenadores, membresias,  # noqa: E402
                      planes, sedes, socios)
from utils import DIAS_SEMANA, ahora, hoy, se_cruzan  # noqa: E402

random.seed(42)
Faker.seed(42)
fake = Faker("es_CO")
HOY = hoy()
AHORA = ahora()

N_SOCIOS = 320
METODOS = ["efectivo", "tarjeta", "transferencia", "nequi"]


def limpiar():
    for c in (asistencias, clases, membresias, socios, entrenadores, planes, sedes):
        c.drop()
    crear_indices()


def crear_sedes():
    datos = [
        ("Prime Laureles", "Medellín", "Cra 70 # 44-21", "6044441010", 160),
        ("Prime Niquía", "Bello", "Cl 57 # 52-30", "6044442020", 120),
        ("Prime Envigado", "Envigado", "Cra 43A # 38 Sur-15", "6044443030", 110),
    ]
    docs = [{"_id": ObjectId(), "nombre": n, "ciudad": c, "direccion": d, "telefono": t,
             "capacidad_maxima": cap, "activa": True} for n, c, d, t, cap in datos]
    sedes.insert_many(docs)
    return docs


def crear_planes():
    datos = [
        ("Básico Mensual", "Acceso a máquinas en la sede principal", 89000, 30, False, False),
        ("Plus Mensual", "Máquinas + clases grupales en la sede principal", 129000, 30, True, False),
        ("Total Mensual", "Todo incluido en todas las sedes", 159000, 30, True, True),
        ("Trimestral Plus", "Máquinas + clases, 3 meses", 349000, 90, True, False),
        ("Semestral Total", "Todo incluido en todas las sedes, 6 meses", 799000, 180, True, True),
        ("Anual Básico", "Acceso a máquinas durante un año", 890000, 365, False, False),
        ("Pase Estudiante", "Plan mensual con descuento (solo máquinas)", 69000, 30, False, False),
    ]
    docs = [{"_id": ObjectId(), "nombre": n, "descripcion": d, "precio": p, "duracion_dias": dur,
             "incluye_clases": ic, "acceso_todas_sedes": at, "activo": True}
            for n, d, p, dur, ic, at in datos]
    # Un plan antiguo inactivo para demostrar el filtro y la regla de borrado
    docs.append({"_id": ObjectId(), "nombre": "Promo Enero 2025", "descripcion": "Promoción descontinuada",
                 "precio": 59000, "duracion_dias": 30, "incluye_clases": True, "acceso_todas_sedes": False,
                 "activo": False})
    planes.insert_many(docs)
    return docs


TIPOS = ["yoga", "spinning", "crossfit", "funcional", "pilates", "zumba", "boxeo"]


def crear_entrenadores(lista_sedes):
    docs = []
    for sede in lista_sedes:
        for _ in range(5):
            docs.append({
                "_id": ObjectId(),
                "documento": str(fake.unique.random_int(10_000_000, 1_299_999_999)),
                "nombre": fake.name(),
                "especialidades": random.sample(TIPOS, k=random.randint(2, 3)),
                "telefono": "3" + str(random.randint(100000000, 259999999)),
                "email": fake.unique.email(),
                "sede_id": sede["_id"],
                "activo": True,
                "fecha_ingreso": HOY - timedelta(days=random.randint(60, 1500)),
            })
    entrenadores.insert_many(docs)
    return docs


def crear_socios(lista_sedes):
    docs = []
    pesos = [0.45, 0.30, 0.25]
    for _ in range(N_SOCIOS):
        sede = random.choices(lista_sedes, weights=pesos)[0]
        genero = random.choice(["M", "F"])
        nombre = fake.first_name_male() if genero == "M" else fake.first_name_female()
        edad = random.randint(16, 65)
        nac = HOY - timedelta(days=edad * 365 + random.randint(0, 364))
        registro = HOY - timedelta(days=random.randint(10, 480))
        evals = []
        estatura = random.randint(150, 192)
        peso = round(random.uniform(52, 105), 1)
        for k in range(random.randint(0, 4)):
            f = registro + timedelta(days=45 * k)
            if f > HOY:
                break
            peso = round(peso + random.uniform(-2.5, 1.5), 1)
            evals.append({"_id": ObjectId(), "fecha": f, "peso_kg": peso, "estatura_cm": estatura,
                          "imc": round(peso / (estatura / 100) ** 2, 1),
                          "porcentaje_grasa": round(random.uniform(12, 35), 1), "observaciones": ""})
        docs.append({
            "_id": ObjectId(),
            "documento": str(fake.unique.random_int(1_000_000, 1_299_999_999)),
            "nombre": nombre,
            "apellido": f"{fake.last_name()} {fake.last_name()}",
            "fecha_nacimiento": datetime(nac.year, nac.month, nac.day),
            "genero": genero,
            "email": fake.unique.email().lower(),
            "telefono": "3" + str(random.randint(100000000, 259999999)),
            "sede_id": sede["_id"],
            "fecha_registro": registro,
            "contacto_emergencia": {
                "nombre": fake.name(),
                "telefono": "3" + str(random.randint(100000000, 259999999)),
                "parentesco": random.choice(["Madre", "Padre", "Pareja", "Hermano(a)", "Amigo(a)"]),
            },
            "evaluaciones": evals,
        })
    socios.insert_many(docs)
    return docs


def snapshot(p):
    return {"nombre": p["nombre"], "duracion_dias": p["duracion_dias"],
            "incluye_clases": p["incluye_clases"], "acceso_todas_sedes": p["acceso_todas_sedes"]}


def crear_membresias(lista_socios, lista_planes):
    activos = [p for p in lista_planes if p["activo"]]
    pesos = [30, 25, 12, 10, 5, 4, 14]
    docs = []
    for s in lista_socios:
        fecha = s["fecha_registro"]
        # 80 % de los socios renuevan con frecuencia; el resto abandona antes
        fiel = random.random() < 0.8
        while fecha <= HOY:
            plan = random.choices(activos, weights=pesos)[0]
            fin = fecha + timedelta(days=plan["duracion_dias"] - 1)
            precio = plan["precio"]
            if fin < HOY:
                estado = "cancelada" if random.random() < 0.04 else "vencida"
            else:
                estado = "activa"
            # Pagos: la mayoría paga completo; algunos activos pagan en cuotas
            pagos = []
            if estado == "activa" and random.random() < 0.3:
                abono = int(precio * random.choice([0.3, 0.5, 0.6]) // 1000 * 1000)
                pagos.append({"_id": ObjectId(), "fecha": fecha + timedelta(hours=random.randint(6, 20)),
                              "valor": abono, "metodo": random.choice(METODOS)})
            elif estado != "cancelada" or random.random() < 0.5:
                pagos.append({"_id": ObjectId(), "fecha": fecha + timedelta(hours=random.randint(6, 20)),
                              "valor": precio, "metodo": random.choices(METODOS, weights=[25, 30, 20, 25])[0]})
            pagado = sum(p["valor"] for p in pagos)
            docs.append({
                "_id": ObjectId(), "socio_id": s["_id"], "plan_id": plan["_id"], "plan_snapshot": snapshot(plan),
                "fecha_inicio": fecha, "fecha_fin": fin, "precio_total": precio, "pagos": pagos,
                "saldo_pendiente": precio - pagado if estado != "cancelada" else 0,
                "estado": estado, "fecha_creacion": fecha,
            })
            if estado == "activa":
                break
            if not fiel and random.random() < 0.5:
                break
            fecha = fin + timedelta(days=1 + random.choice([0, 0, 0, 3, 10, 25]))
    membresias.insert_many(docs)
    return docs


FRANJAS = [("06:00", "07:00"), ("07:00", "08:00"), ("09:00", "10:00"), ("12:00", "13:00"),
           ("17:00", "18:00"), ("18:00", "19:00"), ("19:00", "20:00")]
NOMBRES = {"yoga": "Yoga Flow", "spinning": "Spinning Power", "crossfit": "CrossFit WOD",
           "funcional": "Entrenamiento Funcional", "pilates": "Pilates Mat", "zumba": "Zumba Fitness",
           "boxeo": "Boxeo Cardio"}


def crear_clases(lista_sedes, lista_entrenadores, lista_socios, lista_membresias):
    docs = []
    for sede in lista_sedes:
        ents = [e for e in lista_entrenadores if e["sede_id"] == sede["_id"]]
        ocupado = set()
        creadas = 0
        while creadas < 12:
            e = random.choice(ents)
            dia = random.choice(DIAS_SEMANA[:6])
            hi, hf = random.choice(FRANJAS)
            if (e["_id"], dia, hi) in ocupado:
                continue
            ocupado.add((e["_id"], dia, hi))
            tipo = random.choice(e["especialidades"])
            docs.append({"_id": ObjectId(), "nombre": NOMBRES[tipo], "tipo": tipo, "entrenador_id": e["_id"],
                         "sede_id": sede["_id"], "dia_semana": dia, "hora_inicio": hi, "hora_fin": hf,
                         "cupo_maximo": random.choice([12, 15, 20, 25]), "inscritos": [], "activa": True})
            creadas += 1

    # Inscribir socios con membresía activa que incluya clases
    sede_de = {s["_id"]: s["sede_id"] for s in lista_socios}
    elegibles = [m for m in lista_membresias if m["estado"] == "activa" and m["fecha_inicio"] <= HOY
                 and m["plan_snapshot"]["incluye_clases"]]
    agenda = {}
    for m in elegibles:
        sid = m["socio_id"]
        posibles = [c for c in docs if m["plan_snapshot"]["acceso_todas_sedes"] or c["sede_id"] == sede_de[sid]]
        # La demanda no es uniforme: spinning y crossfit son más populares
        random.shuffle(posibles)
        posibles.sort(key=lambda c: c["tipo"] not in ("spinning", "crossfit", "funcional"))
        for c in posibles[: random.randint(1, 3)]:
            if len(c["inscritos"]) >= c["cupo_maximo"]:
                continue
            ag = agenda.setdefault(sid, [])
            if any(d == c["dia_semana"] and se_cruzan(c["hora_inicio"], c["hora_fin"], i, f) for d, i, f in ag):
                continue
            ag.append((c["dia_semana"], c["hora_inicio"], c["hora_fin"]))
            c["inscritos"].append({"socio_id": sid, "fecha_inscripcion": m["fecha_inicio"] + timedelta(hours=10)})
    clases.insert_many(docs)
    return docs


HORAS = list(range(5, 22))
PESO_HORA = [3, 9, 10, 6, 3, 2, 3, 4, 3, 2, 3, 6, 10, 11, 8, 4, 2]


def crear_asistencias(lista_socios, lista_membresias):
    sede_de = {s["_id"]: s["sede_id"] for s in lista_socios}
    otras = list({s["sede_id"] for s in lista_socios})
    docs = []
    desde = HOY - timedelta(days=120)
    for m in lista_membresias:
        if m["estado"] == "cancelada":
            continue
        ini = max(m["fecha_inicio"], desde)
        fin = min(m["fecha_fin"], HOY)
        d = ini
        frecuencia = random.choice([0.25, 0.4, 0.55, 0.7])
        while d <= fin:
            if d.weekday() != 6 and random.random() < frecuencia:
                h = random.choices(HORAS, weights=PESO_HORA)[0]
                fh = d + timedelta(hours=h, minutes=random.randint(0, 59))
                if fh <= AHORA:
                    sede = sede_de[m["socio_id"]]
                    if m["plan_snapshot"]["acceso_todas_sedes"] and random.random() < 0.25:
                        sede = random.choice(otras)
                    docs.append({"socio_id": m["socio_id"], "sede_id": sede, "fecha_hora": fh})
            d += timedelta(days=1)
    asistencias.insert_many(docs)
    return docs


def main():
    print("Limpiando base de datos...")
    limpiar()
    s = crear_sedes()
    p = crear_planes()
    e = crear_entrenadores(s)
    so = crear_socios(s)
    m = crear_membresias(so, p)
    c = crear_clases(s, e, so, m)
    a = crear_asistencias(so, m)
    total = len(s) + len(p) + len(e) + len(so) + len(m) + len(c) + len(a)
    print(f"sedes={len(s)} planes={len(p)} entrenadores={len(e)} socios={len(so)} "
          f"membresias={len(m)} clases={len(c)} asistencias={len(a)}  TOTAL={total}")
    print("Datos de prueba cargados correctamente.")


if __name__ == "__main__":
    main()
