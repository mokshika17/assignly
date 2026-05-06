import uuid
from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.dependencies import get_db, get_current_user, require_admin
from app.models import Task, Project, User, UserRole, TaskStatus
from app.schemas import TaskCreate, TaskUpdate, TaskRead

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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    if payload.assignee_id:
        assignee = db.query(User).filter(User.id == payload.assignee_id).first()
        if not assignee:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assignee not found",
            )

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
    query = db.query(Task)
    if project_id:
        query = query.filter(Task.project_id == project_id)
    return query.all()


# ---------------------------------------------------------------------------
# Get Single Task
# ---------------------------------------------------------------------------

@router.get("/{task_id}", response_model=TaskRead)
def get_task(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    if current_user.role == UserRole.member:
        # Members can only update status on their own tasks
        if task.assignee_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only update tasks assigned to you",
            )
        update_data = payload.model_dump(exclude_unset=True)
        allowed_fields = {"status"}
        forbidden = set(update_data.keys()) - allowed_fields
        if forbidden:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Members can only update status. Forbidden fields: {forbidden}",
            )
    else:
        update_data = payload.model_dump(exclude_unset=True)

        if "assignee_id" in update_data and update_data["assignee_id"]:
            assignee = db.query(User).filter(User.id == update_data["assignee_id"]).first()
            if not assignee:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Assignee not found",
                )

    for field, value in update_data.items():
        setattr(task, field, value)

    db.commit()
    db.refresh(task)
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    db.delete(task)
    db.commit()


# ---------------------------------------------------------------------------
# Dashboard — overdue + status summary (all users)
# ---------------------------------------------------------------------------

@router.get("/dashboard/summary", response_model=dict)
def dashboard_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
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
    return summary