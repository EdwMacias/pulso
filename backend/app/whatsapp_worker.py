import argparse
import hmac
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from .chat_service import ChatConfigurationError, ChatProviderError, run_chat_turn
from .config import get_settings
from .database import session_scope
from .evolution_client import EvolutionClient, EvolutionRejected, EvolutionUncertain
from .models import (
    User,
    WhatsAppInboundEvent,
    WhatsAppLink,
    WhatsAppLinkChallenge,
)
from .security import hash_token


CONFIRMATION_TEXT = (
    "Tu número quedó vinculado a Pulso. Ya puedes escribirle al asistente."
)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _claim_event(db: Session) -> WhatsAppInboundEvent | None:
    now = datetime.now(UTC)
    event = db.scalar(
        select(WhatsAppInboundEvent)
        .where(
            or_(
                and_(
                    WhatsAppInboundEvent.status == "pending",
                    or_(
                        WhatsAppInboundEvent.next_attempt_at.is_(None),
                        WhatsAppInboundEvent.next_attempt_at <= now,
                    ),
                ),
                and_(
                    WhatsAppInboundEvent.status == "processing",
                    WhatsAppInboundEvent.next_attempt_at <= now,
                ),
            )
        )
        .order_by(WhatsAppInboundEvent.received_at, WhatsAppInboundEvent.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if event is None:
        return None
    event.status = "processing"
    event.attempts += 1
    event.next_attempt_at = now + timedelta(minutes=5)
    db.commit()
    db.refresh(event)
    return event


def _finish(
    db: Session, event: WhatsAppInboundEvent, status: str, error: str | None = None
) -> None:
    event.status = status
    event.last_error = error
    event.next_attempt_at = None
    event.processed_at = datetime.now(UTC)
    db.commit()


def _mark_sending(db: Session, event: WhatsAppInboundEvent) -> None:
    event.status = "sending"
    event.next_attempt_at = None
    db.commit()


def _schedule_chat_retry(
    db: Session, event: WhatsAppInboundEvent, error: str
) -> None:
    if event.attempts >= 3:
        _finish(db, event, "failed", error)
        return
    delay = 30 if event.attempts == 1 else 120
    event.status = "pending"
    event.last_error = error
    event.next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay)
    event.processed_at = None
    db.commit()


def _find_active_link(
    db: Session, event: WhatsAppInboundEvent
) -> WhatsAppLink | None:
    if event.sender_phone is None:
        return None
    return db.scalar(
        select(WhatsAppLink).where(
            WhatsAppLink.phone_e164 == event.sender_phone,
            WhatsAppLink.instance_name == event.instance_name,
            WhatsAppLink.revoked_at.is_(None),
        )
    )


def _matching_challenge(
    db: Session, event: WhatsAppInboundEvent
) -> WhatsAppLinkChallenge | None:
    if event.sender_phone is None:
        return None
    return db.scalar(
        select(WhatsAppLinkChallenge)
        .where(
            WhatsAppLinkChallenge.phone_e164 == event.sender_phone,
            WhatsAppLinkChallenge.consumed_at.is_(None),
        )
        .order_by(WhatsAppLinkChallenge.created_at.desc())
    )


def _verify_challenge(
    db: Session,
    event: WhatsAppInboundEvent,
    challenge: WhatsAppLinkChallenge,
) -> WhatsAppLink | None:
    now = datetime.now(UTC)
    if _as_utc(challenge.expires_at) <= now or challenge.attempts >= 5:
        challenge.consumed_at = now
        db.commit()
        return None
    if not hmac.compare_digest(challenge.code_hash, hash_token(event.message_text.strip())):
        challenge.attempts += 1
        if challenge.attempts >= 5:
            challenge.consumed_at = now
        db.commit()
        return None

    phone_link = db.scalar(
        select(WhatsAppLink).where(WhatsAppLink.phone_e164 == challenge.phone_e164)
    )
    user_link = db.scalar(
        select(WhatsAppLink).where(WhatsAppLink.user_id == challenge.user_id)
    )
    if (
        phone_link is not None
        and phone_link.revoked_at is None
        and phone_link.user_id != challenge.user_id
    ):
        challenge.consumed_at = now
        db.commit()
        return None
    if phone_link is not None and user_link is not None and phone_link.id != user_link.id:
        challenge.consumed_at = now
        db.commit()
        return None
    link = phone_link or user_link
    if link is None:
        link = WhatsAppLink(user_id=challenge.user_id)
        db.add(link)
    link.phone_e164 = challenge.phone_e164
    link.provider_jid = event.sender_jid
    link.instance_name = event.instance_name
    link.verified_at = now
    link.revoked_at = None
    challenge.consumed_at = now
    event.status = "sending"
    event.next_attempt_at = None
    db.commit()
    db.refresh(link)
    return link


def process_next_event(db: Session, sender: EvolutionClient) -> bool:
    event = _claim_event(db)
    if event is None:
        return False
    try:
        link = _find_active_link(db, event)
        if link is not None:
            link.provider_jid = event.sender_jid
            user = db.get(User, link.user_id)
            if user is None:
                _finish(db, event, "failed", "linked_user_missing")
                return True
            _mark_sending(db, event)
            assistant = run_chat_turn(db, user, event.message_text)
            sender.send_text(event.sender_jid, assistant.content)
            _finish(db, event, "processed")
            return True

        challenge = _matching_challenge(db, event)
        if challenge is None:
            _finish(db, event, "ignored", "sender_not_authorized")
            return True
        link = _verify_challenge(db, event, challenge)
        if link is None:
            _finish(db, event, "ignored", "invalid_or_expired_code")
            return True
        sender.send_text(event.sender_jid, CONFIRMATION_TEXT)
        _finish(db, event, "processed")
    except (ChatConfigurationError, ChatProviderError):
        db.rollback()
        event = db.get(WhatsAppInboundEvent, event.id)
        _schedule_chat_retry(db, event, "groq_unavailable")
    except EvolutionRejected:
        db.rollback()
        event = db.get(WhatsAppInboundEvent, event.id)
        _finish(db, event, "failed", "evolution_rejected")
    except EvolutionUncertain:
        db.rollback()
        event = db.get(WhatsAppInboundEvent, event.id)
        _finish(db, event, "failed", "send_result_unknown")
    return True


def run_once(sender: EvolutionClient | None = None) -> bool:
    sender = sender or EvolutionClient()
    with session_scope() as db:
        return process_next_event(db, sender)


def main() -> None:
    parser = argparse.ArgumentParser(description="Process inbound WhatsApp events")
    parser.add_argument("mode", choices=("once", "run"))
    args = parser.parse_args()
    sender = EvolutionClient()
    if args.mode == "once":
        run_once(sender)
        return
    poll_seconds = get_settings().whatsapp_worker_poll_seconds
    while True:
        processed = run_once(sender)
        if not processed:
            time.sleep(poll_seconds)


if __name__ == "__main__":
    main()
