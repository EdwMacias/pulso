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
