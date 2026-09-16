# WhatsApp Inbound Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir que un usuario verifique su teléfono y converse con el agente mediante mensajes entrantes de Evolution API 2.3.7, sin habilitar mensajes proactivos.

**Architecture:** FastAPI recibe y deduplica `messages.upsert` en una bandeja persistente; un worker independiente procesa verificaciones y conversaciones, reutiliza el servicio de chat y responde mediante un adaptador aislado de Evolution. Vue expone el registro, estado y revocación del vínculo.

**Tech Stack:** FastAPI, Pydantic Settings, SQLAlchemy 2, httpx, pytest, Vue 3, TypeScript, Vitest, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-16-whatsapp-inbound-agent-design.md`

## Global Constraints

- Evolution API debe mantenerse en la versión 2.3.7.
- Pulso solo responde como consecuencia de un mensaje entrante del usuario vinculado.
- Solo se admiten conversaciones privadas de texto; grupos, broadcasts, multimedia y mensajes `fromMe` se ignoran.
- Los secretos permanecen en el backend y el webhook exige `X-Webhook-Secret`.
- El teléfono se valida como E.164 y nunca se devuelve sin enmascarar después de crear el desafío.
- Cada evento se procesa como máximo una vez por `(instance_name, provider_event_id)`.
- No se añaden Redis, Celery, STT, TTS ni recordatorios salientes por WhatsApp.

---

### Task 1: Configuración segura de WhatsApp

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/tests/test_email.py`
- Modify: `backend/tests/test_chat.py`
- Modify: `backend/.env.example`

**Interfaces:**
- Produces: `Settings.whatsapp_instance: str | None`
- Produces: `Settings.whatsapp_webhook_secret: str | None`
- Produces: `Settings.whatsapp_worker_poll_seconds: int`
- Produces: `Settings.whatsapp_configured: bool`

- [ ] **Step 1: Repair and extend the failing configuration tests**

Separate the accidentally interleaved SMTP test in `test_email.py`, preserve its existing assertions, and add:

```python
def test_production_rejects_development_email_bypass(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "a-production-secret-that-is-long-enough")
    monkeypatch.setenv("COOKIE_SECURE", "true")
    monkeypatch.setenv("DEV_AUTO_VERIFY_EMAIL", "true")
    with pytest.raises(ValidationError, match="development email flags"):
        Settings()


def test_whatsapp_is_available_only_with_complete_configuration(
    client, registered, monkeypatch
):
    for name, value in {
        "WHATSAPP_API_URL": "https://evolution.example.test",
        "WHATSAPP_API_KEY": "api-key",
        "WHATSAPP_INSTANCE": "pulso",
        "WHATSAPP_WEBHOOK_SECRET": "webhook-secret-at-least-32-characters",
    }.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    body = client.get("/api/v1/integrations/status").json()
    assert body["whatsapp"] == {"configured": True, "available": True}
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `cd backend && .venv/bin/pytest tests/test_email.py tests/test_chat.py -q`

Expected: the production flag and complete WhatsApp availability assertions fail.

- [ ] **Step 3: Implement cross-field settings validation**

Use `@model_validator(mode="after")` so validation does not depend on field order:

```python
@model_validator(mode="after")
def validate_environment_safety(self):
    if self.environment == "production" and (
        self.dev_auto_verify_email or self.dev_outbox_enabled
    ):
        raise ValueError("development email flags are forbidden in production")
    return self

@property
def whatsapp_configured(self) -> bool:
    return bool(
        self.whatsapp_api_url
        and self.whatsapp_api_key
        and self.whatsapp_instance
        and self.whatsapp_webhook_secret
    )
```

Add the new settings, strip a trailing slash from `WHATSAPP_API_URL`, validate the webhook secret length when set, and make `integrations_status` use `whatsapp_configured` for both `configured` and `available`.

- [ ] **Step 4: Verify GREEN**

Run: `cd backend && .venv/bin/pytest tests/test_email.py tests/test_chat.py -q`

Expected: all focused tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/tests/test_email.py backend/tests/test_chat.py backend/.env.example
git commit -m "backend: validate WhatsApp configuration"
```

### Task 2: Persistencia y API de vinculación

**Files:**
- Create: `backend/app/whatsapp.py`
- Create: `backend/tests/test_whatsapp_link.py`
- Modify: `backend/app/models.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Produces: `normalize_e164(value: str) -> str`
- Produces: `mask_phone(value: str) -> str`
- Produces: `create_link_challenge(db: Session, user: User, phone: str) -> tuple[WhatsAppLinkChallenge, str]`
- Produces: `GET|POST|DELETE /api/v1/whatsapp/...`

- [ ] **Step 1: Write API tests first**

Cover invalid national numbers, successful creation, hash-only persistence, one-time code visibility, masked status, replacement of a pending challenge, CSRF, and revocation:

```python
def test_create_link_challenge_stores_only_hash(client, registered, csrf_headers):
    response = client.post(
        "/api/v1/whatsapp/link",
        headers=csrf_headers,
        json={"phone": "+573001234567"},
    )
    assert response.status_code == 201
    body = response.json()
    assert len(body["code"]) == 6
    assert body["masked_phone"] == "+57******4567"
    with session_scope() as db:
        row = db.query(WhatsAppLinkChallenge).one()
        assert row.phone_e164 == "+573001234567"
        assert row.code_hash != body["code"]
