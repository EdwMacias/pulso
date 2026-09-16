import json

import httpx
import pytest


@pytest.fixture()
def evolution_settings(monkeypatch):
    from app.config import get_settings

    for name, value in {
        "WHATSAPP_API_URL": "https://evolution.example.test/",
        "WHATSAPP_API_KEY": "api-key",
        "WHATSAPP_INSTANCE": "pulso principal",
        "WHATSAPP_WEBHOOK_SECRET": "webhook-secret-at-least-32-characters",
    }.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_send_text_uses_instance_apikey_and_modern_payload(evolution_settings):
    from app.evolution_client import EvolutionClient

    captured = {}

    def handler(request: httpx.Request):
        captured["request"] = request
        return httpx.Response(201, json={"key": {"id": "out-1"}})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = EvolutionClient(http_client=http_client)

    assert client.send_text("573001234567@s.whatsapp.net", "Hola") == "out-1"
    request = captured["request"]
    assert request.url.raw_path == b"/message/sendText/pulso%20principal"
    assert request.headers["apikey"] == "api-key"
    assert json.loads(request.content) == {
        "number": "573001234567@s.whatsapp.net",
        "text": "Hola",
    }


def test_send_text_classifies_provider_rejection(evolution_settings):
    from app.evolution_client import EvolutionClient, EvolutionRejected

    http_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(400, json={"error": "bad recipient"})
        )
    )
    with pytest.raises(EvolutionRejected):
        EvolutionClient(http_client=http_client).send_text("invalid@lid", "Hola")


def test_send_text_classifies_uncertain_server_failure(evolution_settings):
    from app.evolution_client import EvolutionClient, EvolutionUncertain

    http_client = httpx.Client(
        transport=httpx.MockTransport(lambda _request: httpx.Response(503))
    )
    with pytest.raises(EvolutionUncertain):
        EvolutionClient(http_client=http_client).send_text(
            "573001234567@s.whatsapp.net", "Hola"
        )
