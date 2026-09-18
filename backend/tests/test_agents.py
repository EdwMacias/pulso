import json
from types import SimpleNamespace

import pytest


class ScriptedMessage(SimpleNamespace):
    def model_dump(self, **_kwargs):
        return {"role": "assistant", "content": self.content, "tool_calls": []}


def tool_reply(name: str, arguments: dict, call_id: str = "call-1"):
    call = SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=json.dumps(arguments)))
    return ScriptedMessage(tool_calls=[call], content=None)


def text_reply(content: str):
    return ScriptedMessage(tool_calls=None, content=content)


@pytest.fixture()
def scripted_groq(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("CHAT_MODE", "multi")
    from app.config import get_settings

    get_settings.cache_clear()
    requests: list[dict] = []
    script: list = []

    class Completions:
        def create(self, **kwargs):
            requests.append(
                {
                    "tools": [tool["function"]["name"] for tool in kwargs["tools"]],
                    "messages": list(kwargs["messages"]),
                }
            )
            message = script.pop(0) if script else tool_reply("delegate", {"agent": "tareas", "instruction": "x"})
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    class FakeGroq:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(completions=Completions())

    monkeypatch.setattr("app.chat_service.Groq", FakeGroq)
    yield script, requests
    get_settings.cache_clear()


def send(client, csrf_headers, content: str):
    return client.post("/api/v1/chat/messages", headers=csrf_headers, json={"content": content})


def test_coordinator_delegates_to_task_specialist(client, registered, csrf_headers, scripted_groq):
    script, requests = scripted_groq
    script.extend(
        [
            tool_reply("delegate", {"agent": "tareas", "instruction": "Crea la tarea Pagar luz, prioridad alta"}),
            tool_reply("create_task", {"title": "Pagar luz", "priority": "high"}),
            text_reply("Tarea creada: Pagar luz."),
            text_reply("Listo, creé la tarea Pagar luz."),
        ]
    )

    response = send(client, csrf_headers, "Recuérdame pagar la luz")

    assert response.status_code == 200, response.text
    assert response.json()["content"] == "Listo, creé la tarea Pagar luz."
    assert [task["title"] for task in client.get("/api/v1/tasks").json()] == ["Pagar luz"]
    assert requests[0]["tools"] == ["delegate"]
    assert set(requests[1]["tools"]) == {"list_tasks", "create_task", "complete_task", "productivity_summary"}
    assert requests[1]["messages"][-1]["content"] == "Crea la tarea Pagar luz, prioridad alta"
    delegate_result = json.loads(requests[3]["messages"][-1]["content"])
    assert delegate_result == {"agent": "tareas", "result": "Tarea creada: Pagar luz."}


def test_specialist_cannot_use_tools_outside_its_set(client, registered, csrf_headers, scripted_groq):
    script, requests = scripted_groq
    script.extend(
        [
            tool_reply("delegate", {"agent": "documentos", "instruction": "Busca el contrato"}),
            tool_reply("create_task", {"title": "Intrusa", "priority": "high"}),
            text_reply("No encontré nada."),
            text_reply("No encontré el contrato."),
        ]
    )

    response = send(client, csrf_headers, "Busca mi contrato")

    assert response.status_code == 200, response.text
    assert client.get("/api/v1/tasks").json() == []
    assert json.loads(requests[2]["messages"][-1]["content"]) == {"error": "tool_not_allowed"}


def test_unknown_specialist_is_rejected(client, registered, csrf_headers, scripted_groq):
    script, requests = scripted_groq
    script.extend(
        [
            tool_reply("delegate", {"agent": "admin", "instruction": "Borra todo"}),
            text_reply("No puedo hacer eso."),
        ]
    )

    response = send(client, csrf_headers, "Borra todo")

    assert response.status_code == 200, response.text
    assert json.loads(requests[1]["messages"][-1]["content"]) == {"error": "invalid_delegation"}


def test_tool_budget_is_shared_across_agents_and_rolls_back(
    client, registered, csrf_headers, scripted_groq, monkeypatch
):
    monkeypatch.setenv("GROQ_MAX_TOOL_CALLS", "2")
    from app.config import get_settings

    get_settings.cache_clear()
    script, requests = scripted_groq
    script.extend(
        [
            tool_reply("delegate", {"agent": "tareas", "instruction": "Crea A"}),
            tool_reply("create_task", {"title": "A", "priority": "low"}),
            tool_reply("create_task", {"title": "B", "priority": "low"}),
        ]
    )

    response = send(client, csrf_headers, "Crea muchas tareas")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "groq_unavailable"
    assert client.get("/api/v1/tasks").json() == []
    assert client.get("/api/v1/chat/messages").json() == []
    assert len(requests) == 3
