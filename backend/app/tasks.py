from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import get_db
from .dependencies import current_user, require_csrf
from .models import Task, User
from .schemas import AnalyticsSummary, TaskCreate, TaskOut, TaskPatch


router = APIRouter(tags=["tasks"])


@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(
        select(Task).where(Task.user_id == user.id).order_by(Task.created_at, Task.id)
    ).all()


@router.post("/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate, user: User = Depends(require_csrf), db: Session = Depends(get_db)
):
    task = Task(user_id=user.id, **payload.model_dump(mode="json"))
    if task.status == "completed":
        task.completed_at = datetime.now(UTC)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def patch_task(
    task_id: str,
    payload: TaskPatch,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    task = db.scalar(select(Task).where(Task.id == task_id, Task.user_id == user.id))
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    changes = payload.model_dump(exclude_unset=True, mode="json")
    previous_status = task.status
    for key, value in changes.items():
        setattr(task, key, value)
    if task.status == "completed" and previous_status != "completed":
        task.completed_at = datetime.now(UTC)
    elif task.status != "completed":
        task.completed_at = None
    db.commit()
    db.refresh(task)
    return task


@router.get("/analytics/summary", response_model=AnalyticsSummary, tags=["analytics"])
def analytics_summary(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = dict(
        db.execute(
            select(Task.status, func.count(Task.id))
            .where(Task.user_id == user.id)
            .group_by(Task.status)
        ).all()
    )
    total = sum(rows.values())
    completed = rows.get("completed", 0)
    return AnalyticsSummary(
        total_tasks=total,
        pending_tasks=rows.get("pending", 0),
        completed_tasks=completed,
        completion_rate=round(completed * 100 / total, 2) if total else 0.0,
    )
