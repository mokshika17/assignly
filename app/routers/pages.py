from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from typing import Optional
import uuid

from app.dependencies import get_db
from app.models import User, Project, Task, UserRole, TaskStatus
from app.auth import verify_password, create_access_token, hash_password, decode_access_token

router = APIRouter(tags=["Pages"])
templates = Jinja2Templates(directory="templates")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_optional_user(request: Request, db: Session) -> Optional[User]:
    """Return current user from cookie, or None if not authenticated."""
    token = request.cookies.get("access_token")
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload:
        return None
    try:
        user = db.query(User).filter(User.id == uuid.UUID(payload["sub"])).first()
        return user if user and user.is_active else None
    except Exception:
        return None


def redirect_with_cookie(url: str, token: str, remember_me: bool = False) -> RedirectResponse:
    response = RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)
    max_age = 30 * 24 * 60 * 60 if remember_me else None  # 30 days in seconds
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=max_age,  # None = session cookie (expires on browser close)
    )
    return response


def render(template_name: str, request: Request, context: dict) -> HTMLResponse:
    """Wrapper to keep TemplateResponse calls consistent."""
    return templates.TemplateResponse(
        request=request,
        name=template_name,
        context=context,
    )


# ---------------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
def root(request: Request, db: Session = Depends(get_db)):
    user = get_optional_user(request, db)
    if user:
        return RedirectResponse(url="/dashboard", status_code=302)
    return RedirectResponse(url="/login", status_code=302)


# ---------------------------------------------------------------------------
# Auth Pages
# ---------------------------------------------------------------------------

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return render("login.html", request, {"user": None})


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    remember_me: str = Form(default="off"),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        return render("login.html", request, {
            "user": None,
            "error": "Invalid email or password",
        })
    is_remembered = remember_me == "on"
    token = create_access_token(
        subject=str(user.id),
        role=user.role.value,
        remember_me=is_remembered,
    )
    return redirect_with_cookie("/dashboard", token, remember_me=is_remembered)


@router.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    return render("signup.html", request, {"user": None})


@router.post("/signup", response_class=HTMLResponse)
def signup_submit(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form("member"),
    db: Session = Depends(get_db),
):
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return render("signup.html", request, {
            "user": None,
            "error": "Email already registered",
        })
    if len(password) < 8:
        return render("signup.html", request, {
            "user": None,
            "error": "Password must be at least 8 characters",
        })
    user = User(
        name=name,
        email=email,
        hashed_password=hash_password(password),
        role=UserRole(role),
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=str(user.id), role=user.role.value)
    return redirect_with_cookie("/dashboard", token)


@router.post("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("access_token")
    return response


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_optional_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    now = datetime.now(timezone.utc)
    base_query = db.query(Task).options(joinedload(Task.project))
    if user.role == UserRole.member:
        base_query = base_query.filter(Task.assignee_id == user.id)

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

    return render("dashboard.html", request, {
        "user": user,
        "summary": summary,
        "tasks": tasks,
    })


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

@router.get("/projects", response_class=HTMLResponse)
def projects_page(request: Request, db: Session = Depends(get_db)):
    user = get_optional_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    projects = db.query(Project).all()
    return render("projects.html", request, {
        "user": user,
        "projects": projects,
    })


@router.get("/projects/new", response_class=HTMLResponse)
def new_project_page(request: Request, db: Session = Depends(get_db)):
    user = get_optional_user(request, db)
    if not user or user.role != UserRole.admin:
        return RedirectResponse(url="/dashboard", status_code=302)
    return render("projects.html", request, {
        "user": user,
        "projects": db.query(Project).all(),
        "show_form": True,
    })


@router.post("/projects/new", response_class=HTMLResponse)
def create_project_submit(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_optional_user(request, db)
    if not user or user.role != UserRole.admin:
        return RedirectResponse(url="/dashboard", status_code=302)
    project = Project(name=name, description=description, owner_id=user.id)
    db.add(project)
    db.commit()
    return RedirectResponse(url="/projects", status_code=302)


@router.get("/projects/{project_id}", response_class=HTMLResponse)
def project_detail(request: Request, project_id: uuid.UUID, db: Session = Depends(get_db)):
    user = get_optional_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse(url="/projects", status_code=302)
    tasks = (
        db.query(Task)
        .options(joinedload(Task.assignee))
        .filter(Task.project_id == project_id)
        .all()
    )
    return render("project_detail.html", request, {
        "user": user,
        "project": project,
        "tasks": tasks,
    })


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@router.get("/projects/{project_id}/tasks/new", response_class=HTMLResponse)
def new_task_page(request: Request, project_id: uuid.UUID, db: Session = Depends(get_db)):
    user = get_optional_user(request, db)
    if not user or user.role != UserRole.admin:
        return RedirectResponse(url="/dashboard", status_code=302)
    project = db.query(Project).filter(Project.id == project_id).first()
    members = db.query(User).all()
    return render("project_detail.html", request, {
        "user": user,
        "project": project,
        "tasks": db.query(Task).options(joinedload(Task.assignee)).filter(Task.project_id == project_id).all(),
        "members": members,
        "show_task_form": True,
    })


@router.post("/projects/{project_id}/tasks/new", response_class=HTMLResponse)
def create_task_submit(
    request: Request,
    project_id: uuid.UUID,
    title: str = Form(...),
    description: str = Form(""),
    due_date: str = Form(""),
    assignee_id: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_optional_user(request, db)
    if not user or user.role != UserRole.admin:
        return RedirectResponse(url="/dashboard", status_code=302)
    task = Task(
        title=title,
        description=description or None,
        due_date=datetime.fromisoformat(due_date) if due_date else None,
        project_id=project_id,
        assignee_id=uuid.UUID(assignee_id) if assignee_id else None,
    )
    db.add(task)
    db.commit()
    return RedirectResponse(url=f"/projects/{project_id}", status_code=302)


@router.get("/tasks/{task_id}/edit", response_class=HTMLResponse)
def edit_task_page(request: Request, task_id: uuid.UUID, db: Session = Depends(get_db)):
    user = get_optional_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return RedirectResponse(url="/dashboard", status_code=302)
    if user.role == UserRole.member and task.assignee_id != user.id:
        return RedirectResponse(url="/dashboard", status_code=302)
    members = db.query(User).all()
    return render("task_edit.html", request, {
        "user": user,
        "task": task,
        "members": members,
        "statuses": [s.value for s in TaskStatus],
    })


@router.post("/tasks/{task_id}/edit", response_class=HTMLResponse)
def edit_task_submit(
    request: Request,
    task_id: uuid.UUID,
    title: str = Form(...),
    description: str = Form(""),
    status_val: str = Form(..., alias="status"),
    due_date: str = Form(""),
    assignee_id: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_optional_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return RedirectResponse(url="/dashboard", status_code=302)

    if user.role == UserRole.member:
        if task.assignee_id != user.id:
            return RedirectResponse(url="/dashboard", status_code=302)
        task.status = TaskStatus(status_val)
    else:
        task.title = title
        task.description = description or None
        task.status = TaskStatus(status_val)
        task.due_date = datetime.fromisoformat(due_date) if due_date else None
        task.assignee_id = uuid.UUID(assignee_id) if assignee_id else None

    db.commit()
    return RedirectResponse(url=f"/projects/{task.project_id}", status_code=302)