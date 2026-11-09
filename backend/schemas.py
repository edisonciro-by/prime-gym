"""
Esquemas de entrada (Pydantic). Primera capa de validación: tipos, rangos y
formatos. Las reglas de negocio que dependen de otros datos (cupos, cruces de
horario, membresía vigente, etc.) se validan en cada router.
"""
from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

HORA = r"^([01]\d|2[0-3]):[0-5]\d$"
DiaSemana = Literal["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
TipoClase = Literal["yoga", "spinning", "crossfit", "funcional", "pilates", "zumba", "boxeo"]
MetodoPago = Literal["efectivo", "tarjeta", "transferencia", "nequi"]


def _texto(v: str) -> str:
    v = (v or "").strip()
    if not v:
        raise ValueError("no puede estar vacío")
    return v


# ---------------------------- SEDES ----------------------------
class SedeIn(BaseModel):
    nombre: str = Field(min_length=3, max_length=60)
    ciudad: str = Field(min_length=3, max_length=40)
    direccion: str = Field(min_length=5, max_length=100)
    telefono: str = Field(pattern=r"^\d{7,10}$")
    capacidad_maxima: int = Field(ge=20, le=1000)
    activa: bool = True

    _limpiar = field_validator("nombre", "ciudad", "direccion")(_texto)


# ---------------------------- PLANES ----------------------------
class PlanIn(BaseModel):
    nombre: str = Field(min_length=3, max_length=40)
    descripcion: str = Field(default="", max_length=200)
    precio: int = Field(gt=0, le=5_000_000, description="Precio en pesos colombianos")
    duracion_dias: int = Field(ge=1, le=365)
    incluye_clases: bool = False
    acceso_todas_sedes: bool = False
    activo: bool = True

    _limpiar = field_validator("nombre")(_texto)


# ---------------------------- ENTRENADORES ----------------------------
class EntrenadorIn(BaseModel):
    documento: str = Field(pattern=r"^\d{6,12}$")
    nombre: str = Field(min_length=3, max_length=80)
    especialidades: List[TipoClase] = Field(min_length=1)
    telefono: str = Field(pattern=r"^3\d{9}$", description="Celular colombiano (10 dígitos, inicia en 3)")
    email: EmailStr
    sede_id: str
    activo: bool = True

    _limpiar = field_validator("nombre")(_texto)


# ---------------------------- SOCIOS ----------------------------
class ContactoEmergencia(BaseModel):
    nombre: str = Field(min_length=3, max_length=80)
    telefono: str = Field(pattern=r"^\d{7,10}$")
    parentesco: str = Field(min_length=3, max_length=30)


class SocioIn(BaseModel):
    documento: str = Field(pattern=r"^\d{6,12}$")
    nombre: str = Field(min_length=2, max_length=50)
    apellido: str = Field(min_length=2, max_length=50)
    fecha_nacimiento: date
    genero: Literal["M", "F", "O"]
    email: EmailStr
    telefono: str = Field(pattern=r"^3\d{9}$")
    sede_id: str
    contacto_emergencia: ContactoEmergencia

    _limpiar = field_validator("nombre", "apellido")(_texto)

    @field_validator("fecha_nacimiento")
    @classmethod
    def edad_minima(cls, v: date):
        hoy = date.today()
        edad = hoy.year - v.year - ((hoy.month, hoy.day) < (v.month, v.day))
        if edad < 14:
            raise ValueError("el socio debe tener al menos 14 años")
        if edad > 100:
            raise ValueError("fecha de nacimiento no válida")
        return v


class EvaluacionIn(BaseModel):
    fecha: Optional[date] = None
    peso_kg: float = Field(ge=30, le=300)
    estatura_cm: float = Field(ge=100, le=250)
    porcentaje_grasa: Optional[float] = Field(default=None, ge=3, le=70)
    observaciones: str = Field(default="", max_length=200)


# ---------------------------- MEMBRESÍAS ----------------------------
class PagoIn(BaseModel):
    valor: int = Field(gt=0)
    metodo: MetodoPago


class MembresiaIn(BaseModel):
    socio_id: str
    plan_id: str
    fecha_inicio: date
    pago_inicial: Optional[PagoIn] = None


# ---------------------------- CLASES ----------------------------
class ClaseIn(BaseModel):
    nombre: str = Field(min_length=3, max_length=60)
    tipo: TipoClase
    entrenador_id: str
    sede_id: str
    dia_semana: DiaSemana
    hora_inicio: str = Field(pattern=HORA)
    hora_fin: str = Field(pattern=HORA)
    cupo_maximo: int = Field(ge=1, le=50)
    activa: bool = True

    _limpiar = field_validator("nombre")(_texto)

    @model_validator(mode="after")
    def validar_horario(self):
        if self.hora_fin <= self.hora_inicio:
            raise ValueError("la hora de fin debe ser posterior a la hora de inicio")
        if not ("05:00" <= self.hora_inicio and self.hora_fin <= "22:00"):
            raise ValueError("las clases deben estar entre las 05:00 y las 22:00")
        return self


class InscripcionIn(BaseModel):
    socio_id: str


# ---------------------------- ASISTENCIAS ----------------------------
class AsistenciaIn(BaseModel):
    socio_id: str
    sede_id: str
