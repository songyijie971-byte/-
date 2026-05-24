# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

智慧课堂行为识别与分析系统 — a Flask web app for classroom behavior detection and analysis. Uses YOLO (ONNX) or Roboflow hosted inference to detect student behaviors (phone use, sleeping, head-down, hand-raising, turn-talk) from webcam streams or uploaded videos. Built for a Chinese undergraduate graduation project (毕设).

## Commands

### Run (SQLite, quickest for dev)
```bash
set DATABASE_URL=sqlite:///classroom_demo.db
python app.py
# or PowerShell:
.\scripts\run_sqlite.ps1
```

### Run tests
```bash
python -m unittest discover -s tests -p "test_*.py" -q
# or PowerShell:
.\scripts\test.ps1
```

### Docker
```bash
docker compose up          # MySQL + app (requires .env with passwords)
docker compose up --build  # rebuild after code changes
```

## Architecture

### Entry Points
- `app.py` — thin entry point, imports `create_app()` from `webapp.py` and runs Flask dev server
- `webapp.py` — the real application bootstrap: creates Flask app, loads `RuntimeConfig`, builds `AppContext` and `DEPENDENCIES` service registry, wires all routes and error handlers

### Layering Pattern
Routes → Services → Database/Storage. There is no ORM repository abstraction layer; services call SQLAlchemy session_scope directly.

- **Routes** (`*_routes.py`): HTTP request handling, input validation, response formatting. Four modules: `analysis_routes`, `auth_routes`, `config_routes`, `report_routes`.
- **Services** (`*_service.py`): Business logic. Six modules: `analysis_service`, `auth_service`, `camera_service`, `config_service`, `report_service`, `security_service`.
- **`app_core/`**: Lower-level infrastructure — `context.py` (AppContext dataclass with shared state), `registry.py` (builds and wires the DEPENDENCIES dict), `job_executor.py` (thread/process/queue backends for background analysis), `analysis_workflow.py` (video analysis pipeline), `inference_runtime.py` (device selection, ONNX inference), `detection_models.py` (Roboflow hosted model wrapper), `file_queue.py` (JSON file-based job queue), `queue_worker.py` (standalone queue consumer), `maintenance.py` (orphan cleanup), `repositories.py` (DB query helpers).

### Key Domain Modules
- `behavior_core.py` — maps YOLO class IDs/names to behavior keys, temporal analysis rules, `BehaviorTemporalAnalyzer` for consecutive-frame detection
- `focus_score.py` — calculates a 0–100 focus score from behavior counts (penalty-based formula)
- `database.py` — SQLAlchemy models (`User`, `AlertEvent`, `SystemConfig`, `VideoAnalysisJob`, `AnalysisReport`), engine/session factory creation, DB init, seed logic
- `storage.py` — `EventStorage` for saving alert snapshots to disk
- `app_config.py` — `RuntimeConfig` dataclass, reads all env vars with defaults

### Dependency Injection
`webapp.py` builds a `DEPENDENCIES` dict (via `app_core/registry.py`) containing all service functions and shared references. Stored in `app.extensions["classroom_demo.dependencies"]`. Routes access it via `current_app.extensions["classroom_demo.dependencies"]`.

### Shared State
`AppContext` (in `app_core/context.py`) holds mutable shared state: the SQLAlchemy engine, session factory, current stats dict, runtime refs (model state, camera status), and several locks (stats_lock, runtime_lock, frame_lock, model_lock, etc.). Stored in `app.extensions["classroom_demo.context"]`.

### Inference Providers
Two backends configured via `INFERENCE_PROVIDER` env var:
- `local` — loads `best.onnx` with ultralytics YOLO
- `roboflow` — calls Roboflow hosted API (requires `ROBOFLOW_API_KEY`)

### Background Job Execution
Configured via `JOB_EXECUTOR_BACKEND`:
- `thread` (default) — runs analysis in a thread pool
- `process` — uses `ProcessPoolExecutor`
- `queue` — writes JSON to `data/job_queue/pending/`, requires separate `python -m app_core.queue_worker` process

### Auth & Roles
Three roles: `admin`, `teacher`, `user`. Default admin seeded on startup (`admin`/`admin123456`, forced password change on first login). Role-based access controls camera access (admin + teacher only by default).

### Frontend
Server-rendered Jinja2 templates in `templates/` with a `layout/base.html` base. Client-side JS in `static/js/` handles polling, DOM updates, and API calls. CSS tokens in `static/css/tokens.css`.

## Key Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///classroom_demo.db` | DB connection string |
| `YOLO_MODEL_PATH` | `best.onnx` | Local ONNX model path |
| `INFERENCE_PROVIDER` | `local` | `local` or `roboflow` |
| `ROBOFLOW_API_KEY` | — | Roboflow hosted inference key |
| `JOB_EXECUTOR_BACKEND` | `thread` | `thread` / `process` / `queue` |
| `MAX_UPLOAD_SIZE_MB` | `200` | Upload size limit |
| `CAMERA_INDEX` / `CAMERA_BACKEND` | `0` / `auto` | Webcam config |
| `FLASK_SECRET_KEY` | auto-generated | Session secret |

## Conventions

- Python 3.10+, Flask 2.3–3.0, SQLAlchemy 1.4–2.0, ultralytics 8.x
- No linting/formatting tooling configured; follow existing code style (4-space indent, no trailing commas in dicts)
- All Chinese UI strings are hardcoded inline (no i18n framework)
- Tests use `unittest` (no pytest), run from project root
- The `calculate_focus_score` in `webapp.py` delegates to `focus_score.py` — always use the shared version
