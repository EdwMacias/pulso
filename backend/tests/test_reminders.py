from datetime import UTC, datetime, timedelta


def _task(client, headers):
    return client.post(
        "/api/v1/tasks", headers=headers, json={"title": "Timed task", "priority": "medium"}
    ).json()


def test_reminder_contract_and_timezone_validation(client, registered, csrf_headers):
    task = _task(client, csrf_headers)
    scheduled = (datetime.now(UTC) + timedelta(hours=1)).replace(microsecond=0).isoformat()
    created = client.post(
        "/api/v1/reminders",
        headers=csrf_headers,
        json={
            "task_id": task["id"],
            "scheduled_at": scheduled,
            "timezone": "America/Bogota",
            "recurrence": "daily",
        },
    )
    assert created.status_code == 201, created.text
    reminder = created.json()
    assert set(reminder) == {"id", "task_id", "scheduled_at", "timezone", "recurrence", "status"}
    assert reminder["scheduled_at"].endswith("Z") or reminder["scheduled_at"].endswith("+00:00")
    assert client.get("/api/v1/reminders").json() == [reminder]

    invalid = client.post(
        "/api/v1/reminders",
        headers=csrf_headers,
        json={
            "task_id": task["id"],
            "scheduled_at": "2030-01-01T08:00:00",
            "timezone": "America/Bogota",
            "recurrence": "none",
        },
    )
    assert invalid.status_code == 422


def test_reminder_cannot_reference_another_users_task(client, registered, csrf_headers):
    from .conftest import register

    task = _task(client, csrf_headers)
    client.post("/api/v1/auth/logout", headers=csrf_headers)
    second = register(client, "second@example.com").json()
    scheduled = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    response = client.post(
        "/api/v1/reminders",
        headers={"X-CSRF-Token": second["csrf_token"]},
        json={
            "task_id": task["id"],
            "scheduled_at": scheduled,
            "timezone": "America/Bogota",
            "recurrence": "none",
        },
    )
    assert response.status_code == 404


def test_scheduler_claims_due_occurrence_once_and_advances_daily(client, registered, csrf_headers):
    task = _task(client, csrf_headers)
    due = (datetime.now(UTC) - timedelta(minutes=1)).replace(microsecond=0)
    reminder = client.post(
        "/api/v1/reminders",
        headers=csrf_headers,
        json={
            "task_id": task["id"],
            "scheduled_at": due.isoformat(),
            "timezone": "America/Bogota",
            "recurrence": "daily",
        },
    ).json()

    from app.database import session_scope
    from app.scheduler import claim_due_reminders

    with session_scope() as db:
        assert claim_due_reminders(db, now=datetime.now(UTC)) == 1
    with session_scope() as db:
        assert claim_due_reminders(db, now=datetime.now(UTC)) == 0

    from app.models import NotificationOutbox, ReminderOccurrence

    with session_scope() as db:
        assert db.query(ReminderOccurrence).filter_by(reminder_id=reminder["id"]).count() == 1
        assert db.query(NotificationOutbox).count() == 1


def test_reminder_patch_rejects_null_or_empty_scheduler_fields(client, registered, csrf_headers):
    task = _task(client, csrf_headers)
    scheduled = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    reminder = client.post(
        "/api/v1/reminders",
        headers=csrf_headers,
        json={
            "task_id": task["id"],
            "scheduled_at": scheduled,
            "timezone": "America/Bogota",
            "recurrence": "none",
        },
    ).json()
    invalid_changes = [
        {"timezone": ""},
        {"timezone": None},
        {"scheduled_at": None},
        {"recurrence": None},
        {"status": None},
    ]
    for changes in invalid_changes:
        response = client.patch(
            f"/api/v1/reminders/{reminder['id']}", headers=csrf_headers, json=changes
        )
        assert response.status_code == 422, (changes, response.text)


def test_notifications_are_owner_scoped_and_scheduler_output_has_no_content(
    client, registered, csrf_headers, capsys
):
    task = _task(client, csrf_headers)
    due = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    client.post(
        "/api/v1/reminders",
        headers=csrf_headers,
        json={
            "task_id": task["id"],
            "scheduled_at": due,
            "timezone": "America/Bogota",
            "recurrence": "none",
        },
    )
    from app.database import session_scope
    from app.scheduler import claim_due_reminders, publish_local_outbox

    with session_scope() as db:
        claim_due_reminders(db)
    before_publish = client.get("/api/v1/notifications")
    assert before_publish.status_code == 200
    notification = before_publish.json()[0]
    assert set(notification) == {"id", "title", "content", "status", "created_at"}
    assert notification["title"] == "Timed task"
    assert notification["status"] == "pending"

    with session_scope() as db:
        publish_local_outbox(db)
    output = capsys.readouterr().out
    assert "Timed task" not in output
    assert registered["user"]["id"] not in output
    assert client.get("/api/v1/notifications").json()[0]["status"] == "published"


def test_scheduler_skips_very_late_or_completed_task_reminders(client, registered, csrf_headers):
    late_task = _task(client, csrf_headers)
    completed_task = _task(client, csrf_headers)
    client.patch(
        f"/api/v1/tasks/{completed_task['id']}",
        headers=csrf_headers,
        json={"status": "completed"},
    )
    for task_id, due in (
        (late_task["id"], datetime.now(UTC) - timedelta(hours=2)),
        (completed_task["id"], datetime.now(UTC) - timedelta(minutes=1)),
    ):
        client.post(
            "/api/v1/reminders",
            headers=csrf_headers,
            json={
                "task_id": task_id,
                "scheduled_at": due.isoformat(),
                "timezone": "America/Bogota",
                "recurrence": "none",
            },
        )

    from app.database import session_scope
    from app.models import NotificationOutbox, ReminderOccurrence
    from app.scheduler import claim_due_reminders

    with session_scope() as db:
        assert claim_due_reminders(db) == 0
    with session_scope() as db:
        assert db.query(ReminderOccurrence).filter_by(status="skipped").count() == 2
        assert db.query(NotificationOutbox).count() == 0


def test_scheduler_quarantines_legacy_invalid_timezone(client, registered, csrf_headers):
    task = _task(client, csrf_headers)
    from app.database import session_scope
    from app.models import Reminder
    from app.scheduler import claim_due_reminders

    with session_scope() as db:
        db.add(
            Reminder(
                user_id=registered["user"]["id"],
                task_id=task["id"],
                timezone="Invalid/Legacy",
                recurrence="daily",
                next_run_at=datetime.now(UTC) - timedelta(minutes=1),
            )
        )
    with session_scope() as db:
        assert claim_due_reminders(db) == 0
    with session_scope() as db:
        reminder = db.query(Reminder).filter_by(timezone="Invalid/Legacy").one()
        assert reminder.status == "cancelled"
