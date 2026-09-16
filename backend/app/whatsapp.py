import re
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .dependencies import current_user, require_csrf
from .models import User, WhatsAppLink, WhatsAppLinkChallenge
from .schemas import WhatsAppLinkIn, WhatsAppLinkPending, WhatsAppLinkStatus
from .security import hash_token


router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
E164_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_e164(value: str) -> str:
    if not E164_PATTERN.fullmatch(value):
        raise ValueError("phone must use E.164 format")
    return value


def mask_phone(value: str) -> str:
    return f"{value[:3]}{'*' * max(0, len(value) - 7)}{value[-4:]}"


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def create_link_challenge(
    db: Session, user: User, phone: str
) -> tuple[WhatsAppLinkChallenge, str]:
    phone = normalize_e164(phone)
    now = datetime.now(UTC)
    pending = db.scalars(
        select(WhatsAppLinkChallenge).where(
            WhatsAppLinkChallenge.user_id == user.id,
            WhatsAppLinkChallenge.consumed_at.is_(None),
        )
    ).all()
    for challenge in pending:
        challenge.consumed_at = now
    raw_code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
    challenge = WhatsAppLinkChallenge(
        user_id=user.id,
        phone_e164=phone,
        code_hash=hash_token(raw_code),
        expires_at=now + timedelta(minutes=10),
    )
    db.add(challenge)
    db.commit()
    db.refresh(challenge)
    return challenge, raw_code


@router.post("/link", response_model=WhatsAppLinkPending, status_code=status.HTTP_201_CREATED)
def start_link(
    payload: WhatsAppLinkIn,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    try:
        challenge, code = create_link_challenge(db, user, payload.phone)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return WhatsAppLinkPending(
        status="pending",
        masked_phone=mask_phone(challenge.phone_e164),
        code=code,
        expires_at=_as_utc(challenge.expires_at),
    )


@router.get("/status", response_model=WhatsAppLinkStatus)
def link_status(
    user: User = Depends(current_user), db: Session = Depends(get_db)
):
    link = db.scalar(
        select(WhatsAppLink).where(
            WhatsAppLink.user_id == user.id, WhatsAppLink.revoked_at.is_(None)
        )
    )
    if link is not None:
        return WhatsAppLinkStatus(
            status="verified",
            masked_phone=mask_phone(link.phone_e164),
            verified_at=link.verified_at,
        )
    challenge = db.scalar(
        select(WhatsAppLinkChallenge)
        .where(
            WhatsAppLinkChallenge.user_id == user.id,
            WhatsAppLinkChallenge.consumed_at.is_(None),
        )
        .order_by(WhatsAppLinkChallenge.created_at.desc())
    )
    if challenge is not None and _as_utc(challenge.expires_at) > datetime.now(UTC):
        return WhatsAppLinkStatus(
            status="pending",
            masked_phone=mask_phone(challenge.phone_e164),
            expires_at=_as_utc(challenge.expires_at),
        )
    return WhatsAppLinkStatus(status="unlinked")


@router.delete("/link", status_code=status.HTTP_204_NO_CONTENT)
def unlink(
    user: User = Depends(require_csrf), db: Session = Depends(get_db)
):
    now = datetime.now(UTC)
    links = db.scalars(
        select(WhatsAppLink).where(
            WhatsAppLink.user_id == user.id, WhatsAppLink.revoked_at.is_(None)
        )
    ).all()
    for link in links:
        link.revoked_at = now
    challenges = db.scalars(
        select(WhatsAppLinkChallenge).where(
            WhatsAppLinkChallenge.user_id == user.id,
            WhatsAppLinkChallenge.consumed_at.is_(None),
        )
    ).all()
    for challenge in challenges:
        challenge.consumed_at = now
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
