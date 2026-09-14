from pathlib import Path


def test_register_login_me_logout_and_csrf(client, registered, csrf_headers):
    assert registered["user"]["email"] == "ada@example.com"
    assert registered["verification_required"] is False
    assert client.cookies.get("session")
    assert client.cookies.get("csrf_token") == registered["csrf_token"]

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "ada@example.com"

    assert client.post("/api/v1/auth/logout").status_code == 403
    assert client.post("/api/v1/auth/logout", headers=csrf_headers).status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "ADA@example.com", "password": "correct horse battery staple"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["email"] == "ada@example.com"
    assert login.json()["csrf_token"]


def test_password_is_argon2_hashed_and_duplicate_email_rejected(client):
    first = client.post(
        "/api/v1/auth/register",
        json={"email": "hash@example.com", "password": "a sufficiently long password"},
    )
    assert first.status_code == 201

    from app.database import session_scope
    from app.models import User

    with session_scope() as db:
        user = db.query(User).filter_by(email="hash@example.com").one()
        assert user.password_hash.startswith("$argon2id$")
        assert "sufficiently" not in user.password_hash

    duplicate = client.post(
        "/api/v1/auth/register",
        json={"email": "HASH@example.com", "password": "another long enough password"},
    )
    assert duplicate.status_code == 409


def test_forgot_password_is_generic_and_writes_dev_outbox(client, tmp_path: Path):
    unknown = client.post("/api/v1/auth/forgot-password", json={"email": "nobody@example.com"})
    assert unknown.status_code == 202
    assert "token" not in unknown.text.lower()

    client.post(
        "/api/v1/auth/register",
        json={"email": "reset@example.com", "password": "a sufficiently long password"},
    )
    known = client.post("/api/v1/auth/forgot-password", json={"email": "reset@example.com"})
    assert known.status_code == 202
    assert "token" not in known.text.lower()

    lines = (tmp_path / "outbox.jsonl").read_text().splitlines()
    assert len(lines) == 1
    assert "reset@example.com" in lines[0]
    assert "reset_password" in lines[0]


def test_unverified_user_can_inspect_and_logout_but_cannot_use_app(unverified_client):
    response = unverified_client.post(
        "/api/v1/auth/register",
        json={"email": "verify@example.com", "password": "a sufficiently long password"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["verification_required"] is True
    assert unverified_client.get("/api/v1/auth/me").status_code == 200
    assert unverified_client.get("/api/v1/tasks").status_code == 403
    assert unverified_client.post(
        "/api/v1/auth/logout", headers={"X-CSRF-Token": body["csrf_token"]}
    ).status_code == 204

    login = unverified_client.post(
        "/api/v1/auth/login",
        json={"email": "verify@example.com", "password": "a sufficiently long password"},
    )
    assert login.status_code == 403


def test_forgot_password_stays_generic_when_delivery_fails(client, monkeypatch):
    client.post(
        "/api/v1/auth/register",
        json={"email": "mailfail@example.com", "password": "a sufficiently long password"},
    )

    def fail_delivery(*_args, **_kwargs):
        raise RuntimeError("smtp is down")

    monkeypatch.setattr("app.auth.send_auth_email", fail_delivery)
    response = client.post(
        "/api/v1/auth/forgot-password", json={"email": "mailfail@example.com"}
    )
    assert response.status_code == 202
    assert "token" not in response.text.lower()
