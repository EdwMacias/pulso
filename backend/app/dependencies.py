import hmac
from datetime import UTC, datetime

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models import LoginSession, User
from .security import hash_token


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def get_login_session(
    request: Request, db: Session = Depends(get_db)
) -> LoginSession:
    session = request.cookies.get(get_settings().session_cookie_name)
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    login_session = db.scalar(
        select(LoginSession).where(LoginSession.token_hash == hash_token(session))
    )
    if (
        login_session is None
        or login_session.revoked_at is not None
        or _as_utc(login_session.expires_at) <= datetime.now(UTC)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    return login_session


def current_user(login_session: LoginSession = Depends(get_login_session)) -> User:
    user = login_session.user
    if user.email_verified_at is None:
        raise HTTPException(status_code=403, detail="Email verification required")
    return user


def require_csrf_session(
    request: Request,
    login_session: LoginSession = Depends(get_login_session),
    x_csrf_token: str | None = Header(default=None),
) -> User:
    csrf_token = request.cookies.get(get_settings().csrf_cookie_name)
    if (
        not x_csrf_token
        or not csrf_token
        or not hmac.compare_digest(x_csrf_token, csrf_token)
        or not hmac.compare_digest(login_session.csrf_hash, hash_token(x_csrf_token))
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")
    return login_session.user


def require_csrf(user: User = Depends(require_csrf_session)) -> User:
    if user.email_verified_at is None:
        raise HTTPException(status_code=403, detail="Email verification required")
    return user
