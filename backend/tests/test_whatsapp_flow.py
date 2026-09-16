from types import SimpleNamespace


def webhook_payload(message_id: str, text: str):
    return {
        "event": "messages.upsert",
        "instance": "pulso",
        "data": {
            "key": {
                "remoteJid": "573001234567@s.whatsapp.net",
                "fromMe": False,
                "id": message_id,
            },
            "message": {"conversation": text},
            "messageType": "conversation",
        },
        "sender": "573001234567@s.whatsapp.net",
    }


class RecordingSender:
    def __init__(self):
        self.calls = []

    def send_text(self, jid, text):
        self.calls.append((jid, text))
        return f"out-{len(self.calls)}"


def test_link_then_converse_from_inbound_messages_only(
    client, registered, csrf_headers, monkeypatch
):
    from app.config import get_settings

    for name, value in {
        "WHATSAPP_API_URL": "https://evolution.example.test",
        "WHATSAPP_API_KEY": "api-key",
        "WHATSAPP_INSTANCE": "pulso",
        "WHATSAPP_WEBHOOK_SECRET": "webhook-secret-at-least-32-characters",
        "GROQ_API_KEY": "groq-key",
    }.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()

    challenge = client.post(
        "/api/v1/whatsapp/link",
        headers=csrf_headers,
        json={"phone": "+573001234567"},
    ).json()
    webhook_headers = {
        "X-Webhook-Secret": "webhook-secret-at-least-32-characters"
    }
    verified_event = webhook_payload("verify-1", challenge["code"])
    assert client.post(
        "/api/v1/integrations/evolution/webhook",
        headers=webhook_headers,
        json=verified_event,
    ).json() == {"status": "accepted"}

    sender = RecordingSender()
    from app.database import session_scope
    from app.whatsapp_worker import process_next_event

    with session_scope() as db:
        assert process_next_event(db, sender) is True
    assert client.get("/api/v1/whatsapp/status").json()["status"] == "verified"

    class FakeGroq:
        def __init__(self, **_kwargs):
            message = SimpleNamespace(tool_calls=[], content="Tu agente está listo.")
            completion = SimpleNamespace(choices=[SimpleNamespace(message=message)])
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=lambda **_kwargs: completion)
            )

    monkeypatch.setattr("app.chat_service.Groq", FakeGroq)
    conversation_event = webhook_payload("conversation-1", "Hola, ¿estás ahí?")
    assert client.post(
        "/api/v1/integrations/evolution/webhook",
        headers=webhook_headers,
        json=conversation_event,
    ).json() == {"status": "accepted"}
    with session_scope() as db:
        assert process_next_event(db, sender) is True

    duplicate = client.post(
        "/api/v1/integrations/evolution/webhook",
        headers=webhook_headers,
        json=conversation_event,
    )
    assert duplicate.json() == {"status": "duplicate"}
    assert sender.calls == [
        (
            "573001234567@s.whatsapp.net",
            "Tu número quedó vinculado a Pulso. Ya puedes escribirle al asistente.",
        ),
        ("573001234567@s.whatsapp.net", "Tu agente está listo."),
    ]

    from app.models import ChatMessage, WhatsAppInboundEvent

    with session_scope() as db:
        assert db.query(ChatMessage).count() == 2
        assert db.query(WhatsAppInboundEvent).count() == 2
    get_settings.cache_clear()
