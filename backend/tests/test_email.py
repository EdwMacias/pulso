import pytest
from pydantic import ValidationError


def test_smtp_email_contains_frontend_action_url(monkeypatch, tmp_path):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    monkeypatch.setenv("DEV_OUTBOX_ENABLED", "false")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_FROM", "assistant@example.test")
    monkeypatch.setenv("SMTP_STARTTLS", "false")
    monkeypatch.setenv("APP_URL", "https://assistant.example.test")
    from app.config import get_settings

    get_settings.cache_clear()
    captured = {}

    class FakeSMTP:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def send_message(self, message):
            captured["body"] = message.get_content()

    monkeypatch.setattr("app.outbox.smtplib.SMTP", FakeSMTP)
    from app.outbox import send_auth_email

    send_auth_email("person@example.test", "reset_password", "secret-token")
    assert (
        "https://assistant.example.test/restablecer?token=secret-token" in captured["body"]
    )
    get_settings.cache_clear()


def test_production_rejects_development_email_bypass(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "a-production-secret-that-is-long-enough")
    monkeypatch.setenv("COOKIE_SECURE", "true")
    monkeypatch.setenv("DEV_AUTO_VERIFY_EMAIL", "true")
    from app.config import Settings

    with pytest.raises(ValidationError, match="development email flags"):
        Settings()
