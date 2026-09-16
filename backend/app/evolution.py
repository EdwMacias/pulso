from dataclasses import dataclass

from .whatsapp import normalize_e164


@dataclass(frozen=True)
class ParsedInbound:
    event_id: str
    instance_name: str
    sender_jid: str
    sender_phone: str | None
    text: str


def _phone_from_jid(value: object) -> str | None:
    if not isinstance(value, str) or not value.endswith("@s.whatsapp.net"):
        return None
    local_part = value.removesuffix("@s.whatsapp.net")
    try:
        return normalize_e164(f"+{local_part}")
    except ValueError:
        return None


def parse_inbound_event(payload: dict, expected_instance: str) -> ParsedInbound | None:
    if payload.get("event") != "messages.upsert":
        return None
    if payload.get("instance") != expected_instance:
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("messages.upsert data is required")
    key = data.get("key")
    if not isinstance(key, dict):
        raise ValueError("messages.upsert key is required")
    event_id = key.get("id")
    sender_jid = key.get("remoteJid")
    from_me = key.get("fromMe")
    if not isinstance(event_id, str) or not event_id.strip():
        raise ValueError("message id is required")
    if not isinstance(sender_jid, str) or not sender_jid:
        raise ValueError("sender JID is required")
    if not isinstance(from_me, bool):
        raise ValueError("fromMe is required")
    if from_me or sender_jid.endswith("@g.us") or sender_jid.endswith("@broadcast"):
        return None
    message = data.get("message")
    if not isinstance(message, dict):
        return None
    text = message.get("conversation")
    if not isinstance(text, str):
        extended = message.get("extendedTextMessage")
        text = extended.get("text") if isinstance(extended, dict) else None
    if not isinstance(text, str) or not text.strip():
        return None
    text = text.strip()
    if len(text) > 10_000:
        raise ValueError("message text is too long")
    sender_phone = _phone_from_jid(sender_jid) or _phone_from_jid(payload.get("sender"))
    return ParsedInbound(
        event_id=event_id,
        instance_name=expected_instance,
        sender_jid=sender_jid,
        sender_phone=sender_phone,
        text=text,
    )
