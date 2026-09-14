# Desplegar Pulso en Dokploy

Este despliegue corresponde al primer incremento: web, API, PostgreSQL y scheduler de avisos internos. Evolution API, STT/TTS y cola distribuida todavía no forman parte de los contenedores.

## Servicios y dominio

| Servicio | Función | Puerto interno | Persistencia |
| --- | --- | --- | --- |
| `web` | Vue compilado servido por Nginx sin privilegios | 8080 | Imagen estática |
| `api` | FastAPI y sesiones | 8000 | PostgreSQL |
| `scheduler` | Procesa vencimientos cada 15 segundos | Ninguno | PostgreSQL |
| `db` | PostgreSQL 17 | 5432, privado | `postgres_data` |

1. Publicar el código en un repositorio accesible por tu Dokploy, o cargarlo mediante su método de despliegue correspondiente.
2. Crear un servicio **Docker Compose**, conectar el repositorio y seleccionar `infra/compose.dokploy.yaml` como ruta Compose. Los contextos `../backend` y `../frontend` son relativos a ese archivo.
3. Añadir las variables indicadas abajo en la sección de entorno del servicio. No usar `infra/compose.yaml` en producción: contiene valores de desarrollo y desactiva la verificación de email.
4. En **Domains**, añadir tu dominio al servicio **web**, puerto **8080**, con HTTPS. La web usa `/api` en ese mismo dominio; Nginx lo redirige a `api:8000`.
5. Revisar **Preview Compose** y comprobar que `web` conserva la red privada compartida con `api`, además de la red que Dokploy agregue para Traefik. No publicar PostgreSQL ni FastAPI con puertos del host.
6. Desplegar y esperar los healthchecks. Crear una cuenta y verificar el enlace recibido por correo.

La configuración nativa de dominios está documentada por [Dokploy](https://docs.dokploy.com/docs/core/docker-compose/domains). Los cambios de dominio requieren un nuevo despliegue del servicio Compose.

## Variables

- `APP_URL`: origen público HTTPS, sin barra final; ejemplo `https://pulso.tudominio.com`. Se usa para los enlaces de correo y el origen permitido.
- `POSTGRES_PASSWORD`: contraseña aleatoria de la base de datos.
- `DATABASE_URL`: `postgresql+psycopg://pulso:CONTRASEÑA_CODIFICADA@db:5432/pulso`. La contraseña debe coincidir con `POSTGRES_PASSWORD`; codificar caracteres reservados de URL.
- `SECRET_KEY`: secreto aleatorio de al menos 32 caracteres. Puedes generarlo con `openssl rand -hex 32` y copiarlo directamente a Dokploy.
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`: servidor y remitente verificado para correos de acceso.
- `SMTP_USERNAME`, `SMTP_PASSWORD`: credenciales si tu proveedor las exige.
- `SMTP_STARTTLS=true`: conexión STARTTLS, normalmente puerto 587. No confundir con TLS implícito del puerto 465.
- `GROQ_API_KEY`: opcional para activar el chat. Sin ella, tareas y avisos internos siguen funcionando.
- `GROQ_CHAT_MODEL`: modelo de lenguaje con herramientas, por defecto `llama-3.3-70b-versatile`.

`ENVIRONMENT=production`, `COOKIE_SECURE=true` y los indicadores de desarrollo desactivados ya están fijados en Compose. Nunca guardar claves reales en `.env.example`, Dockerfiles o variables del frontend.

## Actualizaciones y datos

El volumen `postgres_data` conserva las cuentas, sesiones, tareas, recordatorios e historial entre reconstrucciones. Mantener el mismo proyecto Compose y volumen al actualizar. No usar `docker compose down -v` para actualizar: eliminaría el volumen.

En este incremento, el backend crea las tablas faltantes al arrancar; aún no hay migraciones Alembic para cambios de esquema existentes. Una actualización futura que cambie columnas necesita su migración antes de desplegar. No aplicar cambios incompatibles a una base con datos sin esa migración.

Para un respaldo lógico, desde un entorno con acceso al Compose desplegado:

```bash
docker compose -f infra/compose.dokploy.yaml exec -T db pg_dump -U pulso -d pulso -Fc > pulso-backup.dump
```

Guardar el archivo fuera del servidor y protegerlo como datos privados. Para comprobar la restauración, usar una base de datos aislada y vacía con `pg_restore`; verificar cuentas, tareas y avisos antes de depender del respaldo. No restaurar sobre producción como prueba.

## Comprobaciones y diagnóstico

- Web: `/health` devuelve `ok`.
- API: healthcheck interno en `http://api:8000/health`.
- Base de datos: `pg_isready`.
- Scheduler: revisar su estado y los conteos de procesamiento en los logs; una base saludable no demuestra por sí sola que el scheduler esté avanzando.
- Error 502: verificar red privada, salud de la API y puerto 8080 seleccionado para la web.
- Login sin sesión persistente: verificar que el acceso sea HTTPS y que web/API compartan origen.
- Correo ausente: revisar SMTP y remitente autorizado. No habilitar el bypass de desarrollo para resolverlo en producción.

Este documento prepara el despliegue. No se ha accedido al Dokploy del usuario ni publicado un dominio.
