# Conexión entrante de WhatsApp con Evolution API 2.3.7

## Objetivo

Permitir que un usuario de Pulso vincule y verifique su número personal de
WhatsApp y converse con el agente a través de la instancia emisora existente de
Evolution API 2.3.7. Pulso solo responderá como consecuencia directa de un
mensaje entrante del usuario vinculado; este alcance no habilita recordatorios
ni campañas proactivas por WhatsApp.

## Alcance

Este incremento incluye:

- Registro de un teléfono en formato E.164 desde la configuración de Pulso.
- Verificación de propiedad mediante un código temporal enviado por el usuario
  desde ese teléfono al número emisor conectado a Evolution.
- Recepción autenticada de eventos `messages.upsert`.
- Procesamiento persistente e idempotente de mensajes privados de texto.
- Uso del coordinador Groq y de sus herramientas existentes con la identidad
  del usuario vinculado.
- Envío de la respuesta por `POST /message/sendText/{instance}`.
- Consulta de estado, reemplazo del desafío y desvinculación desde Pulso.
- Pruebas de backend, frontend y flujo integrado.

Quedan fuera de alcance:

- Mensajes proactivos, recordatorios o campañas por WhatsApp.
- Grupos, estados, llamadas, imágenes, documentos y notas de voz.
- STT, TTS y respuestas de audio.
- Redis, Celery y garantías de entrega o lectura del proveedor.
- Creación o emparejamiento de la instancia emisora de Evolution.

## Arquitectura

Se utilizará una bandeja de entrada persistente y un worker independiente. El
webhook valida y persiste rápidamente cada evento; no mantiene abierta la
petición mientras consulta Groq ni mientras envía la respuesta. El worker
reclama eventos pendientes, ejecuta la lógica de vinculación o conversación y
registra el resultado.

Esta separación evita que los reintentos o timeouts de Evolution produzcan
respuestas duplicadas y permite recuperar trabajo después de un reinicio sin
introducir Redis o Celery en este incremento.

## Configuración del servidor

Se añadirán variables de entorno únicamente del lado backend:

- `WHATSAPP_API_URL`: URL base de Evolution API, sin barra final.
- `WHATSAPP_API_KEY`: valor enviado en el encabezado `apikey`.
- `WHATSAPP_INSTANCE`: nombre exacto de la instancia emisora.
- `WHATSAPP_WEBHOOK_SECRET`: secreto aleatorio independiente para autenticar el
  webhook de Pulso.
- `WHATSAPP_WORKER_POLL_SECONDS`: intervalo de sondeo, con valor inicial de 2
  segundos y límites razonables.

La URL configurada en Evolution será:

`https://<dominio>/api/v1/integrations/evolution/webhook`

La configuración del webhook de Evolution incluirá el encabezado personalizado
`X-Webhook-Secret`. Pulso comparará su valor en tiempo constante y nunca lo
incluirá en logs. No se aceptará el secreto mediante query string.

El estado de integración solo será `available: true` cuando URL, API key,
instancia y secreto estén configurados.

## Modelo de datos

### `whatsapp_links`

- `id`: UUID.
- `user_id`: FK única a `users`.
- `phone_e164`: teléfono normalizado, único.
- `provider_jid`: JID real observado en el evento de verificación.
- `instance_name`: instancia que verificó el vínculo.
- `verified_at`: fecha UTC.
- `revoked_at`: fecha UTC opcional.
- `created_at`: fecha UTC.

Solo un vínculo no revocado puede resolver mensajes para un usuario. Al
desvincular se conserva el registro revocado para auditoría, pero deja de
autorizar inmediatamente.

### `whatsapp_link_challenges`

- `id`: UUID.
- `user_id`: FK a `users` e índice.
- `phone_e164`: teléfono solicitado.
- `code_hash`: HMAC del código; nunca se guarda el código legible.
- `expires_at`: diez minutos después de crearlo.
- `attempts`: inicia en cero y admite como máximo cinco intentos.
- `consumed_at`: fecha UTC opcional.
- `created_at`: fecha UTC.

Crear un desafío invalida los desafíos pendientes anteriores del mismo usuario.
El código tendrá seis caracteres del alfabeto `ABCDEFGHJKLMNPQRSTUVWXYZ23456789`
para evitar caracteres ambiguos.

### `whatsapp_inbound_events`

