# Microservicio de Usuarios — Cars ATTM

API FastAPI para registro, autenticación JWT, perfiles y administración de cuentas. La instalación integrada usa Python 3.12, PostgreSQL 16 y comunicación HTTP interna entre microservicios.

## Endpoints principales

| Método | Ruta | Acceso |
|---|---|---|
| POST | `/api/auth/login` | Público |
| GET | `/api/auth/me` | Usuario autenticado |
| POST | `/usuarios` | Registro público; solo rol cliente |
| GET | `/usuarios` | Administrador |
| POST | `/usuarios/vendedores` | Administrador |
| PATCH | `/usuarios/{id}/estado` | Administrador |
| POST | `/internal/usuarios/{id}/bloquear` | Clave interna |
| POST | `/internal/usuarios/{id}/desbloquear-multas` | Clave interna |
| GET | `/health` | Healthcheck interno |

Las contraseñas se almacenan con `pgcrypto`/bcrypt. Los roles se verifican en el servidor y los microservicios consultan el estado actual de la cuenta mediante el endpoint interno de autorización.

## Kafka heredado

El consumidor de activación/desactivación de cuentas es una integración heredada y está desactivado por defecto (`ENABLE_LEGACY_ACCOUNT_EVENTS=false`). No lo actives en la composición normal: el evento `Usuario_usuarioActivado` puede cambiar `activo` a `TRUE`, mientras que el flujo actual de multas utiliza una restricción separada `bloqueado_por_multas` y una llamada HTTP interna para retirarla. Consulta `EVENTOS.md` antes de activar esta integración heredada.

## Ejecución integrada

Desde la raíz `CARS ATTM V1`:

```powershell
docker compose --env-file .env config --quiet
docker compose --env-file .env up -d --build usuarios-service
```

No elimines los volúmenes PostgreSQL para reiniciar el servicio.
