from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .dependencies import current_user, require_csrf
from .document_service import (DocumentConfigurationError, DocumentProviderError,
    DocumentValidationError, answer_document_question, create_document, delete_document_file)
from .document_tasks import create_document_tasks, extract_task_suggestions
from .models import Document, User
from .schemas import (DocumentAnswerOut, DocumentDetailOut, DocumentOut, DocumentQuestionIn, DocumentSourceOut,
    DocumentTasksIn, DocumentTasksOut, TaskSuggestionsOut)

router = APIRouter(prefix="/documents", tags=["documents"])

def _owned(db: Session, user: User, document_id: str) -> Document:
    document = db.scalar(select(Document).where(Document.id == document_id, Document.user_id == user.id))
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document

@router.get("", response_model=list[DocumentOut])
def list_documents(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Document).where(Document.user_id == user.id).order_by(Document.created_at.desc())).all()

@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(file: UploadFile = File(...), user: User = Depends(require_csrf), db: Session = Depends(get_db)):
    try: return await create_document(db, user, file)
    except DocumentValidationError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc

@router.get("/{document_id}", response_model=DocumentDetailOut)
def get_document(document_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _owned(db, user, document_id)

@router.post("/{document_id}/questions", response_model=DocumentAnswerOut)
def ask_document(document_id: str, payload: DocumentQuestionIn, user: User = Depends(require_csrf), db: Session = Depends(get_db)):
    document = _owned(db, user, document_id)
    if document.status != "ready": raise HTTPException(status_code=409, detail="Document is not ready")
    try:
        result = answer_document_question(db, user, document, payload.question)
        return DocumentAnswerOut(
            answer=result.answer,
            source_pages=sorted({item.chunk.page_number for item in result.sources}),
            sources=[DocumentSourceOut(chunk_index=item.chunk.chunk_index, page_number=item.chunk.page_number,
                score=item.score, matched_terms=list(item.matched_terms), content=item.chunk.content) for item in result.sources],
            total_chunks=result.total_chunks,
        )
    except DocumentConfigurationError as exc: raise HTTPException(status_code=503, detail={"code":"groq_unavailable", "message":"Groq is not configured"}) from exc
    except DocumentProviderError as exc: raise HTTPException(status_code=503, detail={"code":"groq_unavailable", "message":"Groq request failed"}) from exc

@router.post("/{document_id}/task-suggestions", response_model=TaskSuggestionsOut)
def suggest_document_tasks(document_id: str, user: User = Depends(require_csrf), db: Session = Depends(get_db)):
    document = _owned(db, user, document_id)
    if document.status != "ready": raise HTTPException(status_code=409, detail="Document is not ready")
    try:
        return TaskSuggestionsOut(suggestions=extract_task_suggestions(db, user, document))
    except DocumentConfigurationError as exc: raise HTTPException(status_code=503, detail={"code":"groq_unavailable", "message":"Groq is not configured"}) from exc
    except DocumentProviderError as exc: raise HTTPException(status_code=503, detail={"code":"groq_unavailable", "message":"Groq request failed"}) from exc

@router.post("/{document_id}/tasks", response_model=DocumentTasksOut, status_code=status.HTTP_201_CREATED)
def add_document_tasks(document_id: str, payload: DocumentTasksIn, user: User = Depends(require_csrf), db: Session = Depends(get_db)):
    document = _owned(db, user, document_id)
    tasks, reminders = create_document_tasks(db, user, document, payload.tasks)
    return DocumentTasksOut(created_tasks=tasks, created_reminders=reminders)

@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_document(document_id: str, user: User = Depends(require_csrf), db: Session = Depends(get_db)):
    document = _owned(db, user, document_id); delete_document_file(document); db.delete(document); db.commit()
