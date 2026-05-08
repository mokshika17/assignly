# Assignly

> A full-stack team task management web application with role-based access control, built with FastAPI and PostgreSQL.

**Live Demo:** [assignly-production.up.railway.app](https://assignly-production.up.railway.app)  
**GitHub:** [github.com/mokshika17/assignly](https://github.com/mokshika17/assignly)

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [API Reference](#api-reference)
- [Role-Based Access Control](#role-based-access-control)
- [Database Schema](#database-schema)
- [Deployment](#deployment)
- [Project Structure](#project-structure)

---

## Overview

Assignly is a team task management platform where admins create projects, assign tasks to team members, and track progress across the full task lifecycle. Members log in and see only what is assigned to them.

Built as a full-stack application with a REST API backend, server-rendered UI via Jinja2 templates, and PostgreSQL persistence — deployed on Railway.

---

## Features

### Authentication
- JWT-based login and signup
- Remember Me — 30-day persistent cookie vs session cookie
- Secure httponly cookies, bcrypt password hashing
- Rate limiting on auth endpoints

### Projects
- Admin can create, edit, and delete projects
- Members see only projects where they have assigned tasks
- Full CRUD via REST API

### Tasks
- Full lifecycle: `todo` → `in_progress` → `done`
- Task assignment to team members
- Due date tracking with overdue detection
- `completed_at` timestamp stamped on status change to done
- Days late computed on completion

### Dashboard
- Per-user task summary (total, todo, in progress, done, overdue)
- Clickable task titles with project context
- Role-scoped view — admins see all, members see their own

### Analytics (Admin only)
- Summary metrics — completion rate, avg lateness, overdue count
- Per-project completion rate bar chart
- Tasks completed over last 30 days line chart
- Per-project breakdown table
- Per-assignee breakdown table with overdue highlights

### Role-Based Access Control
- Two roles: `admin` and `member`
- Enforced at every API route and every page route
- Members cannot access admin-only pages or mutate others' data

### Production Quality
- Structured JSON logging
- Request ID middleware (X-Request-ID header)
- Global exception handlers with consistent error shapes
- Pydantic BaseSettings for config management
- Alembic database migrations
- Redis caching layer (graceful fallback if unavailable)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend framework | FastAPI 0.136+ |
| Database | PostgreSQL |
| ORM | SQLAlchemy |
| Migrations | Alembic |
| Authentication | JWT (python-jose) + bcrypt (passlib) |
| Frontend | Jinja2 templates + Pico CSS |
| Caching | Redis (optional) |
| Rate limiting | SlowAPI |
| Deployment | Railway |
| Config | Pydantic BaseSettings |

---

## Architecture

```
Browser
  │
  ▼
FastAPI App (Uvicorn)
  ├── /api/*          → JSON REST API (auth, projects, tasks, analytics)
  └── /*              → Server-rendered HTML pages (Jinja2)
  │
  ├── SQLAlchemy ORM
  │     └── PostgreSQL
  │
  └── Redis (optional cache)
```

All API routes live under `/api` to avoid conflicts with page routes. Page routes render Jinja2 templates and read auth state from the JWT cookie.

---

## Getting Started

### Prerequisites

- Python 3.11+
- PostgreSQL
- Redis (optional)

### Local Setup

```bash
# Clone the repo
git clone git@github.com:mokshika17/assignly.git
cd assignly

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment variables
cp .env.example .env
# Edit .env with your local DB credentials

# Run database migrations
alembic upgrade head

# Start the development server
uvicorn app.main:app --reload --port 8000
```

The app will be available at `http://localhost:8000`.

---

## Environment Variables

Create a `.env` file in the project root:

```env
# Application
APP_NAME=Assignly
APP_VERSION=1.0.0
DEBUG=true

# Database
DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/assignly

# Auth
SECRET_KEY=your-secret-key-min-32-chars
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Redis (optional)
REDIS_URL=redis://localhost:6379/0
```

On Railway, `DATABASE_URL` is injected automatically by the Postgres plugin.

---

## API Reference

### Auth

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/signup` | Register a new user |
| POST | `/api/auth/login` | Login and receive JWT cookie |
| POST | `/api/auth/logout` | Clear auth cookie |
| GET | `/api/auth/me` | Get current user |

### Projects

| Method | Endpoint | Description | Role |
|---|---|---|---|
| GET | `/api/projects` | List projects | Admin: all, Member: assigned |
| POST | `/api/projects` | Create project | Admin |
| GET | `/api/projects/{id}` | Get project | Admin/Member |
| PUT | `/api/projects/{id}` | Update project | Admin |
| DELETE | `/api/projects/{id}` | Delete project | Admin |

### Tasks

| Method | Endpoint | Description | Role |
|---|---|---|---|
| GET | `/api/tasks` | List tasks | Admin: all, Member: assigned |
| POST | `/api/tasks` | Create task | Admin |
| GET | `/api/tasks/{id}` | Get task | Admin/Member |
| PUT | `/api/tasks/{id}` | Update task | Admin: full, Member: status only |
| DELETE | `/api/tasks/{id}` | Delete task | Admin |

### Analytics

| Method | Endpoint | Description | Role |
|---|---|---|---|
| GET | `/api/analytics/summary` | Overall stats | Admin |
| GET | `/api/analytics/projects` | Per-project stats | Admin |
| GET | `/api/analytics/assignees` | Per-assignee stats | Admin |
| GET | `/api/analytics/timeline` | Completions last 30 days | Admin |

---

## Role-Based Access Control

| Action | Admin | Member |
|---|---|---|
| View all projects | ✅ | ❌ |
| View assigned projects | ✅ | ✅ |
| Create / edit / delete projects | ✅ | ❌ |
| View all tasks | ✅ | ❌ |
| View assigned tasks | ✅ | ✅ |
| Create / assign / delete tasks | ✅ | ❌ |
| Update task status | ✅ | ✅ (own tasks only) |
| View analytics | ✅ | ❌ |

---

## Database Schema

```
users
  id            UUID PK
  name          VARCHAR
  email         VARCHAR UNIQUE
  hashed_password VARCHAR
  role          ENUM (admin, member)
  is_active     BOOLEAN
  created_at    TIMESTAMPTZ
  updated_at    TIMESTAMPTZ

projects
  id            UUID PK
  name          VARCHAR
  description   TEXT
  owner_id      UUID FK → users.id
  created_at    TIMESTAMPTZ
  updated_at    TIMESTAMPTZ

tasks
  id            UUID PK
  title         VARCHAR
  description   TEXT
  status        ENUM (todo, in_progress, done)
  due_date      TIMESTAMPTZ
  completed_at  TIMESTAMPTZ
  project_id    UUID FK → projects.id
  assignee_id   UUID FK → users.id
  created_at    TIMESTAMPTZ
  updated_at    TIMESTAMPTZ
```

---

## Deployment

The app is deployed on [Railway](https://railway.app) with a managed PostgreSQL database.

### Deploy your own

1. Fork this repository
2. Create a new project on Railway
3. Connect your GitHub repo
4. Add a PostgreSQL plugin — Railway injects `DATABASE_URL` automatically
5. Set the remaining environment variables in Railway's Variables tab
6. Railway will build and deploy automatically on every push to `master`

Migrations run automatically on startup via `start.sh`:

```bash
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

---

## Project Structure

```
assignly/
├── app/
│   ├── main.py           # FastAPI app factory, middleware, exception handlers
│   ├── config.py         # Pydantic BaseSettings
│   ├── database.py       # SQLAlchemy engine and session
│   ├── models.py         # SQLAlchemy ORM models
│   ├── schemas.py        # Pydantic request/response schemas
│   ├── auth.py           # JWT creation, bcrypt hashing
│   ├── dependencies.py   # get_db, get_current_user, require_admin
│   ├── cache.py          # Redis cache helpers
│   ├── limiter.py        # SlowAPI rate limiter
│   ├── logger.py         # Structured logging setup
│   └── routers/
│       ├── auth.py       # /api/auth/*
│       ├── projects.py   # /api/projects/*
│       ├── tasks.py      # /api/tasks/*
│       ├── analytics.py  # /api/analytics/*
│       └── pages.py      # Server-rendered UI routes
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── signup.html
│   ├── dashboard.html
│   ├── projects.html
│   ├── project_detail.html
│   ├── task_detail.html
│   ├── task_edit.html
│   └── analytics.html
├── static/
├── alembic/
│   └── versions/
├── Procfile
├── start.sh
├── railway.toml
├── requirements.txt
└── README.md
```

---

## License

MIT
