# Archivos ZIP individuales

Los ZIP individuales contienen solo el código de cada microservicio (Dockerfile, dependencias, endpoints, modelos y SQL cuando corresponda). Son componentes de la misma versión del ZIP general.

Si necesitas sustituir un microservicio, extrae su carpeta dentro de `CARS ATTM V1/services/` y reconstruye ese servicio desde la raíz del proyecto. Por ejemplo:

```powershell
docker compose --env-file .env build usuarios-service
docker compose --env-file .env up -d --no-deps usuarios-service
```

No reemplaces otros servicios ni elimines los volúmenes PostgreSQL.

**Para ejecutar el sistema completo necesitas el ZIP general**, que incluye Blazor, imágenes, Docker Compose, `.env`, Kafka y las cinco bases de datos. Un ZIP individual no es una aplicación lista para abrir en el navegador.