```

- [ ] **Step 2: Run the new test module and verify RED**

Run: `cd backend && .venv/bin/pytest tests/test_whatsapp_link.py -q`

Expected: collection or route failures because the models and endpoints do not exist.

- [ ] **Step 3: Add the models and schemas**

Implement `WhatsAppLink`, `WhatsAppLinkChallenge`, and `WhatsAppInboundEvent` exactly as specified. Reuse `uuid_str()` and `utc_now()`. Add enums/schema models:

```python
class WhatsAppLinkIn(BaseModel):
    phone: str = Field(min_length=8, max_length=16)

class WhatsAppLinkStatus(BaseModel):
    status: Literal["unlinked", "pending", "verified"]
    masked_phone: str | None = None
    expires_at: datetime | None = None
    verified_at: datetime | None = None
```

- [ ] **Step 4: Implement the linking service and routes**

Use `hash_token()` for the code HMAC and `secrets.choice()` with the approved alphabet. Expose an `APIRouter(prefix="/whatsapp")`; all user mutations require `require_csrf`, status requires `current_user`. Return the raw code only from the successful POST response.

- [ ] **Step 5: Verify GREEN and regression tests**

Run: `cd backend && .venv/bin/pytest tests/test_whatsapp_link.py tests/test_auth.py -q`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/whatsapp.py backend/app/models.py backend/app/schemas.py backend/app/main.py backend/tests/test_whatsapp_link.py
git commit -m "backend: add WhatsApp number linking"
```

### Task 3: Webhook autenticado e idempotente

**Files:**
- Create: `backend/app/evolution.py`
- Create: `backend/tests/test_evolution_webhook.py`
- Modify: `backend/app/integrations.py`
- Modify: `backend/app/schemas.py`

**Interfaces:**
- Produces: `parse_inbound_event(payload: dict) -> ParsedInbound | None`
- Produces: `POST /api/v1/integrations/evolution/webhook`
- Produces: persisted `WhatsAppInboundEvent(status="pending")`

- [ ] **Step 1: Write failing webhook behavior tests**

Use realistic `messages.upsert` fixtures and test missing/wrong secret, wrong instance, `fromMe`, `@g.us`, status broadcast, plain and extended text, malformed payload, and duplicate ID:

```python
def test_webhook_persists_inbound_text_once(client, configured_whatsapp, inbound_payload):
    first = client.post(
        "/api/v1/integrations/evolution/webhook",
        headers={"X-Webhook-Secret": configured_whatsapp.secret},
        json=inbound_payload,
    )
    second = client.post(
        "/api/v1/integrations/evolution/webhook",
        headers={"X-Webhook-Secret": configured_whatsapp.secret},
        json=inbound_payload,
    )
    assert first.json() == {"status": "accepted"}
    assert second.json() == {"status": "duplicate"}
```

- [ ] **Step 2: Verify RED**

Run: `cd backend && .venv/bin/pytest tests/test_evolution_webhook.py -q`

Expected: 404 because the webhook does not exist.

- [ ] **Step 3: Implement provider parsing and webhook persistence**

Create a frozen dataclass:

```python
@dataclass(frozen=True)
class ParsedInbound:
    event_id: str
    instance_name: str
    sender_jid: str
    sender_phone: str | None
    text: str
```

Only derive `sender_phone` from `@s.whatsapp.net` or an explicit trusted alternate phone field that passes `normalize_e164`; never derive it from `@lid`. Compare the secret with `hmac.compare_digest`. Catch the unique-constraint `IntegrityError`, roll back, and return `duplicate`.

- [ ] **Step 4: Verify GREEN**

Run: `cd backend && .venv/bin/pytest tests/test_evolution_webhook.py -q`

