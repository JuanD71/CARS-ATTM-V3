"""API de Usuarios: persistencia real, registro y autenticación JWT."""
import os
import hmac
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

import jwt
import psycopg2
from fastapi import Depends, FastAPI, HTTPException, status, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator

import consumer
import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.asegurar_esquema_restricciones()
    if os.getenv("ENABLE_LEGACY_ACCOUNT_EVENTS", "false").lower() == "true":
        consumer.iniciar()  # compatibilidad opcional, desactivada por seguridad
    yield
    consumer.detener()


app = FastAPI(title="Microservicio de Usuarios", version="2.0.0", lifespan=lifespan)
SEGURIDAD = HTTPBearer(auto_error=False)
BANCOS = (
    'Bancolombia', 'Banco de Bogotá', 'Davivienda', 'BBVA Colombia',
    'Banco de Occidente', 'Banco Popular', 'Banco AV Villas', 'Banco Caja Social',
    'Banco Agrario', 'Scotiabank Colpatria', 'Banco Falabella', 'Banco Finandina',
)



class UsuarioResponse(BaseModel):
    id: int
    nombre: str
    email: str
    rol: str
    activo: bool


class UsuarioCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int = Field(..., ge=1, le=9999999999, description="Cédula del usuario")
    nombre: str = Field(..., min_length=2, max_length=100)
    email: str = Field(..., max_length=150)
    password: str = Field(..., min_length=8, max_length=72)
    rol: Literal["cliente"] = "cliente"  # impide autoasignarse rol administrador
    banco: str = Field(..., min_length=3, max_length=65)
    numeroCuenta: str = Field(..., pattern=r'^[0-9]{6,20}$')

    @field_validator("password")
    @classmethod
    def validar_password(cls, value: str):
        if len(value.encode("utf-8")) > 72:
            raise ValueError("La contraseña supera el límite de bcrypt (72 bytes)")
        return value

    @field_validator("email")
    @classmethod
    def validar_email(cls, value: str):
        value = value.strip().lower()
        if value.count("@") != 1 or "." not in value.split("@")[-1] or any(c.isspace() for c in value):
            raise ValueError("Correo electrónico no válido")
        return value


class CuentaCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    banco: str = Field(..., min_length=3, max_length=65)
    numeroCuenta: str = Field(..., pattern=r'^[0-9]{6,20}$')


class VendedorCreate(BaseModel):
    """Alta de vendedor reservada al administrador autenticado."""
    model_config = ConfigDict(extra="forbid")
    id: int = Field(..., ge=1, le=9999999999, description="Cédula del vendedor")
    nombre: str = Field(..., min_length=2, max_length=100)
    email: str = Field(..., max_length=150)
    password: str = Field(..., min_length=8, max_length=72)

    @field_validator("password")
    @classmethod
    def validar_password(cls, value: str):
        if len(value.encode("utf-8")) > 72:
            raise ValueError("La contraseña supera el límite de bcrypt (72 bytes)")
        return value

    @field_validator("email")
    @classmethod
    def validar_email(cls, value: str):
        return UsuarioCreate.validar_email(value)


class UsuarioUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombre: str = Field(..., min_length=2, max_length=100)
    email: str = Field(..., max_length=150)

    @field_validator("email")
    @classmethod
    def validar_email(cls, value: str):
        return UsuarioCreate.validar_email(value)


class LoginRequest(BaseModel):
    # Coincide con LoginContracts.cs: System.Text.Json produce userName/password
    userName: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    token: str


class EstadoUsuario(BaseModel):
    usuario_id: int
    activo: bool
    bloqueadoPorMultas: bool = False


class IdentidadUsuario(BaseModel):
    id: int
    nombre: str


def _error_bd(error: Exception):
    if isinstance(error, psycopg2.IntegrityError):
        raise HTTPException(status_code=409, detail="Cédula o correo ya registrado") from None
    raise HTTPException(status_code=503, detail="Base de datos no disponible") from None


def _secreto_jwt() -> str:
    secreto = os.getenv("JWT_SECRET", "")
    if len(secreto.encode("utf-8")) < 32:
        raise RuntimeError("Configure JWT_SECRET con al menos 32 bytes en el entorno")
    return secreto


