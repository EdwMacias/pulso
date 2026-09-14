from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .dependencies import current_user
from .models import NotificationOutbox, Reminder, ReminderOccurrence, Task, User
from .schemas import NotificationOut


router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
def list_notifications(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(NotificationOutbox, Task.title)
        .join(ReminderOccurrence, ReminderOccurrence.id == NotificationOutbox.occurrence_id)
        .join(Reminder, Reminder.id == ReminderOccurrence.reminder_id)
        .join(Task, Task.id == Reminder.task_id)
        .where(Reminder.user_id == user.id)
        .order_by(NotificationOutbox.created_at.desc(), NotificationOutbox.id.desc())
    ).all()
    return [
        NotificationOut(
            id=event.id,
            title=title,
            content=f"Recordatorio: {title}",
            status="published" if event.published_at else "pending",
            created_at=event.created_at,
        )
        for event, title in rows
    ]
