"""
Conexión con MongoDB Atlas.

La cadena de conexión NUNCA se escribe en el código: se lee de la variable de
entorno MONGO_URI (archivo .env en local, o "Environment" en Render).
El archivo .env está en .gitignore, así que no se sube al repositorio.
"""
import os

from dotenv import load_dotenv
from pymongo import ASCENDING, MongoClient

load_dotenv()  # carga las variables del archivo .env (solo en local)

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "prime_gym_db")

if not MONGO_URI:
    raise RuntimeError(
        "Falta la variable de entorno MONGO_URI. "
        "Copie .env.example como .env y pegue su cadena de conexión de Atlas."
    )

# Un único cliente para toda la aplicación (pymongo maneja internamente un pool
# de conexiones, por eso no se abre una conexión por cada petición).
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
db = client[DB_NAME]

# Colecciones del sistema
sedes = db["sedes"]
planes = db["planes"]
entrenadores = db["entrenadores"]
socios = db["socios"]
membresias = db["membresias"]
clases = db["clases"]
asistencias = db["asistencias"]


def crear_indices():
    """Índices que aceleran las consultas y garantizan unicidad."""
    socios.create_index([("documento", ASCENDING)], unique=True)
    socios.create_index([("email", ASCENDING)], unique=True)
    socios.create_index([("apellido", ASCENDING), ("nombre", ASCENDING)])
    entrenadores.create_index([("documento", ASCENDING)], unique=True)
    planes.create_index([("nombre", ASCENDING)], unique=True)
    sedes.create_index([("nombre", ASCENDING)], unique=True)
    membresias.create_index([("socio_id", ASCENDING), ("estado", ASCENDING)])
    membresias.create_index([("fecha_fin", ASCENDING)])
    clases.create_index([("sede_id", ASCENDING), ("dia_semana", ASCENDING)])
    clases.create_index([("entrenador_id", ASCENDING)])
    asistencias.create_index([("socio_id", ASCENDING)])
    asistencias.create_index([("fecha_hora", ASCENDING)])
