from .conftest import register


def test_task_crud_and_analytics(client, registered, csrf_headers):
    created = client.post(
        "/api/v1/tasks",
        headers=csrf_headers,
        json={"title": "Entregar informe", "description": "Antes del viernes", "priority": "high"},
    )
    assert created.status_code == 201, created.text
    task = created.json()
    assert set(task) == {
        "id", "title", "description", "priority", "status", "created_at", "completed_at"
    }
    assert task["status"] == "pending"

    listed = client.get("/api/v1/tasks")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [task["id"]]

    completed = client.patch(
        f"/api/v1/tasks/{task['id']}", headers=csrf_headers, json={"status": "completed"}
    )
    assert completed.status_code == 200
    assert completed.json()["completed_at"] is not None

    summary = client.get("/api/v1/analytics/summary")
    assert summary.json() == {
        "total_tasks": 1,
        "pending_tasks": 0,
        "completed_tasks": 1,
        "completion_rate": 100.0,
    }


def test_tasks_are_isolated_by_user(client, registered, csrf_headers):
    own = client.post(
        "/api/v1/tasks", headers=csrf_headers, json={"title": "Private", "priority": "low"}
    ).json()
    first_csrf = registered["csrf_token"]
    client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": first_csrf})

    second = register(client, "grace@example.com").json()
    second_headers = {"X-CSRF-Token": second["csrf_token"]}
    assert client.get("/api/v1/tasks").json() == []
    assert client.patch(
        f"/api/v1/tasks/{own['id']}", headers=second_headers, json={"status": "completed"}
    ).status_code == 404


def test_preferences_are_validated(client, registered, csrf_headers):
    updated = client.patch(
        "/api/v1/me/preferences",
        headers=csrf_headers,
        json={"timezone": "Europe/Madrid", "response_mode": "both"},
    )
    assert updated.status_code == 200
    assert updated.json() == {"timezone": "Europe/Madrid", "response_mode": "both"}
    assert client.patch(
        "/api/v1/me/preferences", headers=csrf_headers, json={"timezone": "Mars/Olympus"}
    ).status_code == 422
    for invalid in ({"timezone": ""}, {"timezone": None}, {"response_mode": None}):
        assert client.patch(
            "/api/v1/me/preferences", headers=csrf_headers, json=invalid
        ).status_code == 422


def test_task_patch_rejects_null_nonnullable_fields(client, registered, csrf_headers):
    task = client.post(
        "/api/v1/tasks", headers=csrf_headers, json={"title": "Keep valid", "priority": "low"}
    ).json()
    for field in ("title", "priority", "status"):
        response = client.patch(
            f"/api/v1/tasks/{task['id']}", headers=csrf_headers, json={field: None}
        )
        assert response.status_code == 422, (field, response.text)
