import uuid


def test_document_chunks_belong_to_the_document_in_order(client, registered):
    from app.database import session_scope
    from app.models import Document, DocumentChunk

    with session_scope() as db:
        document = Document(
            user_id=registered["user"]["id"],
            original_name="guia.pdf",
            storage_name="opaque.pdf",
            size_bytes=10,
            page_count=1,
            status="ready",
        )
        db.add(document)
        db.flush()
        db.add(
            DocumentChunk(
                document_id=document.id,
                chunk_index=0,
                page_number=1,
                content="Contenido de prueba",
            )
        )

    with session_scope() as db:
        chunk = db.query(DocumentChunk).filter_by(document_id=document.id).one()
        assert chunk.page_number == 1
        assert chunk.content == "Contenido de prueba"


def test_rank_chunks_prefers_question_terms(client, registered):
    from app.document_service import rank_chunks
    from app.models import DocumentChunk

    chunks = [
        DocumentChunk(chunk_index=0, page_number=1, content="Cocina y recetas"),
        DocumentChunk(chunk_index=1, page_number=2, content="La guía explica seguridad de contraseñas"),
    ]

    ranked = rank_chunks(chunks, "¿Qué dice sobre la seguridad de las contraseñas?")

    assert [item.chunk.page_number for item in ranked] == [2]
    assert set(ranked[0].matched_terms) == {"seguridad", "contrasena"}


def test_bm25_ignores_accents_and_rewards_rare_terms(client, registered):
    from app.retrieval import bm25_rank, tokenize
    from app.models import DocumentChunk

    assert tokenize("Límites de Contraseñas") == ["limite", "contrasena"]
    chunks = [
        DocumentChunk(chunk_index=0, page_number=1, content="La política general aplica a todo el personal."),
        DocumentChunk(chunk_index=1, page_number=2, content="La política de vacaciones concede quince días hábiles."),
        DocumentChunk(chunk_index=2, page_number=3, content="La política de horarios y la política de uniformes."),
    ]

    ranked = bm25_rank(chunks, "politica de VACACIONES")

    assert ranked[0].chunk.page_number == 2
    assert ranked[0].score > ranked[1].score


def test_chunks_overlap_and_respect_limit(client, registered):
    from app.document_service import CHUNK_MAX_CHARS, _chunks_for_page

    text = " ".join(f"palabra{i}" for i in range(600))
    chunks = _chunks_for_page(text, page_number=4, start_index=10)

    assert len(chunks) > 1
    assert all(len(chunk.content) <= CHUNK_MAX_CHARS for chunk in chunks)
    assert [chunk.chunk_index for chunk in chunks] == list(range(10, 10 + len(chunks)))
    assert chunks[0].content.split()[-1] in chunks[1].content.split()[:40]


def test_context_budget_keeps_whole_chunks():
    from app.document_service import select_context
    from app.models import DocumentChunk
    from app.retrieval import ScoredChunk

    ranked = [
        ScoredChunk(DocumentChunk(chunk_index=i, page_number=i + 1, content="x" * 600), 3.0 - i, ("x",))
        for i in range(3)
    ]

    assert [item.chunk.page_number for item in select_context(ranked, 1_300)] == [1, 2]


def _ready_document(user_id: str, contents: list[tuple[int, str]]) -> str:
    from app.database import session_scope
    from app.models import Document, DocumentChunk

    with session_scope() as db:
        document = Document(user_id=user_id, original_name="manual.pdf", storage_name=f"{uuid.uuid4()}.pdf",
            size_bytes=10, page_count=len(contents), status="ready")
        db.add(document)
        db.flush()
        for index, (page, content) in enumerate(contents):
            db.add(DocumentChunk(document_id=document.id, chunk_index=index, page_number=page, content=content))
        return document.id


