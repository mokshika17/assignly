import uuid
from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.dependencies import get_db, get_current_user, require_admin
from app.models import Task, Project, User, UserRole, TaskStatus
from app.schemas import TaskCreate, TaskUpdate, TaskRead
from app.cache import cache_get, cache_set, cache_delete
from app.config import settings

router = APIRouter(prefix="/tasks", tags=["Tasks"])


# ---------------------------------------------------------------------------
# Create Task (admin only)
# ---------------------------------------------------------------------------

@router.post("/", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    project = db.query(Project).filter(Project.id == payload.project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    if payload.assignee_id:
        assignee = db.query(User).filter(User.id == payload.assignee_id).first()
        if not assignee:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignee not found")

    task = Task(
        title=payload.title,
        description=payload.description,
        due_date=payload.due_date,
        project_id=payload.project_id,
        assignee_id=payload.assignee_id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    # Invalidate tasks cache for this project + dashboard for assignee
    cache_delete(f"tasks:project:{payload.project_id}")
    if payload.assignee_id:
        cache_delete(f"dashboard:{payload.assignee_id}")

    return task


# ---------------------------------------------------------------------------
# List Tasks (optionally filter by project)
# ---------------------------------------------------------------------------

@router.get("/", response_model=List[TaskRead])
def list_tasks(
    project_id: uuid.UUID = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if project_id:
        cache_key = f"tasks:project:{project_id}"
        cached = cache_get(cache_key)
        if cached is not None:
            return cached
        tasks = db.query(Task).filter(Task.project_id == project_id).all()
        serialized = [TaskRead.model_validate(t).model_dump(mode="json") for t in tasks]
        cache_set(cache_key, serialized, settings.CACHE_TTL_TASKS)
        return tasks

    return db.query(Task).all()


@router.get("/dashboard/summary", response_model=dict)
def dashboard_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cache_key = f"dashboard:{current_user.id}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    now = datetime.now(timezone.utc)
    base_query = db.query(Task)
    if current_user.role == UserRole.member:
        base_query = base_query.filter(Task.assignee_id == current_user.id)

    tasks = base_query.all()
    summary = {
        "total": len(tasks),
        "todo": sum(1 for t in tasks if t.status == TaskStatus.todo),
        "in_progress": sum(1 for t in tasks if t.status == TaskStatus.in_progress),
        "done": sum(1 for t in tasks if t.status == TaskStatus.done),
        "overdue": sum(
            1 for t in tasks
            if t.due_date and t.due_date < now and t.status != TaskStatus.done
        ),
    }
    cache_set(cache_key, summary, settings.CACHE_TTL_DASHBOARD)
    return summary


@router.get("/{task_id}", response_model=TaskRead)
def get_task(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


# ---------------------------------------------------------------------------
# Update Task
# Admin: can update any field on any task
# Member: can only update status on their own assigned tasks
# ---------------------------------------------------------------------------

@router.patch("/{task_id}", response_model=TaskRead)
def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    if current_user.role == UserRole.member:
        # Members can only update status on their own tasks
        if task.assignee_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only update tasks assigned to you")
        update_data = payload.model_dump(exclude_unset=True)
        forbidden = set(update_data.keys()) - {"status"}
        if forbidden:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Members can only update status. Forbidden fields: {forbidden}")
    else:
        update_data = payload.model_dump(exclude_unset=True)

        if "assignee_id" in update_data and update_data["assignee_id"]:
            assignee = db.query(User).filter(User.id == update_data["assignee_id"]).first()
            if not assignee:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignee not found")

    for field, value in update_data.items():
        setattr(task, field, value)

    # Set or clear completed_at based on status
    if "status" in update_data:
        if update_data["status"] == TaskStatus.done:
            task.completed_at = datetime.now(timezone.utc)
        else:
            task.completed_at = None   # revert if moved back from done

    db.commit()
    db.refresh(task)

    # Invalidate tasks + dashboard cache
    cache_delete(f"tasks:project:{task.project_id}")
    if task.assignee_id:
        cache_delete(f"dashboard:{task.assignee_id}")

    return task


# ---------------------------------------------------------------------------
# Delete Task (admin only)
# ---------------------------------------------------------------------------

@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    project_id = task.project_id
    assignee_id = task.assignee_id
    db.delete(task)
    db.commit()

    cache_delete(f"tasks:project:{project_id}")
    if assignee_id:
        cache_delete(f"dashboard:{assignee_id}")