Expected: all webhook tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/evolution.py backend/app/integrations.py backend/app/schemas.py backend/tests/test_evolution_webhook.py
git commit -m "backend: accept Evolution inbound webhooks"
```

### Task 4: Servicio compartido del agente y cliente Evolution

**Files:**
- Create: `backend/app/chat_service.py`
- Create: `backend/app/evolution_client.py`
- Create: `backend/tests/test_evolution_client.py`
- Modify: `backend/app/chat.py`
- Modify: `backend/tests/test_chat.py`

**Interfaces:**
- Produces: `run_chat_turn(db: Session, user: User, content: str) -> ChatMessage`
- Produces: `EvolutionClient.send_text(recipient_jid: str, text: str) -> str`
- Consumes: settings URL, key and instance.

- [ ] **Step 1: Write service and HTTP-contract tests**

First prove that the web route delegates to one transaction-safe service and that the Evolution request uses the v2.3.7 payload:

```python
def test_send_text_uses_instance_apikey_and_modern_payload(monkeypatch):
    captured = {}
    def handler(request: httpx.Request):
        captured["request"] = request
        return httpx.Response(201, json={"key": {"id": "out-1"}})
    client = EvolutionClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert client.send_text("573001234567@s.whatsapp.net", "Hola") == "out-1"
    assert json.loads(captured["request"].content) == {
        "number": "573001234567@s.whatsapp.net", "text": "Hola"
    }
```

- [ ] **Step 2: Verify RED**

Run: `cd backend && .venv/bin/pytest tests/test_chat.py tests/test_evolution_client.py -q`

Expected: import failures for the missing service/client.

- [ ] **Step 3: Extract chat orchestration without changing behavior**

Move tool definitions, `_tool_loop`, and `_execute_tool` into `chat_service.py`. Implement `run_chat_turn` to validate Groq configuration, build history, call the tool loop, persist both messages and commit. Keep the HTTP route responsible only for translating provider failures to the existing 503 response.

- [ ] **Step 4: Implement the Evolution client**

Use `httpx.Client(timeout=15)` and URL-encode the instance path. Send `apikey` and JSON `{number, text}`. Define explicit `EvolutionRejected` for 4xx and `EvolutionUncertain` for network/timeouts/5xx so the worker can choose whether retrying could duplicate a message.

- [ ] **Step 5: Verify GREEN and all chat regressions**

Run: `cd backend && .venv/bin/pytest tests/test_chat.py tests/test_evolution_client.py -q`

Expected: all tests pass, including rollback after a failed Groq tool loop.

- [ ] **Step 6: Commit**

```bash
git add backend/app/chat.py backend/app/chat_service.py backend/app/evolution_client.py backend/tests/test_chat.py backend/tests/test_evolution_client.py
git commit -m "backend: share agent service with WhatsApp"
```

### Task 5: Worker de verificación y conversación

**Files:**
- Create: `backend/app/whatsapp_worker.py`
- Create: `backend/tests/test_whatsapp_worker.py`

**Interfaces:**
- Produces: `process_next_event(db: Session, sender: EvolutionClient) -> bool`
- Produces: CLI `python -m app.whatsapp_worker once|run`
- Consumes: link/challenge models, `run_chat_turn`, and `EvolutionClient.send_text`.

- [ ] **Step 1: Write worker tests for every state transition**

Cover correct, incorrect, expired, exhausted and duplicate codes; unauthorized senders; verified conversation; `@lid` preservation; Groq rollback; permanent Evolution rejection; and uncertain send outcome:

```python
def test_verified_sender_runs_agent_and_replies_once(db, linked_event, fake_sender, monkeypatch):
    monkeypatch.setattr(
        "app.whatsapp_worker.run_chat_turn",
        lambda db, user, content: ChatMessage(user_id=user.id, role="assistant", content="Respuesta"),
    )
    assert process_next_event(db, fake_sender) is True
    assert fake_sender.calls == [(linked_event.sender_jid, "Respuesta")]
    assert linked_event.status == "processed"
    assert process_next_event(db, fake_sender) is False
