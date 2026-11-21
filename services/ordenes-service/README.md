# Órdenes y solicitudes de pago — Cars ATTM

API FastAPI con PostgreSQL, Docker, JWT y comunicación HTTP interna con Usuarios, Inventario, Carrito y Multas. **Sin datos predeterminados**. Tablas creadas por SQLAlchemy: `ordenes`, `detalle_orden`, `solicitudes_pago`.

**Regla obligatoria:** `POST /api/v1/ordenes/checkout` NO realiza ningún cobro. Crea una orden `PAGO_SOLICITADO` y una solicitud `SOLICITADA` en PostgreSQL. Únicamente un JWT con rol `admin` puede ejecutar `/api/v1/ordenes/{id}/pago/aprobar` o `/pago/rechazar`. La aceptación marca pago simulado `APROBADA` y orden `PAGADA`. El asesor solo puede registrar `/entrega` cuando el pago está aprobado. En `/devolucion`, las multas se envían como **solicitudes** para aprobación del administrador.

`/docs` contiene todos los endpoints. Ver README general y ejecutar desde la raíz.
