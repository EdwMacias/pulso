from urllib.parse import quote

import httpx

from .config import get_settings


class EvolutionError(RuntimeError):
    pass


class EvolutionRejected(EvolutionError):
    pass


class EvolutionUncertain(EvolutionError):
    pass


class EvolutionClient:
    def __init__(self, http_client: httpx.Client | None = None):
        settings = get_settings()
        if not settings.whatsapp_configured:
            raise EvolutionRejected("Evolution API is not configured")
        self.base_url = settings.whatsapp_api_url
        self.api_key = settings.whatsapp_api_key
        self.instance = settings.whatsapp_instance
        self.http_client = http_client or httpx.Client(timeout=15)

    def send_text(self, recipient_jid: str, text: str) -> str:
        url = f"{self.base_url}/message/sendText/{quote(self.instance, safe='')}"
        try:
            response = self.http_client.post(
                url,
                headers={"apikey": self.api_key},
                json={"number": recipient_jid, "text": text},
            )
        except httpx.RequestError as exc:
            raise EvolutionUncertain("Evolution request outcome is unknown") from exc
        if 400 <= response.status_code < 500:
            raise EvolutionRejected(f"Evolution rejected the message with {response.status_code}")
        if response.status_code >= 500:
            raise EvolutionUncertain(f"Evolution failed with {response.status_code}")
        try:
            message_id = response.json()["key"]["id"]
        except (KeyError, TypeError, ValueError) as exc:
            raise EvolutionUncertain("Evolution response did not include a message id") from exc
        if not isinstance(message_id, str) or not message_id:
            raise EvolutionUncertain("Evolution response included an invalid message id")
        return message_id