- `id`: UUID interno.
- `provider_event_id`: ID de mensaje de Evolution, único junto con la instancia.
- `instance_name`: nombre de la instancia.
- `sender_jid`: identificador recibido, incluido `@lid` cuando corresponda.
- `sender_phone`: teléfono normalizado cuando el payload permita determinarlo.
- `message_text`: texto validado, con máximo de 10.000 caracteres.
- `status`: `pending`, `processing`, `processed`, `ignored` o `failed`.
- `attempts`: cantidad de reclamaciones.
- `next_attempt_at`: siguiente reintento UTC.
- `last_error`: código interno sin secretos ni contenido del mensaje.
- `received_at`, `processed_at`: fechas UTC.

La restricción única `(instance_name, provider_event_id)` garantiza
idempotencia. Se persistirá solo el subconjunto necesario del evento, no el
payload completo.

## API propia

### `POST /api/v1/whatsapp/link`

Requiere sesión verificada y CSRF. Recibe `{ "phone": "+573001234567" }`.
Normaliza y valida E.164, invalida desafíos anteriores y devuelve:

```json
{
  "status": "pending",
  "masked_phone": "+57******4567",
  "code": "AB23CD",
  "expires_at": "2026-09-16T20:10:00Z"
}
```

El código se muestra una única vez para que el usuario lo envíe desde WhatsApp.
No se devuelve mediante consultas posteriores.

### `GET /api/v1/whatsapp/status`

Requiere sesión verificada. Devuelve uno de `unlinked`, `pending` o `verified`,
el teléfono enmascarado y las fechas relevantes. No expone código, hash ni JID.

### `DELETE /api/v1/whatsapp/link`

Requiere sesión verificada y CSRF. Revoca el vínculo y consume desafíos
pendientes. Los mensajes posteriores del teléfono se ignoran.

### `POST /api/v1/integrations/evolution/webhook`

Es público únicamente para Evolution y exige el encabezado
`X-Webhook-Secret`. Compara el secreto en tiempo constante, limita el tamaño
aceptado y valida el JSON con un esquema permisivo para campos ajenos pero
estricto para los campos utilizados.

Solo acepta semánticamente:

- evento `messages.upsert`;
- instancia igual a `WHATSAPP_INSTANCE`;
- `data.key.fromMe == false`;
- conversación privada, nunca JID `@g.us` ni broadcasts/status;
- ID de mensaje no vacío;
- texto proveniente de `message.conversation` o
  `message.extendedTextMessage.text`.

Eventos válidos pero no procesables responden 200 con estado `ignored`. Eventos
duplicados responden 200 con estado `duplicate`. Autenticación inválida responde
401 y payload inválido responde 422.

## Vinculación

Cuando el worker recibe texto desde un remitente aún no vinculado:

1. Normaliza el número cuando el JID o los campos alternativos confiables del
   evento permiten obtenerlo.
2. Busca un desafío vigente para ese número.
3. Compara el texto completo, tras recortar espacios, con el HMAC del código.
4. En un fallo incrementa `attempts`; al quinto intento consume el desafío.
5. En un acierto crea o activa el vínculo, conserva el JID real, consume el
   desafío y envía una confirmación breve por WhatsApp.

Un teléfono verificado no puede vincularse simultáneamente con otro usuario. La
confirmación de vinculación es una respuesta directa al código entrante y cumple
la regla de no iniciar conversaciones.

Si Evolution entrega un JID `@lid`, Pulso conservará ese JID para responder. La
vinculación solo se completará si el evento también permite asociarlo de forma
inequívoca al teléfono solicitado; no se inferirá un teléfono cortando un LID.

## Conversación

Para un vínculo verificado, el worker:

1. Reclama transaccionalmente un evento pendiente.
2. Resuelve el usuario por vínculo activo e instancia.
3. Construye el contexto del chat con el historial existente.
4. Ejecuta el mismo coordinador y herramientas que usa el chat web.
5. Persiste `ChatMessage(role="user")` y `ChatMessage(role="assistant")`.
6. Envía `{ "number": <provider_jid>, "text": <respuesta> }` a
   `/message/sendText/{instance}` con encabezado `apikey`.
7. Marca el evento como procesado solo después de una respuesta HTTP exitosa de
   Evolution.

La lógica compartida del agente se extraerá de la ruta HTTP actual a un servicio
que recibe explícitamente `db`, `user` y `content`. Ni el webhook ni Evolution
pueden seleccionar un `user_id` directamente.

Aceptar una petición de envío no equivale a entrega o lectura. La aplicación no
mostrará ni registrará afirmaciones de entrega sin eventos de estado, que quedan
fuera de este alcance.

## Reintentos y concurrencia