```

- [ ] **Step 2: Verify RED**

Run: `cd backend && .venv/bin/pytest tests/test_whatsapp_worker.py -q`

Expected: import failure for `app.whatsapp_worker`.

- [ ] **Step 3: Implement claim, verification and conversation processing**

Claim the oldest eligible event, recovering `processing` rows older than five minutes. For a challenge success, upsert the user's link, consume the challenge, and send a direct confirmation. For a linked sender, call `run_chat_turn` and send its response. Mark ignored senders without invoking Groq.

- [ ] **Step 4: Implement deterministic failure policy and CLI**

`EvolutionRejected` becomes `failed`; `EvolutionUncertain` becomes `failed` with `last_error="send_result_unknown"` and is never automatically resent. Groq failures retry after 30 and 120 seconds up to three attempts. Implement `once` for one polling pass and `run` for a loop using the configured interval.

- [ ] **Step 5: Verify GREEN and backend suite**

Run: `cd backend && .venv/bin/pytest tests/test_whatsapp_worker.py -q`

Then: `cd backend && .venv/bin/pytest -q`

Expected: all backend tests pass with no configuration regression.

- [ ] **Step 6: Commit**

```bash
git add backend/app/whatsapp_worker.py backend/tests/test_whatsapp_worker.py
git commit -m "backend: process inbound WhatsApp conversations"
```

### Task 6: Interfaz de vinculación

**Files:**
- Create: `frontend/src/services/whatsapp.ts`
- Create: `frontend/tests/whatsapp.test.ts`
- Modify: `frontend/src/views/WorkspaceView.vue`
- Modify: `frontend/src/style.css`

**Interfaces:**
- Produces: `getWhatsAppStatus()`, `startWhatsAppLink(phone)`, `unlinkWhatsApp()`.
- Consumes: `/whatsapp/status` and `/whatsapp/link`.

- [ ] **Step 1: Add failing API-service tests**

```typescript
it('crea y elimina un vínculo usando el cliente autenticado', async () => {
  const request = vi.spyOn(apiModule, 'api')
    .mockResolvedValueOnce({ status: 'pending', masked_phone: '+57******4567', code: 'AB23CD' })
    .mockResolvedValueOnce(undefined)
  await startWhatsAppLink('+573001234567')
  await unlinkWhatsApp()
  expect(request).toHaveBeenNthCalledWith(1, '/whatsapp/link', expect.objectContaining({ method: 'POST' }))
  expect(request).toHaveBeenNthCalledWith(2, '/whatsapp/link', { method: 'DELETE' })
})
```

- [ ] **Step 2: Verify RED**

Run: `cd frontend && npm run test:unit`

Expected: module import failure for `services/whatsapp`.

- [ ] **Step 3: Implement typed service and settings UI**

Add exact response types and use the shared `api()` client. In `WorkspaceView.vue`, load status with the other settings data, render phone entry, one-time code, expiry, verified state and unlink action. Poll status only while the settings route is visible and status is `pending`; clear the interval on route change/unmount. Replace “Transporte pendiente de implementar” with truthful configured/linked states.

- [ ] **Step 4: Verify GREEN and build**

Run: `cd frontend && npm run test:unit`

Then: `cd frontend && npm run build`

Expected: all Vitest tests and Vue TypeScript compilation pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/services/whatsapp.ts frontend/tests/whatsapp.test.ts frontend/src/views/WorkspaceView.vue frontend/src/style.css
git commit -m "frontend: add WhatsApp linking settings"
```

### Task 7: Contenedores, documentación y verificación integrada

**Files:**
- Modify: `.env.example`
- Modify: `infra/compose.yaml`
- Modify: `infra/compose.dokploy.yaml`
- Modify: `docs/dokploy.md`
- Modify: `README.md`
- Create: `backend/tests/test_whatsapp_flow.py`

**Interfaces:**
- Produces: Compose service `whatsapp-worker`.
- Produces: documented Evolution webhook configuration.

- [ ] **Step 1: Write the integrated backend flow test**

Create a user challenge, submit a verification event, run one worker pass, submit a normal inbound event, run another pass, and replay the same event. Stub only Groq and the outbound HTTP boundary; assert one confirmation, one agent response and no duplicate send.

- [ ] **Step 2: Verify RED against the complete flow**

Run: `cd backend && .venv/bin/pytest tests/test_whatsapp_flow.py -q`

Expected: failure until the test fixtures and final integration seams are wired.

- [ ] **Step 3: Add Compose and environment configuration**

Add the four required variables and poll interval to the shared backend environment. Add:

```yaml
  whatsapp-worker:
    build: ../backend
    command: [python, -m, app.whatsapp_worker, run]
    environment: *backend_env
    depends_on:
      api: { condition: service_healthy }
    restart: unless-stopped
```

Use the equivalent build context in `compose.dokploy.yaml`.

- [ ] **Step 4: Update operating documentation**

Document how to configure `POST /webhook/set/{instance}` with the Pulso HTTPS URL, custom `X-Webhook-Secret` header, `webhook_by_events: false`, and only `MESSAGES_UPSERT`. State that the worker responds only to linked inbound private text and that Evolution acceptance is not delivery confirmation.

- [ ] **Step 5: Verify the integrated flow and configuration rendering**

Run: `cd backend && .venv/bin/pytest tests/test_whatsapp_flow.py -q`

Run: `docker compose -f infra/compose.yaml config --quiet`

Expected: flow passes and Compose configuration is valid.

- [ ] **Step 6: Run the complete verification suite**

Run:

```bash
cd backend && .venv/bin/pytest -q
cd frontend && npm run test:unit
cd frontend && npm run build
E2E_BASE_URL=http://127.0.0.1:8097 npm run test:e2e
```

Expected: backend, frontend unit, production build and existing browser workflow all pass.

- [ ] **Step 7: Commit**

```bash
git add .env.example infra/compose.yaml infra/compose.dokploy.yaml docs/dokploy.md README.md backend/tests/test_whatsapp_flow.py
git commit -m "ops: deploy inbound WhatsApp worker"
```

