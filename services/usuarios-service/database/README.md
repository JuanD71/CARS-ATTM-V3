# Base de datos Usuarios - Cars ATTM

PostgreSQL 16. En el sistema unificado se inicia desde el `docker-compose.yml` de la raíz, NO desde Dockerfile separado.

En un volumen vacío, `init/01_schema.sql` crea la tabla y `init/02_seed.sql` inserta los cinco usuarios ficticios (2 clientes, 2 vendedores y 1 administrador). Las contraseñas se almacenan mediante bcrypt/pgcrypto.

Si se reutiliza la base de la Fase 1, **no se ejecutarán nuevamente los scripts de inicialización**. Conserva `USUARIOS_DB_PASSWORD` del archivo `.env` anterior.
