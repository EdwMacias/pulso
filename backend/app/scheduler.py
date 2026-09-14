import argparse
import json
import time
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import session_scope
from .models import NotificationOutbox, Reminder, ReminderOccurrence, Task


def _aware_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _next_occurrence(current: datetime, timezone: str, recurrence: str) -> datetime:
    local = _aware_utc(current).astimezone(ZoneInfo(timezone))
    days = 1 if recurrence == "daily" else 7
    return (local + timedelta(days=days)).astimezone(UTC)


def claim_due_reminders(db: Session, now: datetime | None = None) -> int:
    now = _aware_utc(now or datetime.now(UTC))
    statement = (
        select(Reminder)
        .where(Reminder.status == "active", Reminder.next_run_at <= now)
        .order_by(Reminder.next_run_at)
        .with_for_update(skip_locked=True)
    )
    reminders = db.scalars(statement).all()
    created = 0
    for reminder in reminders:
        scheduled_at = _aware_utc(reminder.next_run_at)
        exists = db.scalar(
            select(ReminderOccurrence.id).where(
                ReminderOccurrence.reminder_id == reminder.id,
                ReminderOccurrence.scheduled_at == scheduled_at,
            )
        )
        if exists is None:
            try:
                ZoneInfo(reminder.timezone)
                recurrence_valid = reminder.recurrence in {"none", "daily", "weekly"}
            except ZoneInfoNotFoundError:
                recurrence_valid = False
            if not recurrence_valid:
                db.add(
                    ReminderOccurrence(
                        reminder_id=reminder.id,
                        scheduled_at=scheduled_at,
                        status="skipped",
                    )
                )
                reminder.status = "cancelled"
                continue
            task = db.get(Task, reminder.task_id)
            should_skip = scheduled_at < now - timedelta(hours=1) or task is None or task.status != "pending"
            occurrence = ReminderOccurrence(
                reminder_id=reminder.id,
                scheduled_at=scheduled_at,
                status="skipped" if should_skip else "pending",
            )
            db.add(occurrence)
            db.flush()
            if not should_skip:
                db.add(
                    NotificationOutbox(
                        occurrence_id=occurrence.id,
                        payload=json.dumps(
                            {
                                "user_id": reminder.user_id,
                                "reminder_id": reminder.id,
                                "task_id": reminder.task_id,
                                "title": task.title,
                                "scheduled_at": scheduled_at.isoformat(),
                                "timezone": reminder.timezone,
                            }
                        ),
                    )
                )
                created += 1
            elif task is None or task.status != "pending":
                reminder.status = "cancelled"
        if reminder.recurrence == "none":
            reminder.status = "cancelled"
        else:
            reminder.next_run_at = _next_occurrence(
                scheduled_at, reminder.timezone, reminder.recurrence
            )
    db.commit()
    return created


def publish_local_outbox(db: Session) -> int:
    """Persistently claims events; stdout is the first-increment local delivery channel."""
    events = db.scalars(
        select(NotificationOutbox)
        .where(NotificationOutbox.published_at.is_(None))
        .order_by(NotificationOutbox.created_at)
        .with_for_update(skip_locked=True)
    ).all()
    for event in events:
        print(json.dumps({"published_event_id": event.id}), flush=True)
        event.published_at = datetime.now(UTC)
    db.commit()
    return len(events)


def run_once() -> tuple[int, int]:
    with session_scope() as db:
        claimed = claim_due_reminders(db)
    with session_scope() as db:
        published = publish_local_outbox(db)
    return claimed, published


def main() -> None:
    parser = argparse.ArgumentParser(description="Persistent reminder scheduler")
    parser.add_argument("command", choices=["once", "run"], nargs="?", default="run")
    args = parser.parse_args()
    if args.command == "once":
        run_once()
        return
    interval = get_settings().scheduler_poll_seconds
    while True:
        run_once()
        time.sleep(interval)


if __name__ == "__main__":
    main()
