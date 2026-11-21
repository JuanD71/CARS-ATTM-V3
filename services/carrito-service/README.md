# Carrito — Cars ATTM

API FastAPI con PostgreSQL, Docker y JWT. **Sin registros predeterminados**. Tablas `carritos`, `items_carrito` creadas por SQLAlchemy. Solo clientes pueden agregar vehículos (máximo 5), con fechas y disponibilidad confirmada en Inventario. Cada cliente ve únicamente su carrito.

Endpoints: `GET /api/v1/carrito`, `POST /api/v1/carrito/elementos`, `DELETE /api/v1/carrito/elementos/{id}`, `DELETE /api/v1/carrito` y limpieza interna protegida por `X-Internal-Key`.

No publica ni confirma pagos. Úsalo con el Docker Compose de la raíz.