def usuario_actual(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(SEGURIDAD)],
) -> dict:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Token de acceso requerido")
    try:
        claims = jwt.decode(
            credentials.credentials,
            _secreto_jwt(),
            algorithms=["HS256"],
            options={"require": ["sub", "exp", "iat"]},
        )
        usuario_id = int(claims["sub"])
    except (jwt.PyJWTError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Token inválido o vencido") from None
    try:
        usuario = db.obtener_usuario(usuario_id)
    except Exception as error:
        _error_bd(error)
    if not usuario or not usuario["activo"]:
        raise HTTPException(status_code=403, detail="Usuario inexistente o bloqueado")
    return usuario


def _exigir_admin(usuario: dict):
    if usuario["rol"] != "admin":
        raise HTTPException(status_code=403, detail="Se requiere rol administrador")


def _exigir_dueno_o_admin(usuario: dict, usuario_id: int):
    if usuario["rol"] != "admin" and usuario["id"] != usuario_id:
        raise HTTPException(status_code=403, detail="Acceso no autorizado")


@app.get("/health", tags=["Operación"])
def health():
    try:
        db.comprobar_conexion()
        return {"status": "ok"}
    except Exception:
        raise HTTPException(status_code=503, detail="PostgreSQL no disponible") from None


@app.post("/api/auth/login", response_model=LoginResponse, tags=["Autenticación"])
def login(datos: LoginRequest):
    try:
        usuario = db.validar_credenciales(datos.userName.strip(), datos.password)
    except Exception as error:
        _error_bd(error)
    if not usuario:
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    if not usuario["activo"]:
        raise HTTPException(status_code=403, detail="Usuario bloqueado")
    ahora = datetime.now(timezone.utc)
    token = jwt.encode(
        {"sub": str(usuario["id"]), "name": usuario["nombre"],
         "role": usuario["rol"], "iat": ahora, "exp": ahora + timedelta(minutes=30)},
        _secreto_jwt(), algorithm="HS256",
    )
    return LoginResponse(token=token)


@app.get("/api/auth/me", response_model=UsuarioResponse, tags=["Autenticación"])
def me(actual: Annotated[dict, Depends(usuario_actual)]):
    return actual


@app.get("/usuarios", response_model=list[UsuarioResponse], tags=["Usuarios"])
def obtener_usuarios(actual: Annotated[dict, Depends(usuario_actual)]):
    _exigir_admin(actual)
    try:
        return db.listar_usuarios()
    except Exception as error:
        _error_bd(error)


@app.get('/usuarios/bancos', tags=['Cuentas bancarias'])
def bancos_disponibles():
    return list(BANCOS)


@app.get("/usuarios/{usuario_id}", response_model=UsuarioResponse, tags=["Usuarios"])
def obtener_usuario(usuario_id: int, actual: Annotated[dict, Depends(usuario_actual)]):
    _exigir_dueno_o_admin(actual, usuario_id)
    try:
        usuario = db.obtener_usuario(usuario_id)
    except Exception as error:
        _error_bd(error)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return usuario


@app.get("/usuarios/{usuario_id}/identidad", response_model=IdentidadUsuario, tags=["Usuarios"])
def obtener_identidad(usuario_id: int, actual: Annotated[dict, Depends(usuario_actual)]):
    """Consulta mínima para el asesor comercial, sin exponer correo ni contraseña."""
    if actual["rol"] not in ("admin", "vendedor") and actual["id"] != usuario_id:
        raise HTTPException(status_code=403, detail="Acceso no autorizado")
    try:
        usuario = db.obtener_usuario(usuario_id)
    except Exception as error:
        _error_bd(error)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return {"id": usuario["id"], "nombre": usuario["nombre"]}


@app.post("/usuarios", response_model=UsuarioResponse, status_code=201, tags=["Usuarios"])
def crear_usuario(datos: UsuarioCreate):
    """Registro público: solo clientes, con una cuenta de ahorros obligatoria."""
    if datos.banco not in BANCOS:
        raise HTTPException(422, 'Selecciona un banco de la lista')
    try:
        return db.crear_usuario(datos.id, datos.nombre, datos.email, datos.password,
                                banco=datos.banco, numero_cuenta=datos.numeroCuenta)
    except Exception as error:
        _error_bd(error)


@app.get('/usuarios/me/cuentas', tags=['Cuentas bancarias'])
def mis_cuentas(actual: Annotated[dict, Depends(usuario_actual)]):
    if actual['rol'] != 'cliente':
        raise HTTPException(403, 'Las cuentas de ahorros son exclusivas de clientes')
    try:
        return db.listar_cuentas(actual['id'])
    except Exception as error:
        _error_bd(error)


@app.post('/usuarios/me/cuentas', status_code=201, tags=['Cuentas bancarias'])
def nueva_cuenta(datos: CuentaCreate, actual: Annotated[dict, Depends(usuario_actual)]):
    if actual['rol'] != 'cliente':
        raise HTTPException(403, 'Las cuentas de ahorros son exclusivas de clientes')
    if datos.banco not in BANCOS:
        raise HTTPException(422, 'Selecciona un banco de la lista')
    try:
        return db.crear_cuenta(actual['id'], datos.banco, datos.numeroCuenta)
    except psycopg2.IntegrityError:
        raise HTTPException(409, 'La cuenta ya está registrada') from None
    except Exception as error:
        _error_bd(error)


@app.get('/internal/usuarios/{usuario_id}/cuentas/{cuenta_id}', tags=['Operación interna'])
def verificar_cuenta_interna(usuario_id: int, cuenta_id: int,
                            x_internal_key: str | None = Header(default=None)):
    expected=os.environ.get('INTERNAL_API_KEY','')
    if len(expected.encode()) < 32 or not x_internal_key or not hmac.compare_digest(expected,x_internal_key):
        raise HTTPException(403, 'Acceso interno no autorizado')
    try:
        cuenta=db.verificar_cuenta(usuario_id, cuenta_id)
    except Exception as error:
        _error_bd(error)
    if not cuenta:
        raise HTTPException(404, 'Cuenta bancaria no asociada al cliente')
    return cuenta


@app.post("/usuarios/vendedores", response_model=UsuarioResponse, status_code=201, tags=["Usuarios"])
def crear_vendedor(datos: VendedorCreate, actual: Annotated[dict, Depends(usuario_actual)]):
    """Solo el administrador puede dar de alta cuentas de vendedor."""
    _exigir_admin(actual)
    try:
        return db.crear_usuario(datos.id, datos.nombre, datos.email, datos.password, rol="vendedor")
    except Exception as error:
        _error_bd(error)


@app.put("/usuarios/{usuario_id}", response_model=UsuarioResponse, tags=["Usuarios"])
def actualizar_usuario(usuario_id: int, datos: UsuarioUpdate, actual: Annotated[dict, Depends(usuario_actual)]):
    _exigir_dueno_o_admin(actual, usuario_id)
    try:
        usuario = db.actualizar_usuario(usuario_id, datos.nombre, datos.email)
    except Exception as error:
        _error_bd(error)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return usuario


@app.delete("/usuarios/{usuario_id}", status_code=204, tags=["Usuarios"])
def eliminar_usuario(usuario_id: int, actual: Annotated[dict, Depends(usuario_actual)]):
    _exigir_admin(actual)
    if usuario_id == actual["id"]:
        raise HTTPException(status_code=409, detail="No puede eliminar su propia cuenta administradora")
    try:
        objetivo = db.obtener_usuario(usuario_id)
        if objetivo and objetivo["rol"] == "admin":
            raise HTTPException(status_code=409, detail="Las cuentas administradoras están protegidas")
        eliminado = db.eliminar_usuario(usuario_id)
    except HTTPException:
        raise
    except Exception as error:
        _error_bd(error)
    if not eliminado:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return None


@app.get("/internal/usuarios/{usuario_id}/autorizacion", tags=["Operación interna"])
def autorizacion_interna(usuario_id: int, x_internal_key: str | None = Header(default=None)):
    """La red interna y la clave compartida son necesarias para consultar el estado."""
    expected = os.environ.get("INTERNAL_API_KEY", "")
    if len(expected.encode()) < 32 or not x_internal_key or not hmac.compare_digest(expected, x_internal_key):
        raise HTTPException(403, "Acceso interno no autorizado")
    try:
        u = db.autorizacion_usuario(usuario_id)
    except Exception as error:
        _error_bd(error)
    if not u:
        raise HTTPException(404, "Cuenta inexistente")
    return {"id": u["id"], "rol": u["rol"], "activo": u["activo"],
            "bloqueadoPorMultas": bool(u["bloqueado_por_multas"])}


@app.get("/usuarios/{usuario_id}/estado", response_model=EstadoUsuario, tags=["Estado"])
def consultar_estado(usuario_id: int, x_internal_key: str | None = Header(default=None)):
    """Consulta reservada a otros microservicios con clave interna."""
    expected = os.environ.get("INTERNAL_API_KEY", "")
    if len(expected.encode()) < 32 or not x_internal_key or not hmac.compare_digest(expected, x_internal_key):
        raise HTTPException(403, "Acceso interno no autorizado")
    try:
        u = db.autorizacion_usuario(usuario_id)
        activo = u["activo"] if u else None
    except Exception as error:
        _error_bd(error)
    if activo is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return EstadoUsuario(usuario_id=usuario_id, activo=activo, bloqueadoPorMultas=bool(u["bloqueado_por_multas"]))


class CambiarEstado(BaseModel):
    activo: bool


@app.patch('/usuarios/{usuario_id}/estado', tags=['Estado'])
def actualizar_estado_administrativo(usuario_id: int, cambio: CambiarEstado,
                                    actual: Annotated[dict, Depends(usuario_actual)]):
    """Solo administrador: bloqueo y reactivación manual."""
    _exigir_admin(actual)
    if usuario_id == actual['id'] and not cambio.activo:
        raise HTTPException(status_code=409, detail='No puedes bloquear tu propia sesión')
    try:
        changed = db.cambiar_estado(usuario_id, cambio.activo)
    except Exception as error:
        _error_bd(error)
    if not changed:
        raise HTTPException(status_code=404, detail='Usuario no encontrado')
    return {'usuarioId': usuario_id, 'activo': cambio.activo}

@app.post('/internal/usuarios/{usuario_id}/bloquear',tags=['Operación interna'])
def bloqueo_por_incumplimiento(usuario_id:int, x_internal_key:str|None=Header(default=None)):
    """Reservado a Órdenes, que verifica incumplimiento de una orden terminada."""
    expected=os.environ.get('INTERNAL_API_KEY','')
    if len(expected.encode())<32 or not x_internal_key or not hmac.compare_digest(expected,x_internal_key):
        raise HTTPException(403,'Acceso interno no autorizado')
    try:
        u=db.obtener_usuario(usuario_id)
        if not u:raise HTTPException(404,'Cliente no encontrado')
        if u['rol']!='cliente':raise HTTPException(409,'Solo pueden bloquearse cuentas cliente por incumplimiento')
        db.cambiar_restriccion_multas(usuario_id,True)
    except HTTPException:raise
    except Exception as error:_error_bd(error)
    return {'usuarioId':usuario_id,'bloqueadoPorMultas':True}


@app.post('/internal/usuarios/{usuario_id}/desbloquear-multas', tags=['Operación interna'])
def desbloquear_multas(usuario_id: int, x_internal_key: str | None = Header(default=None)):
    """Quita exclusivamente la restricción por multas, NO un bloqueo manual."""
    expected = os.environ.get('INTERNAL_API_KEY', '')
    if len(expected.encode()) < 32 or not x_internal_key or not hmac.compare_digest(expected, x_internal_key):
        raise HTTPException(403, 'Acceso interno no autorizado')
    try:
        if not db.cambiar_restriccion_multas(usuario_id, False):
            raise HTTPException(404, 'Cliente no encontrado')
    except HTTPException:
        raise
    except Exception as error:
        _error_bd(error)
    return {'usuarioId': usuario_id, 'bloqueadoPorMultas': False}
