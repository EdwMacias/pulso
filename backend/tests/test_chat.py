def test_chat_requires_groq_configuration(client, registered, csrf_headers):
    response = client.post(
        "/api/v1/chat/messages", headers=csrf_headers, json={"content": "Hola"}
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "groq_unavailable"
    assert client.get("/api/v1/chat/messages").json() == []


def test_integrations_status_is_explicit(client, registered):
    response = client.get("/api/v1/integrations/status")
    assert response.status_code == 200
    assert response.json() == {
        "groq": {"configured": False},
        "whatsapp": {"configured": False, "available": False},
        "tts": {"configured": False, "available": False},
    }


def test_whatsapp_is_available_only_with_complete_configuration(
    client, registered, monkeypatch
):
    from app.config import get_settings

    for name, value in {
        "WHATSAPP_API_URL": "https://evolution.example.test/",
        "WHATSAPP_API_KEY": "api-key",
        "WHATSAPP_INSTANCE": "pulso",
        "WHATSAPP_WEBHOOK_SECRET": "webhook-secret-at-least-32-characters",
    }.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()

    response = client.get("/api/v1/integrations/status")

    assert response.status_code == 200
    assert response.json()["whatsapp"] == {"configured": True, "available": True}
    assert get_settings().whatsapp_api_url == "https://evolution.example.test"
    get_settings.cache_clear()


def test_failed_groq_turn_rolls_back_tool_writes(client, registered, csrf_headers, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    from app.config import get_settings

    get_settings.cache_clear()
    tool_call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(
            name="create_task",
            arguments='{"title":"Must rollback","priority":"high"}',
        ),
    )

    class ToolMessage(SimpleNamespace):
        def model_dump(self, **_kwargs):
            return {"role": "assistant", "tool_calls": []}

    first = SimpleNamespace(
        choices=[SimpleNamespace(message=ToolMessage(tool_calls=[tool_call], content=None))]
    )

    class Completions:
        calls = 0

        def create(self, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                return first
            raise RuntimeError("provider failed after tool write")

    class FakeGroq:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(completions=Completions())

    monkeypatch.setattr("app.chat.Groq", FakeGroq)
    response = client.post(
        "/api/v1/chat/messages", headers=csrf_headers, json={"content": "Crea una tarea"}
    )
    assert response.status_code == 503
    assert client.get("/api/v1/tasks").json() == []
