from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .dependencies import get_login_session, require_csrf_session
from .models import AuthToken, LoginSession, User
from .outbox import send_auth_email
from .schemas import (
    AuthResponse,
    EmailIn,
    LoginIn,
    MessageResponse,
    RegisterIn,
    RegisterResponse,
    ResetPasswordIn,
    TokenIn,
    UserOut,
)
from .security import (
    clear_auth_cookies,
    create_auth_token,
    create_login_session,
    hash_password,
    hash_token,
    set_auth_cookies,
    verify_password,
)


router = APIRouter(prefix="/auth", tags=["auth"])


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _deliver_token(db: Session, user: User, purpose: str, hours: int) -> None:
    token = create_auth_token(db, user, purpose, hours)
    try:
        send_auth_email(user.email, purpose, token)
    except RuntimeError as exc:
        db.execute(
            delete(AuthToken).where(
                AuthToken.token_hash == hash_token(token), AuthToken.purpose == purpose
            )
        )
        db.commit()
        raise HTTPException(status_code=503, detail="Email delivery is unavailable") from exc


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterIn, response: Response, db: Session = Depends(get_db)):
    settings = get_settings()
    if not settings.dev_auto_verify_email and not settings.email_delivery_configured:
        raise HTTPException(status_code=503, detail="Email delivery is unavailable")
    user = User(
        email=_normalize_email(str(payload.email)),
        password_hash=hash_password(payload.password),
        timezone=settings.default_timezone,
        email_verified_at=datetime.now(UTC) if settings.dev_auto_verify_email else None,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email is already registered")
    db.refresh(user)
    if user.email_verified_at is None:
        try:
            _deliver_token(db, user, "verify_email", 24)
        except HTTPException:
            db.delete(user)
            db.commit()
            raise
    token, csrf = create_login_session(db, user)
    set_auth_cookies(response, token, csrf)
    return RegisterResponse(
        user=UserOut.model_validate(user),
        csrf_token=csrf,
        verification_required=user.email_verified_at is None,
    )


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == _normalize_email(str(payload.email))))
    if user is None or not verify_password(user.password_hash, payload.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if user.email_verified_at is None:
        raise HTTPException(status_code=403, detail="Email verification required")
    token, csrf = create_login_session(db, user)
    set_auth_cookies(response, token, csrf)
    return AuthResponse(user=UserOut.model_validate(user), csrf_token=csrf)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    _: User = Depends(require_csrf_session),
    login_session: LoginSession = Depends(get_login_session),
    db: Session = Depends(get_db),
):
    login_session.revoked_at = datetime.now(UTC)
    db.commit()
    clear_auth_cookies(response)


@router.get("/me", response_model=UserOut)
def me(login_session: LoginSession = Depends(get_login_session)):
    return login_session.user


@router.post("/verify-email", response_model=MessageResponse)
def verify_email(payload: TokenIn, db: Session = Depends(get_db)):
    token = _valid_token(db, payload.token, "verify_email")
    token.user.email_verified_at = datetime.now(UTC)
    token.consumed_at = datetime.now(UTC)
    db.commit()
    return MessageResponse(message="Email verified")


@router.post("/forgot-password", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
def forgot_password(payload: EmailIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == _normalize_email(str(payload.email))))
    if user is not None:
        try:
            _deliver_token(db, user, "reset_password", 1)
        except HTTPException:
            # Keep the response indistinguishable from an unknown account.
            pass
    return MessageResponse(message="If the account exists, reset instructions will be sent")


@router.post(
    "/resend-verification", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED
)
def resend_verification(payload: EmailIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == _normalize_email(str(payload.email))))
    if user is not None and user.email_verified_at is None:
        try:
            _deliver_token(db, user, "verify_email", 24)
        except HTTPException:
            pass
    return MessageResponse(message="If verification is needed, instructions will be sent")


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(payload: ResetPasswordIn, db: Session = Depends(get_db)):
    token = _valid_token(db, payload.token, "reset_password")
    token.user.password_hash = hash_password(payload.password)
    token.consumed_at = datetime.now(UTC)
    db.execute(
        update(LoginSession)
        .where(LoginSession.user_id == token.user_id, LoginSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    db.commit()
    return MessageResponse(message="Password reset")


def _valid_token(db: Session, raw: str, purpose: str) -> AuthToken:
    token = db.scalar(
        select(AuthToken).where(
            AuthToken.token_hash == hash_token(raw),
            AuthToken.purpose == purpose,
            AuthToken.consumed_at.is_(None),
        )
    )
    expires = token.expires_at.replace(tzinfo=UTC) if token and token.expires_at.tzinfo is None else (token.expires_at if token else None)
    if token is None or expires <= datetime.now(UTC):
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    return token
