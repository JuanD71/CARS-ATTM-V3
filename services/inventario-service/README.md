# Inventario — Cars ATTM

API FastAPI con PostgreSQL, Docker y JWT compartido. Tabla `vehiculos` (40 registros ficticios de demostración) y `reservas`. El script `database/init/01_schema_seed.sql` instala los datos únicamente en la creación inicial del volumen.

`GET /api/v1/vehiculos` y `GET /api/v1/vehiculos/{id}` públicos; filtro opcional `fechaInicio/fechaFin` y filtros de marca/categoría. `POST/DELETE` requieren JWT de administrador. `POST /internal/reservas` y `DELETE /internal/reservas/{ordenId}` exigen `X-Internal-Key` (nunca llamar desde navegador).

PostgreSQL utiliza un índice EXCLUDE GiST para evitar reservas temporales superpuestas del mismo vehículo, incluso ante solicitudes concurrentes. Los contratos se consultan en `/docs`.

Ejecutar integrado en la carpeta raíz del proyecto: `docker compose up --build -d`.
