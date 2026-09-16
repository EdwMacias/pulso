import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .dependencies import current_user
from .evolution import parse_inbound_event
from .models import User, WhatsAppInboundEvent


router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("/status")
def integrations_status(_: User = Depends(current_user)):
    settings = get_settings()
    return {
        "groq": {"configured": bool(settings.groq_api_key)},
        "whatsapp": {
            "configured": settings.whatsapp_configured,
            "available": settings.whatsapp_configured,
        },
        "tts": {"configured": bool(settings.tts_api_key), "available": False},
    }


@router.post("/evolution/webhook")
def evolution_webhook(
    payload: dict,
    request: Request,
    x_webhook_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    expected_secret = settings.whatsapp_webhook_secret
    if (
        not expected_secret
        or not x_webhook_secret
        or not hmac.compare_digest(x_webhook_secret, expected_secret)
    ):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 256_000:
        raise HTTPException(status_code=413, detail="Webhook payload is too large")
    if not settings.whatsapp_instance:
        raise HTTPException(status_code=503, detail="WhatsApp is not configured")
    try:
        parsed = parse_inbound_event(payload, settings.whatsapp_instance)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if parsed is None:
        return {"status": "ignored"}
    db.add(
        WhatsAppInboundEvent(
            provider_event_id=parsed.event_id,
            instance_name=parsed.instance_name,
            sender_jid=parsed.sender_jid,
            sender_phone=parsed.sender_phone,
            message_text=parsed.text,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"status": "duplicate"}
    return {"status": "accepted"}
