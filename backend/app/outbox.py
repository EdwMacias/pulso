import json
import smtplib
from datetime import UTC, datetime
from email.message import EmailMessage
from urllib.parse import quote

from .config import get_settings


def send_auth_email(recipient: str, purpose: str, token: str) -> None:
    settings = get_settings()
    if settings.dev_outbox_enabled:
        settings.dev_outbox_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "recipient": recipient,
            "purpose": purpose,
            "token": token,
            "created_at": datetime.now(UTC).isoformat(),
        }
        with settings.dev_outbox_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
        return

    if not settings.smtp_configured:
        raise RuntimeError("Email delivery is not configured")
    subject = "Verifica tu cuenta" if purpose == "verify_email" else "Restablece tu contraseña"
    route = "verificar" if purpose == "verify_email" else "restablecer"
    action_url = f"{settings.app_url}/{route}?token={quote(token, safe='')}"
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from
    message["To"] = recipient
    message.set_content(
        f"Abre este enlace de un solo uso:\n\n{action_url}\n\n"
        "Si no solicitaste este mensaje, puedes ignorarlo."
    )
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        if settings.smtp_starttls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password or "")
        smtp.send_message(message)
