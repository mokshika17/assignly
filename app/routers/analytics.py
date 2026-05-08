from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from pydantic import BaseModel
from app.dependencies import get_db, require_admin
from app.models import Task, Project, User, TaskStatus

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


# ---------------------------------------------------------------------------
# Response Schemas
# ---------------------------------------------------------------------------

class SummaryStats(BaseModel):
    total_tasks: int
    completed_tasks: int
    completion_rate: float
    overdue_tasks: int
    avg_lateness_days: float
    total_projects: int
    total_members: int


class ProjectStat(BaseModel):
    project_id: str
    project_name: str
    total: int
    done: int
    in_progress: int
    todo: int
    completion_rate: float


class AssigneeStat(BaseModel):
    user_id: str
    user_name: str
    total: int
    done: int
    in_progress: int
    todo: int
    overdue: int


class TimelinePoint(BaseModel):
    date: str
    completed: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/summary", response_model=SummaryStats)
def get_summary(db: Session = Depends(get_db), _=Depends(require_admin)):
    now = datetime.now(timezone.utc)
    tasks = db.query(Task).all()

    total = len(tasks)
    completed = [t for t in tasks if t.status == TaskStatus.done]
    overdue = [
        t for t in tasks
        if t.due_date and t.due_date < now and t.status != TaskStatus.done
    ]

    # avg lateness: days between due_date and completed_at for late completions
    late_tasks = [
        t for t in completed
        if t.due_date and t.completed_at and t.completed_at > t.due_date
    ]
    avg_lateness = 0.0
    if late_tasks:
        total_late_days = sum(
            (t.completed_at - t.due_date).total_seconds() / 86400
            for t in late_tasks
        )
        avg_lateness = round(total_late_days / len(late_tasks), 1)

    total_projects = db.query(Project).count()
    total_members = db.query(User).count()

    return SummaryStats(
        total_tasks=total,
        completed_tasks=len(completed),
        completion_rate=round(len(completed) / total * 100, 1) if total else 0.0,
        overdue_tasks=len(overdue),
        avg_lateness_days=avg_lateness,
        total_projects=total_projects,
        total_members=total_members,
    )


@router.get("/projects", response_model=List[ProjectStat])
def get_project_stats(db: Session = Depends(get_db), _=Depends(require_admin)):
    projects = db.query(Project).all()
    result = []
    for p in projects:
        tasks = p.tasks
        total = len(tasks)
        done = sum(1 for t in tasks if t.status == TaskStatus.done)
        in_progress = sum(1 for t in tasks if t.status == TaskStatus.in_progress)
        todo = sum(1 for t in tasks if t.status == TaskStatus.todo)
        result.append(ProjectStat(
            project_id=str(p.id),
            project_name=p.name,
            total=total,
            done=done,
            in_progress=in_progress,
            todo=todo,
            completion_rate=round(done / total * 100, 1) if total else 0.0,
        ))
    return result


@router.get("/assignees", response_model=List[AssigneeStat])
def get_assignee_stats(db: Session = Depends(get_db), _=Depends(require_admin)):
    now = datetime.now(timezone.utc)
    members = db.query(User).all()
    result = []
    for u in members:
        tasks = db.query(Task).filter(Task.assignee_id == u.id).all()
        if not tasks:
            continue
        total = len(tasks)
        done = sum(1 for t in tasks if t.status == TaskStatus.done)
        in_progress = sum(1 for t in tasks if t.status == TaskStatus.in_progress)
        todo = sum(1 for t in tasks if t.status == TaskStatus.todo)
        overdue = sum(
            1 for t in tasks
            if t.due_date and t.due_date < now and t.status != TaskStatus.done
        )
        result.append(AssigneeStat(
            user_id=str(u.id),
            user_name=u.name,
            total=total,
            done=done,
            in_progress=in_progress,
            todo=todo,
            overdue=overdue,
        ))
    return result


@router.get("/timeline", response_model=List[TimelinePoint])
def get_timeline(db: Session = Depends(get_db), _=Depends(require_admin)):
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=29)

    completed_tasks = db.query(Task).filter(
        Task.completed_at >= since,
        Task.status == TaskStatus.done,
    ).all()

    # bucket by date
    counts: dict[str, int] = {}
    for i in range(30):
        day = (since + timedelta(days=i)).strftime("%Y-%m-%d")
        counts[day] = 0

    for t in completed_tasks:
        day = t.completed_at.strftime("%Y-%m-%d")
        if day in counts:
            counts[day] += 1

    return [TimelinePoint(date=k, completed=v) for k, v in sorted(counts.items())]