# Pulso

Asistente personal con FastAPI y Vue 3. Primer incremento del proyecto descrito en [plan.md](plan.md), preparado para Docker y Dokploy.

## Empezar con Docker

Desde la raíz del proyecto:

```bash
docker compose -f infra/compose.yaml up -d --build
```

Abre **http://localhost:8080** y crea una cuenta. El entorno local verifica automáticamente el correo; ese comportamiento está desactivado en la composición de producción. No hay usuarios ni contraseñas predeterminados.

Para parar los servicios conservando datos:

```bash
docker compose -f infra/compose.yaml stop
```

El frontend, backend y scheduler se construyen desde este repositorio; PostgreSQL usa un volumen persistente. Si el puerto 8080 está ocupado, define `WEB_PORT=8081` al ejecutar Compose.

## Incluido en este incremento

- Registro, login, logout, sesiones revocables, CSRF y aislamiento por usuario.
- Verificación y recuperación por correo: SMTP en producción y outbox explícita para desarrollo.
- Crear, editar y completar tareas; programar y cancelar recordatorios únicos, diarios o semanales.
- Scheduler independiente y persistencia de avisos internos, incluso con el navegador cerrado.
- Estadísticas básicas de tareas guardadas y preferencias de zona horaria.
- Chat Groq configurable con herramientas para consultar/crear tareas y programar avisos; sin clave muestra un estado de configuración pendiente.
- Interfaz responsive en español y despliegue del frontend/API bajo el mismo origen.

**Todavía pendiente:** envío y recepción por WhatsApp/Evolution, vinculación del número, STT/TTS, reproducción de voz, análisis CSV/Excel, Redis/Celery, migraciones de evolución de esquema y endurecimiento operativo completo. Un aviso interno guardado no representa una entrega por WhatsApp. Los proveedores externos no se han probado con credenciales reales.

## Groq

Configura `GROQ_API_KEY` en el entorno del servicio API, nunca en Vue. Para Compose local se puede pasar como variable del shell o usar un archivo privado con `--env-file`. No copies valores de ejemplo de producción al entorno local sin revisar su significado.

## Dokploy

Usa [infra/compose.dokploy.yaml](infra/compose.dokploy.yaml). Las instrucciones de dominio, SMTP, variables y respaldo están en [docs/dokploy.md](docs/dokploy.md).

## Desarrollo y pruebas

Backend: seguir [backend/README.md](backend/README.md) para entorno virtual, configuración y pytest.

Frontend:

```bash
cd frontend
npm ci
npm run dev
```

Vite redirige `/api` a `http://127.0.0.1:8000`; se puede cambiar mediante `API_PROXY_TARGET`. Para probar la web de desarrollo contra Docker: `API_PROXY_TARGET=http://127.0.0.1:8080 npm run dev`.

```bash
cd frontend
npm run test:unit
npm run build
npx playwright install chromium
npm run test:e2e
```

Las pruebas E2E necesitan API de desarrollo con verificación automática habilitada. Para ejecutarlas contra el conjunto Docker: `E2E_BASE_URL=http://127.0.0.1:8080 npm run test:e2e`. Crean cuentas y tareas de prueba en esa base; usar siempre un entorno local/de pruebas.

El plan completo sigue en desarrollo; [docs/progreso.md](docs/progreso.md) registra el alcance de este incremento y sus decisiones.
