-- ============================================================
-- Microservicio de Usuarios - Creación de tablas
-- El campo "id" es el número de cédula del usuario.
-- El campo "activo" lo modifican los eventos
-- Usuario_usuarioActivado y Usuario_usuarioDesactivado.
-- ============================================================

-- Permite cifrar contraseñas con bcrypt (crypt / gen_salt)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS usuarios (
    id             BIGINT       PRIMARY KEY,   -- número de cédula (lo envía el cliente, no se autogenera)
    nombre         VARCHAR(100) NOT NULL,
    email          VARCHAR(150) NOT NULL UNIQUE,
    password_hash  VARCHAR(255) NOT NULL,
    rol            VARCHAR(30)  NOT NULL DEFAULT 'cliente',
    activo         BOOLEAN      NOT NULL DEFAULT TRUE,
    creado_en      TIMESTAMP    NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_usuarios_cedula CHECK (id BETWEEN 1 AND 9999999999),
    CONSTRAINT chk_usuarios_rol    CHECK (rol IN ('cliente', 'vendedor', 'admin'))
);

CREATE INDEX IF NOT EXISTS idx_usuarios_rol ON usuarios (rol);

-- Evita cuentas duplicadas que solo cambian mayúsculas/minúsculas del correo.
CREATE UNIQUE INDEX IF NOT EXISTS uq_usuarios_email_lower ON usuarios (LOWER(email));

-- El incumplimiento restringe alquilar, pero no impide iniciar sesión y pagar multas.
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS bloqueado_por_multas BOOLEAN NOT NULL DEFAULT FALSE;

-- Cuentas de ahorros por cliente (los vendedores y admin no las requieren).
CREATE TABLE IF NOT EXISTS cuentas_bancarias (
    id BIGSERIAL PRIMARY KEY,
    usuario_id BIGINT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    banco VARCHAR(65) NOT NULL,
    numero_cuenta VARCHAR(24) NOT NULL,
    principal BOOLEAN NOT NULL DEFAULT FALSE,
    creada_en TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(usuario_id,banco,numero_cuenta),
    CONSTRAINT chk_numero_cuenta CHECK (numero_cuenta ~ '^[0-9]{6,20}$')
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_cuenta_principal_cliente
    ON cuentas_bancarias(usuario_id) WHERE principal;