El worker realizará como máximo tres intentos por evento, con esperas de 30 y
120 segundos después de los dos primeros fallos. Los errores de Groq y de red o
5xx de Evolution son reintentables. Los errores permanentes de validación, un
remitente no autorizado y respuestas 4xx de Evolution quedan como `ignored` o
`failed` según corresponda.

Antes de reintentar un evento cuya solicitud a Evolution pudo haber llegado pero
cuya respuesta se perdió, se marcará `failed` con resultado incierto en lugar de
reenviar automáticamente. Este incremento prioriza no duplicar respuestas.

El reclamo utilizará las capacidades de bloqueo disponibles en PostgreSQL. Las
pruebas SQLite ejecutarán un solo worker. Un evento abandonado en `processing`
podrá recuperarse después de un umbral configurable interno de cinco minutos.

## Seguridad y privacidad

- API keys, secreto de webhook y códigos nunca se registran.
- Los teléfonos se enmascaran en respuestas y logs.
- El webhook no confía en `user_id`, correo ni identidad declarados en el JSON.
- Se ignoran mensajes propios, grupos, broadcasts y remitentes no vinculados,
  excepto códigos que coincidan con desafíos vigentes.
- El contenido se limita a 10.000 caracteres y el cuerpo HTTP tendrá un límite
  conservador.
- La configuración de producción rechazará flags de correo de desarrollo y
  secretos insuficientes; se corregirá la regresión existente de configuración.
- HTTPS es obligatorio en el despliegue público.

## Interfaz web

La vista de Configuración mostrará:

- campo de teléfono con indicativo internacional;
- acción “Generar código”;
- código visible una sola vez y explicación para enviarlo al número emisor;
- vencimiento y posibilidad de generar un código nuevo;
- estado pendiente, verificado o no vinculado;
- teléfono enmascarado y acción de desvinculación.

La interfaz no afirmará que el canal está conectado hasta que el código llegue
por el webhook y el vínculo esté verificado.

## Despliegue

El backend y el nuevo worker usarán la misma imagen. Compose añadirá un servicio
`whatsapp-worker` con el comando `python -m app.whatsapp_worker run`, las mismas
variables y la misma base PostgreSQL que la API. Evolution permanece externo a
este repositorio.

La documentación de Dokploy indicará las nuevas variables, la URL del webhook,
el encabezado personalizado `X-Webhook-Secret` y el evento `MESSAGES_UPSERT` que
debe habilitarse.

## Pruebas y criterios de aceptación

Backend:

- valida y normaliza E.164;
- genera códigos no ambiguos y guarda solo su hash;
- consume códigos correctos y rechaza vencidos, incorrectos o agotados;
- impide que un teléfono pertenezca a dos usuarios activos;
- autentica el webhook y filtra instancia, `fromMe`, grupos y tipos no textuales;
- deduplica por instancia e ID;
- conserva y utiliza el JID real, incluido `@lid` cuando esté asociado de forma
  segura;
- responde únicamente a vínculos activos;
- reutiliza el agente con aislamiento por usuario;
- clasifica fallos y aplica la política de reintentos;
- rechaza flags de desarrollo en configuración de producción.

Frontend:

- muestra estados de carga, error, pendiente, verificado y no vinculado;
- solo muestra el código en la respuesta de creación;
- enmascara el teléfono consultado;
- envía CSRF al crear o borrar vínculos.

Integración:

1. Un usuario autenticado solicita un código.
2. Un fixture de `messages.upsert` desde el teléfono solicitado verifica el
   vínculo y produce una confirmación saliente simulada.
3. Un segundo mensaje genera una respuesta del agente simulada y una sola
   llamada a Evolution.
4. Repetir el mismo evento no genera otra respuesta.
5. Un mensaje de otro número no consulta Groq ni envía texto.

La funcionalidad se considera terminada cuando todas las pruebas backend y
frontend pasan, la compilación de producción termina correctamente y el flujo
integrado anterior pasa con Evolution y Groq simulados. La verificación real con
credenciales se documentará como paso de despliegue y no expondrá secretos.

## Referencias del proveedor

- Evolution API 2.3.7 publica `MESSAGES_UPSERT` como evento de recepción y
  documenta webhooks por evento.
- El endpoint de texto de Evolution v2 es
  `POST /message/sendText/{instance}` y la versión 2.3.7 valida el cuerpo moderno
  con `number` y `text`.
- El adaptador se mantendrá aislado para ajustar diferencias de payload sin
  acoplarlas al servicio de conversación.
