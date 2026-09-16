import copy

import pytest


@pytest.fixture()
def configured_whatsapp(monkeypatch):
    from app.config import get_settings

    values = {
        "WHATSAPP_API_URL": "https://evolution.example.test",
        "WHATSAPP_API_KEY": "api-key",
        "WHATSAPP_INSTANCE": "pulso",
        "WHATSAPP_WEBHOOK_SECRET": "webhook-secret-at-least-32-characters",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    yield values
    get_settings.cache_clear()


@pytest.fixture()
def inbound_payload():
    return {
        "event": "messages.upsert",
        "instance": "pulso",
        "data": {
            "key": {
                "remoteJid": "573001234567@s.whatsapp.net",
                "fromMe": False,
                "id": "message-1",
            },
            "pushName": "Ada",
            "message": {"conversation": "Hola Pulso"},
            "messageType": "conversation",
        },
        "sender": "573001234567@s.whatsapp.net",
    }


def post_webhook(client, configured_whatsapp, payload, secret=None):
    headers = {}
    if secret is not False:
        headers["X-Webhook-Secret"] = secret or configured_whatsapp["WHATSAPP_WEBHOOK_SECRET"]
    return client.post(
        "/api/v1/integrations/evolution/webhook", headers=headers, json=payload
    )


def test_webhook_requires_shared_secret(client, configured_whatsapp, inbound_payload):
    missing = post_webhook(client, configured_whatsapp, inbound_payload, secret=False)
    wrong = post_webhook(client, configured_whatsapp, inbound_payload, secret="x" * 32)
    assert missing.status_code == 401
    assert wrong.status_code == 401


def test_webhook_persists_inbound_text_once(client, configured_whatsapp, inbound_payload):
    first = post_webhook(client, configured_whatsapp, inbound_payload)
    second = post_webhook(client, configured_whatsapp, inbound_payload)

    assert first.status_code == 200
    assert first.json() == {"status": "accepted"}
    assert second.status_code == 200
    assert second.json() == {"status": "duplicate"}

    from app.database import session_scope
    from app.models import WhatsAppInboundEvent

    with session_scope() as db:
        row = db.query(WhatsAppInboundEvent).one()
        assert row.provider_event_id == "message-1"
        assert row.sender_jid == "573001234567@s.whatsapp.net"
        assert row.sender_phone == "+573001234567"
        assert row.message_text == "Hola Pulso"
        assert row.status == "pending"


def test_webhook_accepts_extended_text_and_preserves_lid(
    client, configured_whatsapp, inbound_payload
):
    payload = copy.deepcopy(inbound_payload)
    payload["data"]["key"]["id"] = "message-lid"
    payload["data"]["key"]["remoteJid"] = "123456789012345@lid"
    payload["data"]["message"] = {
        "extendedTextMessage": {"text": "Texto extendido"}
    }
    payload["sender"] = "573001234567@s.whatsapp.net"

    response = post_webhook(client, configured_whatsapp, payload)

    assert response.json() == {"status": "accepted"}
    from app.database import session_scope
    from app.models import WhatsAppInboundEvent

    with session_scope() as db:
        row = db.query(WhatsAppInboundEvent).one()
        assert row.sender_jid == "123456789012345@lid"
        assert row.sender_phone == "+573001234567"


@pytest.mark.parametrize(
    ("change", "value"),
    [
        ("from_me", True),
        ("remote_jid", "120363000000000@g.us"),
        ("remote_jid", "status@broadcast"),
        ("instance", "another-instance"),
        ("event", "messages.update"),
    ],
)
def test_webhook_ignores_non_processable_events(
    client, configured_whatsapp, inbound_payload, change, value
):
    payload = copy.deepcopy(inbound_payload)
    if change == "from_me":
        payload["data"]["key"]["fromMe"] = value
    elif change == "remote_jid":
        payload["data"]["key"]["remoteJid"] = value
    else:
        payload[change] = value

    response = post_webhook(client, configured_whatsapp, payload)

    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}


def test_webhook_rejects_malformed_messages_upsert(
    client, configured_whatsapp, inbound_payload
):
    payload = copy.deepcopy(inbound_payload)
    del payload["data"]["key"]["id"]

    response = post_webhook(client, configured_whatsapp, payload)

    assert response.status_code == 422
