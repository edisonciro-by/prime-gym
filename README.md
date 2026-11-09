# Prime Gym — Sistema de gestión de gimnasio

Proyecto final · **Bases de Datos II** · Universidad Católica Luis Amigó
Profesor: Juan Carlos Gómez
Integrantes: Edison Stiven Ciro López · Juan Pablo Cardona

Aplicación web para administrar una cadena de gimnasios con varias sedes: socios, planes,
membresías con pagos, clases grupales con cupos, entrenadores, control de acceso en recepción
y un módulo de reportes analíticos. La base de datos está alojada en **MongoDB Atlas**.

```
Navegador (HTML + JS)  ──HTTP/JSON──▶  API FastAPI (Python)  ──pymongo──▶  MongoDB Atlas
        frontend/                           backend/                         (nube)
```

## Estructura

```
prime-gym/
├── backend/
│   ├── main.py            # App FastAPI: registra routers y sirve el frontend
│   ├── database.py        # Conexión a Atlas (lee MONGO_URI del entorno) e índices
│   ├── schemas.py         # Validaciones de entrada (Pydantic)
│   ├── services.py        # Lógica compartida (estado de membresías)
│   ├── utils.py           # Utilidades (ObjectId, fechas, cruces de horario)
│   └── routers/           # Un archivo por entidad + reportes.py (Aggregation Pipeline)
├── frontend/              # index.html, styles.css, app.js
├── scripts/
│   ├── seed.py            # Carga ~12.800 documentos de prueba coherentes
│   └── verificar.py       # Conteos e integridad (evidencia)
├── requirements.txt
├── render.yaml            # Despliegue en Render
└── .env.example           # Plantilla de variables (el .env real NO se sube)
```

## Ejecutar en local

```bash
python -m venv venv
venv\Scripts\activate            # Windows   (Mac/Linux: source venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env           # y pegar la cadena de conexión de Atlas en MONGO_URI
python scripts/seed.py           # carga los datos de prueba
cd backend
uvicorn main:app --reload
```

Abrir <http://localhost:8000> (aplicación) y <http://localhost:8000/docs> (documentación interactiva de la API).

## Colecciones

| Colección | Qué guarda | Embebido | Referencias |
|---|---|---|---|
| `sedes` | Sedes del gimnasio | — | — |
| `planes` | Planes de membresía | — | — |
| `entrenadores` | Entrenadores | `especialidades` (array) | `sede_id` |
| `socios` | Socios | `contacto_emergencia`, `evaluaciones[]` | `sede_id` |
| `membresias` | Planes vendidos | `pagos[]`, `plan_snapshot` | `socio_id`, `plan_id` |
| `clases` | Clases grupales | `inscritos[]` (cada uno con `socio_id`) | `entrenador_id`, `sede_id` |
| `asistencias` | Ingresos al gimnasio | — | `socio_id`, `sede_id` |

## Endpoints principales

| Método | Ruta | Descripción |
|---|---|---|
| GET/POST/PUT/DELETE | `/api/sedes`, `/api/planes`, `/api/entrenadores`, `/api/socios`, `/api/clases` | CRUD con búsqueda y filtros |
| POST/DELETE | `/api/socios/{id}/evaluaciones` | Evaluaciones físicas (array embebido) |
| POST | `/api/membresias` · `/api/membresias/{id}/pagos` · PUT `/api/membresias/{id}/cancelar` | Venta, abonos y cancelación |
| POST/DELETE | `/api/clases/{id}/inscripciones` | Inscribir / retirar socios |
| POST | `/api/asistencias` | Registrar ingreso en recepción |
| GET | `/api/reportes/...` | `resumen`, `ingresos-mensuales`, `planes-populares`, `ocupacion-clases`, `por-vencer`, `cartera`, `horas-pico`, `ranking-entrenadores`, `sedes` |

## Despliegue

1. Base de datos en MongoDB Atlas (cluster gratuito M0), con acceso de red `0.0.0.0/0`.
2. Servicio web en Render conectado a este repositorio (usa `render.yaml`).
3. Variable de entorno `MONGO_URI` configurada en el panel de Render (no en el código).
