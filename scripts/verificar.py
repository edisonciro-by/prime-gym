"""
Verificación de la base de datos en Atlas (evidencia para la documentación).

Uso:  python scripts/verificar.py

Muestra cuántos documentos hay por colección y comprueba la integridad:
referencias huérfanas, cupos excedidos, saldos inconsistentes y membresías
activas que se cruzan.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from database import (DB_NAME, asistencias, clases, db, entrenadores,  # noqa: E402
                      membresias, planes, sedes, socios)


def huerfanos(coleccion, campo, destino):
    """Cuenta documentos cuyo 'campo' apunta a un _id que no existe en 'destino'."""
    r = list(coleccion.aggregate([
        {"$lookup": {"from": destino, "localField": campo, "foreignField": "_id", "as": "x"}},
        {"$match": {"x": {"$size": 0}}},
        {"$count": "n"},
    ]))
    return r[0]["n"] if r else 0


def main():
    print(f"Base de datos: {DB_NAME}\n")
    print("== Documentos por colección ==")
    total = 0
    for nombre in ("sedes", "planes", "entrenadores", "socios", "membresias", "clases", "asistencias"):
        n = db[nombre].count_documents({})
        total += n
        print(f"  {nombre:<14}{n:>7}")
    print(f"  {'TOTAL':<14}{total:>7}\n")

    print("== Datos embebidos ==")
    pagos = list(membresias.aggregate([{"$project": {"n": {"$size": "$pagos"}}}, {"$group": {"_id": None, "t": {"$sum": "$n"}}}]))
    evals = list(socios.aggregate([{"$project": {"n": {"$size": "$evaluaciones"}}}, {"$group": {"_id": None, "t": {"$sum": "$n"}}}]))
    ins = list(clases.aggregate([{"$project": {"n": {"$size": "$inscritos"}}}, {"$group": {"_id": None, "t": {"$sum": "$n"}}}]))
    print(f"  pagos embebidos en membresías:     {pagos[0]['t'] if pagos else 0}")
    print(f"  evaluaciones embebidas en socios:  {evals[0]['t'] if evals else 0}")
    print(f"  inscritos embebidos en clases:     {ins[0]['t'] if ins else 0}\n")

    print("== Integridad de referencias (debe ser 0) ==")
    checks = {
        "socios -> sedes": huerfanos(socios, "sede_id", "sedes"),
        "entrenadores -> sedes": huerfanos(entrenadores, "sede_id", "sedes"),
        "membresias -> socios": huerfanos(membresias, "socio_id", "socios"),
        "membresias -> planes": huerfanos(membresias, "plan_id", "planes"),
        "clases -> entrenadores": huerfanos(clases, "entrenador_id", "entrenadores"),
        "clases -> sedes": huerfanos(clases, "sede_id", "sedes"),
        "asistencias -> socios": huerfanos(asistencias, "socio_id", "socios"),
    }
    for k, v in checks.items():
        print(f"  {'OK ' if v == 0 else 'ERR'} {k:<26}{v}")

    print("\n== Reglas de negocio (debe ser 0) ==")
    cupo = clases.count_documents({"$expr": {"$gt": [{"$size": "$inscritos"}, "$cupo_maximo"]}})
    saldo = membresias.count_documents({"$expr": {"$and": [
        {"$ne": ["$estado", "cancelada"]},
        {"$ne": ["$saldo_pendiente", {"$subtract": ["$precio_total", {"$sum": "$pagos.valor"}]}]}]}})
    dobles = list(membresias.aggregate([
        {"$match": {"estado": "activa"}}, {"$group": {"_id": "$socio_id", "n": {"$sum": 1}}},
        {"$match": {"n": {"$gt": 1}}}, {"$count": "n"}]))
    print(f"  {'OK ' if cupo == 0 else 'ERR'} clases con más inscritos que cupo      {cupo}")
    print(f"  {'OK ' if saldo == 0 else 'ERR'} saldos que no cuadran con los pagos   {saldo}")
    dobles = dobles[0]["n"] if dobles else 0
    print(f"  {'OK ' if dobles == 0 else 'ERR'} socios con 2+ membresías activas      {dobles}")
    print(f"\nPlanes activos: {planes.count_documents({'activo': True})} · Sedes: {sedes.count_documents({})}")


if __name__ == "__main__":
    main()
