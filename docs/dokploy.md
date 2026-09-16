# Desplegar Pulso en Dokploy

Este despliegue incluye web, API, PostgreSQL, scheduler de avisos internos y un
worker que procesa mensajes entrantes de WhatsApp. Evolution API 2.3.7 permanece
como servicio externo; STT/TTS y la cola distribuida todavía no forman parte de
los contenedores.

## Servicios y dominio

| Servicio | Función | Puerto interno | Persistencia |
| --- | --- | --- | --- |
| `web` | Vue compilado servido por Nginx sin privilegios | 8080 | Imagen estática |
| `api` | FastAPI y sesiones | 8000 | PostgreSQL |
| `scheduler` | Procesa vencimientos cada 15 segundos | Ninguno | PostgreSQL |
| `whatsapp-worker` | Procesa verificaciones y conversaciones entrantes | Ninguno | PostgreSQL |
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
- `WHATSAPP_API_URL`: origen HTTPS de Evolution API 2.3.7, sin barra final.
- `WHATSAPP_API_KEY`: API key de Evolution; nunca debe exponerse al frontend.
- `WHATSAPP_INSTANCE`: nombre exacto de la instancia emisora ya conectada.
- `WHATSAPP_WEBHOOK_SECRET`: secreto aleatorio de al menos 32 caracteres. Usa un
  valor distinto de `SECRET_KEY`.
- `WHATSAPP_WORKER_POLL_SECONDS`: intervalo del worker, por defecto 2 segundos.

`ENVIRONMENT=production`, `COOKIE_SECURE=true` y los indicadores de desarrollo desactivados ya están fijados en Compose. Nunca guardar claves reales en `.env.example`, Dockerfiles o variables del frontend.

## Configurar el webhook de Evolution API 2.3.7

Después de desplegar Pulso, configura el webhook por instancia en Evolution. El
endpoint de Pulso es público, pero autentica cada petición con el encabezado
personalizado `X-Webhook-Secret`:

```bash
curl --request POST \
  --url "https://EVOLUTION_HOST/webhook/set/INSTANCIA" \
  --header "apikey: EVOLUTION_API_KEY" \
  --header "Content-Type: application/json" \
  --data '{
    "webhook": {
      "enabled": true,
      "url": "https://PULSO_DOMINIO/api/v1/integrations/evolution/webhook",
      "byEvents": false,
      "base64": false,
      "headers": {
        "X-Webhook-Secret": "EL_MISMO_VALOR_DE_WHATSAPP_WEBHOOK_SECRET"
      },
      "events": ["MESSAGES_UPSERT"]
    }
  }'
```

Sustituye todos los marcadores localmente; no pegues secretos en tickets, logs
ni commits. Confirma la configuración con
`GET /webhook/find/INSTANCIA`. `byEvents` debe permanecer en `false`, porque
Pulso expone una sola ruta de webhook.

La versión 2.3.7 ha tenido reportes de configuraciones de webhook que dejan de
emitir después de reconexiones. Si Pulso no recibe mensajes, comprueba primero
el estado de la instancia y vuelve a consultar `/webhook/find/INSTANCIA` antes
de regenerar credenciales.

En local, el worker está detrás del perfil Compose `whatsapp` para que el stack
pueda arrancar sin credenciales externas:

```bash
docker compose --env-file .env -f infra/compose.yaml --profile whatsapp up -d --build
```

Pulso ignora grupos, mensajes propios, multimedia y números no vinculados. Una
respuesta solo se genera después de recibir un texto privado desde el número
verificado. La aceptación del endpoint de Evolution no demuestra entrega ni
lectura en el teléfono. Para evitar mensajes o acciones duplicadas tras una
caída del worker, cada turno se marca como iniciado antes de contactar Groq o
Evolution. Si el proceso se interrumpe y el resultado queda desconocido, Pulso
no lo reintenta automáticamente y el usuario puede escribir de nuevo.

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
- WhatsApp worker: revisar que esté activo, que el webhook entregue
  `MESSAGES_UPSERT` y que el usuario figure como vinculado en Configuración.
- Error 502: verificar red privada, salud de la API y puerto 8080 seleccionado para la web.
- Login sin sesión persistente: verificar que el acceso sea HTTPS y que web/API compartan origen.
- Correo ausente: revisar SMTP y remitente autorizado. No habilitar el bypass de desarrollo para resolverlo en producción.

Este documento prepara el despliegue. No se ha accedido al Dokploy del usuario ni publicado un dominio.
