from datetime import UTC, datetime, timedelta
from types import SimpleNamespace


class FakeSender:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def send_text(self, jid, text):
        self.calls.append((jid, text))
        if self.error:
            raise self.error
        return f"out-{len(self.calls)}"


def add_event(phone="+573001234567", jid="573001234567@s.whatsapp.net", text="Hola"):
    from app.database import session_scope
    from app.models import WhatsAppInboundEvent

    with session_scope() as db:
        event = WhatsAppInboundEvent(
            provider_event_id=f"event-{text}-{jid}",
            instance_name="pulso",
            sender_jid=jid,
            sender_phone=phone,
            message_text=text,
        )
        db.add(event)
        db.flush()
        return event.id


def test_correct_code_verifies_phone_and_sends_direct_confirmation(
    client, registered, csrf_headers
):
    created = client.post(
        "/api/v1/whatsapp/link",
        headers=csrf_headers,
        json={"phone": "+573001234567"},
    ).json()
    event_id = add_event(text=created["code"])
    sender = FakeSender()

    from app.database import session_scope
    from app.models import WhatsAppInboundEvent, WhatsAppLink
    from app.whatsapp_worker import process_next_event

    with session_scope() as db:
        assert process_next_event(db, sender) is True
        event = db.get(WhatsAppInboundEvent, event_id)
        link = db.query(WhatsAppLink).one()
        assert event.status == "processed"
        assert link.user_id == registered["user"]["id"]
        assert link.phone_e164 == "+573001234567"
        assert link.provider_jid == "573001234567@s.whatsapp.net"
    assert sender.calls == [
        (
            "573001234567@s.whatsapp.net",
            "Tu número quedó vinculado a Pulso. Ya puedes escribirle al asistente.",
        )
    ]


def test_wrong_code_increments_attempts_without_reply(client, registered, csrf_headers):
    client.post(
        "/api/v1/whatsapp/link",
        headers=csrf_headers,
        json={"phone": "+573001234567"},
    )
    event_id = add_event(text="WRONG1")
    sender = FakeSender()

    from app.database import session_scope
    from app.models import WhatsAppInboundEvent, WhatsAppLinkChallenge
    from app.whatsapp_worker import process_next_event

    with session_scope() as db:
        assert process_next_event(db, sender) is True
        assert db.get(WhatsAppInboundEvent, event_id).status == "ignored"
        assert db.query(WhatsAppLinkChallenge).one().attempts == 1
    assert sender.calls == []


def test_unknown_sender_is_ignored_without_calling_agent(client, monkeypatch):
    event_id = add_event(phone="+573009999999", text="¿Qué tareas tengo?")
    sender = FakeSender()
    called = False

    def unexpected_chat(*_args):
        nonlocal called
        called = True

    monkeypatch.setattr("app.whatsapp_worker.run_chat_turn", unexpected_chat)
    from app.database import session_scope
    from app.models import WhatsAppInboundEvent
    from app.whatsapp_worker import process_next_event

    with session_scope() as db:
        assert process_next_event(db, sender) is True
        assert db.get(WhatsAppInboundEvent, event_id).status == "ignored"
    assert called is False
    assert sender.calls == []


def test_verified_sender_runs_agent_and_replies_to_actual_lid(
    client, registered, monkeypatch
):
    from app.database import session_scope
    from app.models import WhatsAppInboundEvent, WhatsAppLink

    with session_scope() as db:
        db.add(
            WhatsAppLink(
                user_id=registered["user"]["id"],
                phone_e164="+573001234567",
                provider_jid="573001234567@s.whatsapp.net",
                instance_name="pulso",
                verified_at=datetime.now(UTC),
            )
        )
    event_id = add_event(
        jid="123456789012345@lid", text="Muéstrame mis tareas"
    )
    sender = FakeSender()
    seen = {}

    def fake_chat(db, user, content):
        seen.update(user_id=user.id, content=content)
        return SimpleNamespace(content="No tienes tareas pendientes.")

    monkeypatch.setattr("app.whatsapp_worker.run_chat_turn", fake_chat)
    from app.whatsapp_worker import process_next_event

    with session_scope() as db:
        assert process_next_event(db, sender) is True
        assert db.get(WhatsAppInboundEvent, event_id).status == "processed"
        assert db.query(WhatsAppLink).one().provider_jid == "123456789012345@lid"
    assert seen == {
        "user_id": registered["user"]["id"],
        "content": "Muéstrame mis tareas",
    }
    assert sender.calls == [("123456789012345@lid", "No tienes tareas pendientes.")]


def test_groq_failure_is_scheduled_for_retry(client, registered, monkeypatch):
    from app.chat_service import ChatProviderError
    from app.database import session_scope
    from app.models import WhatsAppInboundEvent, WhatsAppLink

    with session_scope() as db:
        db.add(
            WhatsAppLink(
                user_id=registered["user"]["id"],
                phone_e164="+573001234567",
                provider_jid="573001234567@s.whatsapp.net",
                instance_name="pulso",
                verified_at=datetime.now(UTC),
            )
        )
    event_id = add_event(text="Hola de nuevo")

    def fail_chat(*_args):
        raise ChatProviderError("provider down")

    monkeypatch.setattr("app.whatsapp_worker.run_chat_turn", fail_chat)
    from app.whatsapp_worker import process_next_event

    with session_scope() as db:
        assert process_next_event(db, FakeSender()) is True
        event = db.get(WhatsAppInboundEvent, event_id)
        assert event.status == "pending"
        assert event.attempts == 1
        assert event.next_attempt_at is not None
        assert event.last_error == "groq_unavailable"


def test_uncertain_send_is_terminal_to_avoid_duplicate_reply(
    client, registered, monkeypatch
):
    from app.database import session_scope
    from app.evolution_client import EvolutionUncertain
    from app.models import WhatsAppInboundEvent, WhatsAppLink

    with session_scope() as db:
        db.add(
            WhatsAppLink(
                user_id=registered["user"]["id"],
                phone_e164="+573001234567",
                provider_jid="573001234567@s.whatsapp.net",
                instance_name="pulso",
                verified_at=datetime.now(UTC),
            )
        )
    event_id = add_event(text="Respuesta incierta")
    monkeypatch.setattr(
        "app.whatsapp_worker.run_chat_turn",
        lambda *_args: SimpleNamespace(content="Respuesta"),
    )
    sender = FakeSender(EvolutionUncertain("timeout"))
    from app.whatsapp_worker import process_next_event

    with session_scope() as db:
        assert process_next_event(db, sender) is True
        event = db.get(WhatsAppInboundEvent, event_id)
        assert event.status == "failed"
        assert event.last_error == "send_result_unknown"
        assert event.next_attempt_at is None


def test_claimed_old_event_is_not_immediately_claimed_by_another_worker(client):
    """A second worker must wait for the processing lease, not receipt time."""
    from app.database import session_scope
    from app.models import WhatsAppInboundEvent
    from app.whatsapp_worker import _claim_event

    with session_scope() as db:
        event = WhatsAppInboundEvent(
            provider_event_id="old-event",
            instance_name="pulso",
            sender_jid="573001234567@s.whatsapp.net",
            sender_phone="+573001234567",
            message_text="Hola",
            received_at=datetime.now(UTC) - timedelta(minutes=10),
        )
        db.add(event)

    with session_scope() as first_worker:
        claimed = _claim_event(first_worker)
        assert claimed is not None

    with session_scope() as second_worker:
        assert _claim_event(second_worker) is None
