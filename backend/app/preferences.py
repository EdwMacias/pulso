from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .database import get_db
from .dependencies import current_user, require_csrf
from .models import User
from .schemas import PreferencesOut, PreferencesPatch


router = APIRouter(prefix="/me/preferences", tags=["preferences"])


@router.get("", response_model=PreferencesOut)
def get_preferences(user: User = Depends(current_user)):
    return PreferencesOut(timezone=user.timezone, response_mode=user.response_mode)


@router.patch("", response_model=PreferencesOut)
def patch_preferences(
    payload: PreferencesPatch,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    for key, value in payload.model_dump(exclude_unset=True, mode="json").items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return PreferencesOut(timezone=user.timezone, response_mode=user.response_mode)

