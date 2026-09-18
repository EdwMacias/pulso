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
- Vinculación verificada de un teléfono y conversación de texto entrante por
  Evolution API 2.3.7; Pulso solo responde cuando el usuario vinculado escribe
  primero.
- Documentos PDF privados con RAG: preguntas respondidas por Groq a partir de
  los fragmentos recuperados, con fuentes visibles en la interfaz.
- Interfaz responsive en español y despliegue del frontend/API bajo el mismo origen.

**Todavía pendiente:** recordatorios salientes por WhatsApp, multimedia y voz
STT/TTS, reproducción de voz, análisis CSV/Excel, Redis/Celery, migraciones de
evolución de esquema y endurecimiento operativo completo. Un aviso interno
guardado no representa una entrega por WhatsApp. Los proveedores externos no se
han probado con credenciales reales.

## Groq

Configura `GROQ_API_KEY` en el entorno del servicio API, nunca en Vue. Para Compose local se puede pasar como variable del shell o usar un archivo privado con `--env-file`. No copies valores de ejemplo de producción al entorno local sin revisar su significado.

## RAG sobre documentos

La sección **Documentos** implementa Retrieval-Augmented Generation:

1. **Ingesta** (`backend/app/document_service.py`): `pypdf` extrae el texto de
   cada página y lo divide en fragmentos de hasta 1500 caracteres con 250 de
   solapamiento, guardados con su número de página.
2. **Recuperación** (`backend/app/retrieval.py`): BM25 sin dependencias
   externas; ignora acentos, mayúsculas, plurales simples y palabras vacías.
   Solo se usan fragmentos con coincidencias.
3. **Aumento**: los mejores fragmentos completos, dentro del presupuesto de
   `DOCUMENT_MAX_CONTEXT_CHUNKS`/`DOCUMENT_MAX_CONTEXT_CHARS`, se envían como
   contexto delimitado y no confiable.
4. **Generación**: Groq responde citando páginas. Sin fragmentos relevantes no
   se consulta al modelo y se indica que el documento no contiene la respuesta.

El **Asistente** (web y WhatsApp) también usa RAG: dispone de las herramientas
`list_documents` y `search_documents`, que recuperan con BM25 los fragmentos de
todos los PDFs listos del usuario, y responde citando documento y página.

**Tareas desde documentos** (`backend/app/document_tasks.py`): al subir un PDF,
o con el botón «Extraer tareas», Groq propone pendientes en JSON (vuelos,
citas, plazos, facturas) con página y cita literal de origen. Las facturas a
crédito se marcan como cobro (venta) o pago (compra), con emisor, cliente,
valor y vencimiento; el usuario puede invertir la clasificación. Nada se guarda
hasta confirmar; al agregar se crean las tareas y sus recordatorios futuros.

La interfaz muestra el recorrido y cada fuente recuperada con su página,
puntuación BM25 y términos resaltados. Los PDFs se guardan en
`DOCUMENT_STORAGE_PATH` (en Docker, el volumen `app_data`).

## Dokploy

Usa [infra/compose.dokploy.yaml](infra/compose.dokploy.yaml). Las instrucciones de dominio, SMTP, variables y respaldo están en [docs/dokploy.md](docs/dokploy.md).

La configuración de Evolution API, el webhook `MESSAGES_UPSERT` y el worker de
WhatsApp también están documentados allí. Las claves permanecen exclusivamente
en el backend.

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
