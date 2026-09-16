from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .chat_service import ChatConfigurationError, ChatProviderError, run_chat_turn
from .database import get_db
from .dependencies import current_user, require_csrf
from .models import ChatMessage, User
from .schemas import ChatIn, ChatMessageOut


router = APIRouter(prefix="/chat/messages", tags=["chat"])


@router.get("", response_model=list[ChatMessageOut])
def list_messages(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(
        select(ChatMessage)
        .where(ChatMessage.user_id == user.id)
        .order_by(ChatMessage.created_at, ChatMessage.id)
    ).all()


@router.post("", response_model=ChatMessageOut)
def send_message(
    payload: ChatIn,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    try:
        return run_chat_turn(db, user, payload.content)
    except ChatConfigurationError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "groq_unavailable", "message": "Groq is not configured"},
        ) from exc
    except ChatProviderError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "groq_unavailable", "message": "Groq request failed"},
        ) from exc
