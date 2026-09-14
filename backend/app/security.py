import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Response
from sqlalchemy.orm import Session

from .config import get_settings
from .models import AuthToken, LoginSession, User


password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def hash_token(token: str) -> str:
    secret = get_settings().secret_key.encode()
    return hmac.new(secret, token.encode(), hashlib.sha256).hexdigest()


def create_login_session(db: Session, user: User) -> tuple[str, str]:
    settings = get_settings()
    token = secrets.token_urlsafe(48)
    csrf = secrets.token_urlsafe(32)
    db.add(
        LoginSession(
            user_id=user.id,
            token_hash=hash_token(token),
            csrf_hash=hash_token(csrf),
            expires_at=datetime.now(UTC) + timedelta(hours=settings.session_ttl_hours),
        )
    )
    db.commit()
    return token, csrf


def set_auth_cookies(response: Response, token: str, csrf: str) -> None:
    settings = get_settings()
    max_age = settings.session_ttl_hours * 3600
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf,
        max_age=max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")


def create_auth_token(db: Session, user: User, purpose: str, hours: int) -> str:
    raw = secrets.token_urlsafe(48)
    db.add(
        AuthToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=hash_token(raw),
            expires_at=datetime.now(UTC) + timedelta(hours=hours),
        )
    )
    db.commit()
    return raw

