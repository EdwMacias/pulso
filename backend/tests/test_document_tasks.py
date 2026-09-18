import json
from types import SimpleNamespace

from tests.test_documents import _ready_document


def _fake_groq(monkeypatch, payload, captured=None):
    class FakeGroq:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def create(self, **kwargs):
            if captured is not None:
                captured.append(kwargs)
            message = SimpleNamespace(content=json.dumps(payload))
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    monkeypatch.setattr("app.document_tasks.Groq", FakeGroq)


def _enable_groq(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    get_settings.cache_clear()


def test_parse_suggestions_drops_invalid_items():
    from app.document_tasks import parse_suggestions

    raw = json.dumps({"tasks": [
        {"title": "Hacer check-in", "priority": "urgent", "remind_at": "2030-05-01T08:00:00-05:00", "page": 1},
        {"title": "", "priority": "high"},
        {"title": "Sin zona", "remind_at": "2030-05-01T08:00:00"},
        {"title": "Página inventada", "page": 99, "kind": "otro"},
        "texto suelto",
    ]})

    suggestions = parse_suggestions(raw, page_count=2)

    assert [s.title for s in suggestions] == ["Hacer check-in", "Página inventada"]
    assert suggestions[0].priority.value == "medium"
    assert suggestions[1].page is None and suggestions[1].kind == "general"
    assert parse_suggestions("no es json", page_count=1) == []


def test_flight_document_suggests_tasks_without_saving(client, registered, csrf_headers, monkeypatch):
    _enable_groq(monkeypatch)
    captured = []
    _fake_groq(monkeypatch, {"tasks": [{
        "title": "Hacer check-in vuelo AV123", "description": "Bogotá → Madrid", "priority": "high",
        "remind_at": "2030-05-01T08:00:00-05:00", "page": 1, "evidence": "Salida 02 may 2030 08:00",
    }]}, captured)
    document_id = _ready_document(registered["user"]["id"], [(1, "Vuelo AV123 Bogotá Madrid. Salida 02 may 2030 08:00.")])

    response = client.post(f"/api/v1/documents/{document_id}/task-suggestions", headers=csrf_headers)

    assert response.status_code == 200, response.text
    assert response.json()["suggestions"][0]["title"] == "Hacer check-in vuelo AV123"
    assert captured[0]["response_format"] == {"type": "json_object"}
    assert "Vuelo AV123" in captured[0]["messages"][1]["content"]
    assert client.get("/api/v1/tasks").json() == []


def test_confirmed_tasks_create_tasks_and_future_reminders(client, registered, csrf_headers):
    document_id = _ready_document(registered["user"]["id"], [(1, "Factura FV-88 a crédito, vence 30 días.")])

    response = client.post(f"/api/v1/documents/{document_id}/tasks", headers=csrf_headers, json={"tasks": [
        {"title": "Cobrar factura FV-88 a Acme", "priority": "high", "kind": "cobro", "invoice_number": "FV-88",
         "customer": "Acme SAS", "issuer": "Mi Empresa", "amount": "COP 1.200.000", "due_date": "2030-06-30",
         "remind_at": "2030-06-27T09:00:00-05:00", "page": 1},
        {"title": "Tarea con fecha pasada", "remind_at": "2020-01-01T09:00:00-05:00"},
    ]})

    assert response.status_code == 201, response.text
    assert response.json() == {"created_tasks": 2, "created_reminders": 1}
    tasks = {task["title"]: task for task in client.get("/api/v1/tasks").json()}
    invoice = tasks["Cobrar factura FV-88 a Acme"]
    assert "Cuenta por cobrar" in invoice["description"]
    assert "Cliente: Acme SAS" in invoice["description"]
    assert "Vence: 2030-06-30" in invoice["description"]
    assert "Fuente: manual.pdf, pág. 1" in invoice["description"]
    assert len(client.get("/api/v1/reminders").json()) == 1


def test_payable_invoice_names_the_supplier(client, registered, csrf_headers):
    document_id = _ready_document(registered["user"]["id"], [(1, "Factura de compra.")])

    client.post(f"/api/v1/documents/{document_id}/tasks", headers=csrf_headers, json={"tasks": [
        {"title": "Pagar factura 77 a Proveedor SA", "kind": "pago", "issuer": "Proveedor SA", "customer": "Yo"},
    ]})

    description = client.get("/api/v1/tasks").json()[0]["description"]
    assert description.startswith("Cuenta por pagar")
    assert "Proveedor: Proveedor SA" in description


def test_other_users_cannot_extract_or_add_tasks(client, registered, csrf_headers):
    from tests.conftest import register

    document_id = _ready_document(registered["user"]["id"], [(1, "Vuelo privado.")])
    eve = register(client, "eve@example.com").json()
    headers = {"X-CSRF-Token": eve["csrf_token"]}

    assert client.post(f"/api/v1/documents/{document_id}/task-suggestions", headers=headers).status_code == 404
    assert client.post(f"/api/v1/documents/{document_id}/tasks", headers=headers,
        json={"tasks": [{"title": "Intrusa"}]}).status_code == 404


def test_suggestions_require_groq(client, registered, csrf_headers):
    document_id = _ready_document(registered["user"]["id"], [(1, "Vuelo.")])

    response = client.post(f"/api/v1/documents/{document_id}/task-suggestions", headers=csrf_headers)

    assert response.status_code == 503
