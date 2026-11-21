# Microservicio de Multas — Cars ATTM

API FastAPI para registrar, revisar y cobrar de forma simulada multas por retraso o daños. En la composición integrada se ejecuta con PostgreSQL y Kafka dentro de la red Docker.

## Flujo integrado actual

1. `ordenes-service` calcula el retraso/daños en la devolución y llama por HTTP a `POST /internal/multas` con `X-Internal-Key`.
2. `multas-service` registra la multa inicialmente como `SOLICITADA` en `multas_db`.
3. Un administrador aprueba o rechaza la multa.
4. El cliente puede solicitar el pago simulado cuando la multa está `APROBADA`.
5. El administrador confirma o rechaza esa solicitud.
6. Al confirmar el pago, Multas publica `Orden_MultaPagada` en Kafka y llama al endpoint interno de Usuarios para retirar únicamente la restricción por multas cuando no queden otras multas pendientes.

El flujo actual de creación de multas es HTTP, no el tópico heredado `Multas_IniciarMulta`. El consumidor Kafka de creación de multas permanece desactivado por defecto (`KAFKA_CONSUMER_ENABLED=false`).

El productor Kafka se activa con `KAFKA_ENABLED=true`. El evento `Usuario_usuarioActivado` pertenece a una ruta de dominio heredada y no debe utilizarse para reactivar cuentas deshabilitadas manualmente. El consumidor heredado de Usuarios permanece desactivado por defecto.

## Endpoints principales

| Método | Ruta | Acceso |
|---|---|---|
| GET | `/health` | Interno / healthcheck; comprueba PostgreSQL |
| POST | `/internal/multas` | Clave `X-Internal-Key` |
| GET | `/api/v1/multas` | Administrador |
| GET | `/api/v1/multas/mis` | Usuario autenticado; solo sus multas |
| POST | `/api/v1/multas/{id}/aprobar` | Administrador |
| POST | `/api/v1/multas/{id}/rechazar` | Administrador |
| POST | `/api/v1/multas/{id}/solicitar-pago` | Titular de la multa |
| POST | `/api/v1/multas/{id}/pago/aprobar` | Administrador |
| POST | `/api/v1/multas/{id}/pago/rechazar` | Administrador |

## Ejecución integrada

Desde la raíz `CARS ATTM V1`:

```powershell
docker compose --env-file .env config --quiet
docker compose --env-file .env up -d --build multas-service
```

Logs:

```powershell
docker compose --env-file .env logs --tail=100 multas-service
```

No ejecutes `docker compose down -v` para reiniciar pruebas: eliminaría los volúmenes.

## Pruebas aisladas

Desde la raíz del proyecto:

```powershell
python tests/check_multas.py
```

Las pruebas usan SQLite y desactivan Kafka; no reemplazan la validación de integración real con PostgreSQL y el broker.
