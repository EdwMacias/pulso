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

    assert [chunk.page_number for chunk in rank_chunks(chunks, "seguridad contraseña")] == [2, 1]
