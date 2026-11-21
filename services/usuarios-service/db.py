"""Repositorio PostgreSQL del microservicio de Usuarios.

Cada operación abre su propia conexión; las sentencias están parametrizadas.
La clave primaria de usuarios es la cédula, tal como indica el esquema original.
"""
import os
import secrets
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor

CAMPOS_PUBLICOS = "id, nombre, email, rol, activo"


def _conexion():
    """Acepta DATABASE_URL del repositorio original o variables separadas de Docker."""
    url = os.getenv("DATABASE_URL")
    if url:
        return psycopg2.connect(url, connect_timeout=5)
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "usuarios_db"),
        user=os.getenv("DB_USER", "usuarios_user"),
        password=os.environ.get("DB_PASSWORD", ""),
        connect_timeout=5,
    )


def comprobar_conexion() -> None:
    conn = _conexion()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
    finally:
        conn.close()


def listar_usuarios():
    conn = _conexion()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(f"SELECT {CAMPOS_PUBLICOS} FROM usuarios ORDER BY id")
            return [dict(fila) for fila in cur.fetchall()]
    finally:
        conn.close()


def obtener_usuario(usuario_id: int):
    conn = _conexion()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(f"SELECT {CAMPOS_PUBLICOS} FROM usuarios WHERE id = %s", (usuario_id,))
            fila = cur.fetchone()
            return dict(fila) if fila else None
    finally:
        conn.close()


def crear_usuario(usuario_id: int, nombre: str, email: str, password: str, rol: str = "cliente",
                  banco: str | None = None, numero_cuenta: str | None = None):
    conn = _conexion()
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """INSERT INTO usuarios (id, nombre, email, password_hash, rol)
                       VALUES (%s, %s, LOWER(%s), crypt(%s, gen_salt('bf')), %s)
                       RETURNING id, nombre, email, rol, activo""",
                    (usuario_id, nombre, email, password, rol),
                )
                usuario = dict(cur.fetchone())
                if rol == "cliente":
                    if not banco or not numero_cuenta:
                        raise ValueError("Se requiere una cuenta de ahorros del cliente")
                    cur.execute(
                        """INSERT INTO cuentas_bancarias (usuario_id, banco, numero_cuenta, principal)
                           VALUES (%s,%s,%s,TRUE)""", (usuario_id, banco, numero_cuenta))
                return usuario
    finally:
        conn.close()


def actualizar_usuario(usuario_id: int, nombre: str, email: str):
    conn = _conexion()
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """UPDATE usuarios SET nombre = %s, email = LOWER(%s)
                       WHERE id = %s RETURNING id, nombre, email, rol, activo""",
                    (nombre, email, usuario_id),
                )
                fila = cur.fetchone()
                return dict(fila) if fila else None
    finally:
        conn.close()


def eliminar_usuario(usuario_id: int) -> bool:
    conn = _conexion()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM usuarios WHERE id = %s", (usuario_id,))
                return cur.rowcount > 0
    finally:
        conn.close()


