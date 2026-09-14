from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _test_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, auto_verify: bool):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("DEV_AUTO_VERIFY_EMAIL", str(auto_verify).lower())
    monkeypatch.setenv("DEV_OUTBOX_ENABLED", "true")
    monkeypatch.setenv("DEV_OUTBOX_PATH", str(tmp_path / "outbox.jsonl"))

    from app.config import get_settings
    from app.database import reset_engine

    get_settings.cache_clear()
    reset_engine()
    from app.main import create_app

    return TestClient(create_app())


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from app.config import get_settings
    from app.database import reset_engine

    with _test_client(tmp_path, monkeypatch, auto_verify=True) as test_client:
        yield test_client
    reset_engine()
    get_settings.cache_clear()


@pytest.fixture()
def unverified_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from app.config import get_settings
    from app.database import reset_engine

    with _test_client(tmp_path, monkeypatch, auto_verify=False) as test_client:
        yield test_client
    reset_engine()
    get_settings.cache_clear()


def register(client: TestClient, email: str, password: str = "correct horse battery staple"):
    response = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    return response


@pytest.fixture()
def registered(client: TestClient):
    response = register(client, "ada@example.com")
    return response.json()


@pytest.fixture()
def csrf_headers(client: TestClient, registered):
    return {"X-CSRF-Token": registered["csrf_token"]}