def test_question_returns_answer_with_retrieved_sources(client, registered, csrf_headers, monkeypatch):
    from types import SimpleNamespace

    from app import document_service
    from app.config import get_settings

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    get_settings.cache_clear()
    prompts = []

    class FakeGroq:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def create(self, **kwargs):
            prompts.append(kwargs["messages"][1]["content"])
            message = SimpleNamespace(content="Tienes 15 días de vacaciones (pág. 2).")
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    monkeypatch.setattr(document_service, "Groq", FakeGroq)
    document_id = _ready_document(registered["user"]["id"], [
        (1, "Bienvenida a la empresa y organigrama."),
        (2, "Las vacaciones anuales son de quince días hábiles."),
    ])

    response = client.post(f"/api/v1/documents/{document_id}/questions", headers=csrf_headers,
        json={"question": "¿Cuántos días de vacaciones tengo?"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["answer"].startswith("Tienes 15 días")
    assert body["source_pages"] == [2]
    assert body["total_chunks"] == 2
    assert body["sources"][0]["matched_terms"] == ["dias", "vacacione"]
    assert "[Fragmento 2 · Página 2]" in prompts[0]
    assert "organigrama" not in prompts[0]
    get_settings.cache_clear()


def test_question_without_matches_skips_the_model(client, registered, csrf_headers, monkeypatch):
    from app import document_service
    from app.config import get_settings

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    get_settings.cache_clear()
    monkeypatch.setattr(document_service, "Groq", None)
    document_id = _ready_document(registered["user"]["id"], [(1, "Bienvenida a la empresa.")])

    response = client.post(f"/api/v1/documents/{document_id}/questions", headers=csrf_headers,
        json={"question": "¿Cuál es la capital de Mongolia?"})

    assert response.status_code == 200
    assert response.json()["answer"] == document_service.NO_CONTEXT_ANSWER
    assert response.json()["sources"] == []
    get_settings.cache_clear()


def test_document_search_only_reads_own_ready_documents(client, registered):
    from types import SimpleNamespace

    from app.database import session_scope
    from app.document_service import search_user_documents
    from tests.conftest import register

    ada_id = registered["user"]["id"]
    eve_id = register(client, "eve@example.com").json()["user"]["id"]
    _ready_document(ada_id, [(3, "El reembolso de viáticos se solicita en diez días.")])
    _ready_document(eve_id, [(1, "Viáticos secretos de otra persona.")])

    with session_scope() as db:
        results = search_user_documents(db, SimpleNamespace(id=ada_id), "viáticos")

    assert [(item["document"], item["page"]) for item in results] == [("manual.pdf", 3)]
    assert "secretos" not in results[0]["content"]


def test_assistant_answers_from_documents_with_search_tool(client, registered, csrf_headers, monkeypatch):
    import json
    from types import SimpleNamespace

    from app.config import get_settings

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    get_settings.cache_clear()
    _ready_document(registered["user"]["id"], [
        (1, "Bienvenida y organigrama."),
        (7, "El reembolso de viáticos se solicita en un plazo de diez días."),
    ])
    tool_results = []

    class ToolMessage(SimpleNamespace):
        def model_dump(self, **_kwargs):
            return {"role": "assistant", "tool_calls": []}

    class Completions:
        def create(self, **kwargs):
            tools = {tool["function"]["name"] for tool in kwargs["tools"]}
            assert "search_documents" in tools
            if kwargs["messages"][-1]["role"] != "tool":
                call = SimpleNamespace(id="call-1", function=SimpleNamespace(
                    name="search_documents", arguments='{"query":"plazo reembolso viáticos"}'))
                return SimpleNamespace(choices=[SimpleNamespace(message=ToolMessage(tool_calls=[call], content=None))])
            tool_results.append(json.loads(kwargs["messages"][-1]["content"]))
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                tool_calls=None, content="Tienes diez días (manual.pdf, pág. 7)."))])

    class FakeGroq:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(completions=Completions())

    monkeypatch.setattr("app.chat_service.Groq", FakeGroq)
    response = client.post("/api/v1/chat/messages", headers=csrf_headers,
        json={"content": "¿Cuál es el plazo para el reembolso de viáticos?"})

    assert response.status_code == 200, response.text
    assert response.json()["content"] == "Tienes diez días (manual.pdf, pág. 7)."
    fragments = tool_results[0]["fragments"]
    assert [(item["document"], item["page"]) for item in fragments] == [("manual.pdf", 7)]
    get_settings.cache_clear()