def validar_credenciales(identificador: str, password: str):
    """Verifica bcrypt dentro de PostgreSQL (pgcrypto), igual que el seed original."""
    cedula = int(identificador) if identificador.isdecimal() else -1
    conn = _conexion()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT id, nombre, email, rol, activo FROM usuarios
                   WHERE (LOWER(email) = LOWER(%s) OR id = %s)
                     AND password_hash = crypt(%s, password_hash)""",
                (identificador, cedula, password),
            )
            fila = cur.fetchone()
            return dict(fila) if fila else None
    finally:
        conn.close()


def cambiar_estado(usuario_id: int, activo: bool) -> bool:
    """Aplicación idempotente del evento Kafka existente."""
    conn = _conexion()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE usuarios SET activo = %s WHERE id = %s", (activo, usuario_id))
                return cur.rowcount > 0
    finally:
        conn.close()


def obtener_activo(usuario_id: int) -> Optional[bool]:
    conn = _conexion()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT activo FROM usuarios WHERE id = %s", (usuario_id,))
            fila = cur.fetchone()
            return fila[0] if fila else None
    finally:
        conn.close()


def asegurar_esquema_restricciones() -> None:
    """Migración segura para volúmenes PostgreSQL ya existentes."""
    conn = _conexion()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS bloqueado_por_multas BOOLEAN NOT NULL DEFAULT FALSE")
                cur.execute("""CREATE TABLE IF NOT EXISTS cuentas_bancarias (
                    id BIGSERIAL PRIMARY KEY,
                    usuario_id BIGINT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                    banco VARCHAR(65) NOT NULL,
                    numero_cuenta VARCHAR(24) NOT NULL,
                    principal BOOLEAN NOT NULL DEFAULT FALSE,
                    creada_en TIMESTAMPTZ NOT NULL DEFAULT now(),
                    UNIQUE(usuario_id, banco, numero_cuenta),
                    CONSTRAINT chk_numero_cuenta CHECK (numero_cuenta ~ '^[0-9]{6,20}$')
                )""")
                cur.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_cuenta_principal_cliente
                    ON cuentas_bancarias(usuario_id) WHERE principal""")
                # Sólo los clientes existentes reciben cuentas FICTICIAS para demostración.
                # Se ejecuta de forma incremental sin reemplazar cuentas existentes.
                cur.execute("""SELECT u.id FROM usuarios u WHERE u.rol='cliente' AND NOT EXISTS
                    (SELECT 1 FROM cuentas_bancarias c WHERE c.usuario_id=u.id)""")
                for (uid,) in cur.fetchall():
                    numero = '9' + f'{secrets.randbelow(10**11):011d}'
                    cur.execute("""INSERT INTO cuentas_bancarias
                        (usuario_id,banco,numero_cuenta,principal) VALUES (%s,%s,%s,TRUE)""",
                        (uid, 'Bancolombia', numero))
    finally:
        conn.close()


def listar_cuentas(usuario_id: int):
    conn = _conexion()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""SELECT id, banco, RIGHT(numero_cuenta, 4) AS ultimos4, principal
                           FROM cuentas_bancarias WHERE usuario_id=%s
                           ORDER BY principal DESC, id""", (usuario_id,))
            return [dict(x) for x in cur.fetchall()]
    finally:
        conn.close()


def crear_cuenta(usuario_id: int, banco: str, numero_cuenta: str):
    conn = _conexion()
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""INSERT INTO cuentas_bancarias (usuario_id,banco,numero_cuenta,principal)
                               VALUES (%s,%s,%s,NOT EXISTS(SELECT 1 FROM cuentas_bancarias WHERE usuario_id=%s))
                               RETURNING id, banco, RIGHT(numero_cuenta,4) AS ultimos4, principal""",
                            (usuario_id,banco,numero_cuenta,usuario_id))
                return dict(cur.fetchone())
    finally:
        conn.close()


def verificar_cuenta(usuario_id: int, cuenta_id: int):
    conn = _conexion()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""SELECT c.id,c.banco,RIGHT(c.numero_cuenta,4) AS ultimos4,c.principal
                           FROM cuentas_bancarias c JOIN usuarios u ON c.usuario_id=u.id
                           WHERE c.id=%s AND c.usuario_id=%s AND u.rol='cliente' AND u.activo""",
                        (cuenta_id,usuario_id))
            row=cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def autorizacion_usuario(usuario_id: int):
    conn = _conexion()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, rol, activo, bloqueado_por_multas FROM usuarios WHERE id=%s", (usuario_id,))
            fila = cur.fetchone()
            return dict(fila) if fila else None
    finally:
        conn.close()


def cambiar_restriccion_multas(usuario_id: int, restringido: bool) -> bool:
    """No modifica 'activo', controlado exclusivamente por administración."""
    conn = _conexion()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE usuarios SET bloqueado_por_multas=%s WHERE id=%s AND rol='cliente'",
                    (restringido, usuario_id),
                )
                return cur.rowcount > 0
    finally:
        conn.close()
