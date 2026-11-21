"""Autorización JWT con roles compartidos. JWT se valida en cada solicitud."""
import os,hmac,jwt,httpx
from fastapi import Header,HTTPException

def current_user(authorization:str|None=Header(default=None)):
    if not authorization or not authorization.lower().startswith('bearer '):
        raise HTTPException(401,'Debes iniciar sesión')
    try:
        secret=os.environ['JWT_SECRET']
        if len(secret.encode())<32:raise ValueError('Secreto insuficiente')
        payload=jwt.decode(authorization.split(' ',1)[1],secret,algorithms=['HS256'],options={'require':['sub','iat','exp']})
        return validar_usuario_activo(int(payload['sub']), payload.get('role', 'cliente'))
    except (jwt.PyJWTError,KeyError,ValueError,TypeError):
        raise HTTPException(401,'Sesión inválida o expirada') from None

def require_role(user,*roles):
    if user['rol'] not in roles:raise HTTPException(403,'No tienes permisos para esta operación')

def internal_key(x_internal_key:str|None=Header(default=None)):
    expected=os.environ.get('INTERNAL_API_KEY','')
    if len(expected.encode())<32 or not x_internal_key or not hmac.compare_digest(expected,x_internal_key):
        raise HTTPException(403,'Clave interna inválida')


def validar_usuario_activo(usuario_id: int, rol_token: str) -> dict:
    """Validación de acceso en tiempo real (fallo seguro ante caída de Usuarios).

    El rol efectivo siempre proviene del servidor, nunca del token obsoleto.
    """
    url = os.environ.get("USUARIOS_URL", "").rstrip("/")
    key = os.environ.get("INTERNAL_API_KEY", "")
    if not url or len(key.encode()) < 32:
        raise HTTPException(503, "Servicio de autorización no configurado")
    try:
        response = httpx.get(
            f"{url}/internal/usuarios/{usuario_id}/autorizacion",
            headers={"X-Internal-Key": key}, timeout=4.0,
        )
        if response.status_code == 404:
            raise HTTPException(401, "La cuenta ya no existe")
        response.raise_for_status()
        user = response.json()
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError, KeyError):
        raise HTTPException(503, "No se pudo verificar el estado de tu cuenta") from None
    if not user.get("activo", False):
        raise HTTPException(403, "Cuenta desactivada por el administrador")
    rol_real = user.get("rol")
    if rol_real not in ("admin", "vendedor", "cliente"):
        raise HTTPException(403, "Rol inválido")
    return {"id": usuario_id, "rol": rol_real, "bloqueadoPorMultas": bool(user.get("bloqueadoPorMultas", False))}
