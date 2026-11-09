"""
Prime Gym — API del sistema de gestión de gimnasio.

Arquitectura:
    Navegador (HTML/JS)  →  FastAPI (esta app, /api/...)  →  MongoDB Atlas

FastAPI expone la API REST bajo /api y además sirve los archivos del frontend,
así toda la solución se despliega como un único servicio web.
Documentación interactiva de la API: /docs
"""
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from database import client, crear_indices
from routers import asistencias, clases, entrenadores, membresias, planes, reportes, sedes, socios

@asynccontextmanager
async def lifespan(app: FastAPI):
    crear_indices()  # al arrancar, se asegura de que existan los índices
    yield


app = FastAPI(title="Prime Gym API", version="1.0", lifespan=lifespan,
              description="Gestión de sedes, socios, membresías y clases")

for r in (sedes, planes, entrenadores, socios, membresias, clases, asistencias, reportes):
    app.include_router(r.router)


# Traducimos los errores de validación de Pydantic a mensajes legibles en español
CAMPOS = {
    "fecha_nacimiento": "Fecha de nacimiento", "telefono": "Teléfono", "documento": "Documento",
    "email": "Correo", "hora_inicio": "Hora de inicio", "hora_fin": "Hora de fin", "precio": "Precio",
}


TRADUCCIONES = [
    (r"String should match pattern .*", "formato no válido"),
    (r"String should have at least (\d+) characters?", r"debe tener al menos \1 caracteres"),
    (r"String should have at most (\d+) characters?", r"debe tener máximo \1 caracteres"),
    (r"Input should be greater than or equal to (.+)", r"debe ser mayor o igual a \1"),
    (r"Input should be less than or equal to (.+)", r"debe ser menor o igual a \1"),
    (r"Input should be greater than (.+)", r"debe ser mayor que \1"),
    (r"Field required", "es obligatorio"),
    (r"value is not a valid email address.*", "correo no válido"),
    (r"List should have at least 1 item.*", "seleccione al menos una opción"),
    (r"Input should be a valid (integer|number).*", "debe ser un número"),
    (r"Input should be a valid date.*", "fecha no válida"),
    (r"Input should be (.+)", r"debe ser \1"),
]


def traducir(msg: str) -> str:
    for patron, reemplazo in TRADUCCIONES:
        if re.match(patron, msg):
            return re.sub(patron, reemplazo, msg)
    return msg


@app.exception_handler(RequestValidationError)
async def error_validacion(request: Request, exc: RequestValidationError):
    mensajes = []
    for e in exc.errors():
        campo = ".".join(str(x) for x in e["loc"] if x != "body")
        nombre = CAMPOS.get(campo.split(".")[-1], campo)
        msg = traducir(e["msg"].replace("Value error, ", ""))
        mensajes.append(f"{nombre}: {msg}" if nombre else msg)
    return JSONResponse(status_code=422, content={"detail": " | ".join(mensajes)})


@app.get("/api/salud", tags=["Sistema"])
def salud():
    """Verifica que la API esté arriba y que haya conexión con Atlas."""
    client.admin.command("ping")
    return {"estado": "ok", "base_de_datos": "conectada"}


# ----------------------- Frontend estático -----------------------
FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(FRONTEND / "index.html")
