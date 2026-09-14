from datetime import UTC

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .dependencies import current_user, require_csrf
from .models import Reminder, Task, User
from .schemas import ReminderCreate, ReminderOut, ReminderPatch


router = APIRouter(prefix="/reminders", tags=["reminders"])


def _out(reminder: Reminder) -> ReminderOut:
    scheduled_at = reminder.next_run_at
    if scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=UTC)
    return ReminderOut(
        id=reminder.id,
        task_id=reminder.task_id,
        scheduled_at=scheduled_at,
        timezone=reminder.timezone,
        recurrence=reminder.recurrence,
        status=reminder.status,
    )


@router.get("", response_model=list[ReminderOut])
def list_reminders(user: User = Depends(current_user), db: Session = Depends(get_db)):
    reminders = db.scalars(
        select(Reminder).where(Reminder.user_id == user.id).order_by(Reminder.next_run_at, Reminder.id)
    ).all()
    return [_out(reminder) for reminder in reminders]


@router.post("", response_model=ReminderOut, status_code=status.HTTP_201_CREATED)
def create_reminder(
    payload: ReminderCreate, user: User = Depends(require_csrf), db: Session = Depends(get_db)
):
    task = db.scalar(select(Task).where(Task.id == payload.task_id, Task.user_id == user.id))
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    reminder = Reminder(
        user_id=user.id,
        task_id=task.id,
        timezone=payload.timezone,
        recurrence=payload.recurrence.value,
        next_run_at=payload.scheduled_at,
    )
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    return _out(reminder)


@router.patch("/{reminder_id}", response_model=ReminderOut)
def patch_reminder(
    reminder_id: str,
    payload: ReminderPatch,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    reminder = db.scalar(
        select(Reminder).where(Reminder.id == reminder_id, Reminder.user_id == user.id)
    )
    if reminder is None:
        raise HTTPException(status_code=404, detail="Reminder not found")
    changes = payload.model_dump(exclude_unset=True)
    if "scheduled_at" in changes:
        changes["next_run_at"] = changes.pop("scheduled_at")
    for key, value in changes.items():
        setattr(reminder, key, value)
    db.commit()
    db.refresh(reminder)
    return _out(reminder)
