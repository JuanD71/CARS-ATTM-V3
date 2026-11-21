# Eventos heredados del microservicio de Usuarios (Kafka)

Este consumidor es una compatibilidad heredada y **no forma parte del flujo predeterminado de Cars ATTM**. En `docker-compose.yml` se configura `ENABLE_LEGACY_ACCOUNT_EVENTS=false`.

| Evento | Topic | Efecto heredado |
|---|---|---|
| `Usuario_usuarioActivado` | `Usuario_usuarioActivado` | `activo = TRUE` |
| `Usuario_usuarioDesactivado` | `Usuario_usuarioDesactivado` | `activo = FALSE` |

## Advertencia de seguridad

No actives este consumidor en la instalación integrada sin revisar los productores y las reglas de negocio. Un evento `Usuario_usuarioActivado` puede volver a habilitar una cuenta que un administrador desactivó manualmente. El flujo actual de multas usa `bloqueado_por_multas` y una llamada HTTP interna para retirar esa restricción sin cambiar `activo`.

## Activación opcional

Solo para una integración heredada controlada, define `ENABLE_LEGACY_ACCOUNT_EVENTS=true` en el entorno de `usuarios-service` y verifica primero el formato, la autorización y el origen de cada evento. Los tópicos se crean al iniciar el consumidor. La composición normal no necesita crearlos manualmente.
