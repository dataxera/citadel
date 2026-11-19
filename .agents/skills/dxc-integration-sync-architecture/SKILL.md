---
name: Citadel Integration Sync Architecture
description: End-to-end architecture for multi-step integration syncs using an orchestrator, per-integration subtasks, distributed Redis locking, buffered log streaming, stuck-task recovery, and collapsible progress UI.
---

# Citadel Integration Sync Architecture

Use this architecture whenever a service deploys or reconciles multiple Kubernetes/platform integrations asynchronously (as implemented in `k8s_cluster` and `project`). It builds on [Citadel Background Task Resiliency](../dxc-background-task-resiliency/SKILL.md) and adds concrete patterns for orchestrator/subtask fan-out, buffered log streaming, Celery model registration, and frontend progress UI.

## 1. Data Model & API Exposure

1. **Persistent `sync_state` JSON Column**:
   - Store `sync_state: dict[str, Any] = Field(default_factory=dict, sa_type=JSONType())` on the model (or dedicated status model) with an Alembic migration (`server_default=sa.text("'{}'")`, `nullable=False`).
   - Hide `sync_state` from CRUD forms and user payloads on the `Service`:
     ```python
     @classmethod
     def internal_fields(cls) -> list[str]:
         return super().internal_fields() + ["sync_state"]

     @classmethod
     def hidden_fields(cls) -> list[str]:
         return super().hidden_fields() + ["sync_state"]
     ```
2. **State Endpoint (`/_state`)**:
   - Expose `"sync_state": model.sync_state or {}` alongside `"integrations_status"` from `BaseState.get()`.
3. **Initial Payload (`build_initial_*_sync_state`)**:
   ```python
   {
       "status": "in_progress",  # in_progress | completed | error
       "started_at": now_iso,
       "updated_at": now_iso,
       "completed_at": None,
       "total": len(INTEGRATIONS),
       "completed": 0,
       "tasks": {
           key: {
               "label": label,
               "status": "pending",  # pending | running | completed | failed
               "message": None,
               "logs": None,
               "updated_at": now_iso,
               "attempts": 0,
           }
           for key, label in INTEGRATIONS
       },
   }
   ```

## 2. Celery Worker Model Registration (Critical)

- Celery workers import `citadel.celery_app` (`include=[...]`), **not** `citadel.app`.
- Any task module that queries or commits a SQLModel with foreign keys (e.g., `Project` referencing `dxc_k8s_cluster`, `dxc_ldap_config`, `dxc_stack`) **must** import those referenced model modules at module level in the task file; otherwise `await session.commit()` will raise `sqlalchemy.exc.NoReferencedTableError` in the worker.

## 3. Orchestrator + Per-Integration Subtask Pattern

1. **Action (`sync_*_integrations`)**:
   - `__call__()` initializes `sync_state = build_initial_*_sync_state()`, calls `flag_modified(model, "sync_state")`, `await self.session.flush()` (never `commit()` inside FastAPI view actions), and dispatches `orchestrator_task.delay(model.id)`.
   - Provide `run_integration(key)` (with `self.log_callback`) to execute a single integration idempotently, and `run()` for sequential direct execution.
2. **Orchestrator Task (`@app.task(acks_late=True, reject_on_worker_lost=True)`)**:
   - Acquire an orchestrator lock (`acquire_task_lock(f"{prefix}:{id}:__orchestrator__", ttl=120)`), releasing in `finally`.
   - Use `AsyncSession(engine, expire_on_commit=False)` so `session.commit()` never expires model attributes.
   - Run any prerequisite integration first (e.g., `argocd` for clusters, `namespace` for projects) under `run_with_lock_heartbeat(lock_key, lambda: action.run_integration(prereq_key))`.
   - If the prerequisite fails, mark remaining `pending`/`running` tasks as `failed` (`mark_remaining_failed_on_error=True`) and return.
   - Once the prerequisite is `completed`, refresh the model and dispatch `subtask.delay(id, key)` for each remaining incomplete (`not in ("completed", "failed")`), unlocked (`not await is_task_locked(...)`) integration.
3. **Subtask (`@app.task(acks_late=True, reject_on_worker_lost=True)`)**:
   - Acquire per-integration lock (`acquire_task_lock(f"{prefix}:{id}:{key}", ttl=120)`).
   - Skip early if top-level `sync_state["status"] in ("completed", "error")` or the task itself is already `"completed"`.
   - Mark task `"running"`, stream logs with `_SyncTaskLogStreamer`, execute `run_with_lock_heartbeat(lock_key, lambda: action.run_integration(key))`, flush logs, and mark `"completed"` (or `"failed"` on exception).

## 4. Row-Locked Updates & Buffered Log Streaming

- **Row Locking**: All `sync_state` mutations (`_update_*_sync_task_state`, `_append_*_sync_task_logs`) must query with `.with_for_update()`, `copy.deepcopy(model.sync_state)`, `flag_modified(model, "sync_state")`, and `await session.commit()`.
- **Buffered Log Streamer**: Buffer stdout/stderr chunks behind an `asyncio.Lock` and flush to PostgreSQL every `0.25s` (with a trailing timer task and final `await streamer.flush()` in `try/except`), capping stored logs at `MAX_SYNC_LOG_CHARS = 100_000` from the front (`_trim_sync_logs`).
- **Subprocess Safety**: Apply a timeout (e.g., `asyncio.wait_for(proc.communicate(), timeout=60)`) on CLI subprocesses so a hung command cannot wedge a `--pool=solo` worker.

## 5. Recovery Wiring

- Implement `recover_stuck_*_sync_tasks(stale_seconds=60, id=None)` to:
  1. Finalize if the prerequisite failed.
  2. Re-dispatch the orchestrator if the prerequisite is incomplete, unlocked, and stale.
  3. Reconcile totals if all tasks are done.
  4. Re-dispatch any incomplete, unlocked, stale subtasks.
- Wire recovery into:
  - `beat_schedule` in `backend/src/citadel/celery_app.py` (every `60.0`s).
  - `@worker_ready.connect` in `backend/src/citadel/celery_app.py` (`stale_seconds=0`).
  - A `resume_sync_*` action on the service calling `recover_stuck_*_sync_tasks.delay(stale_seconds=0, <id_kwarg>=self.model.id)`.

## 6. Frontend Progress & Accordion UI

- **Polling**: Use `useVisibilityPolling` on `/_state` to stream `sync_state` updates.
- **Sync Alert Suppression**: Do not show the "Integrations Require Sync" amber alert while `sync_state.status === 'in_progress'`.
- **Collapsible Progress Accordion**:
  - Render the progress widget whenever `sync_state.total > 0` (do **not** hide it after completion).
  - Keep it **expanded** when `in_progress` or `error`, and **keep it expanded** if it completes during the active session (`syncAccordionExpanded` set to `true` when `in_progress`/`error` is observed or sync is triggered).
  - Default to **collapsed** (`syncAccordionExpanded === null` -> `syncStatus !== 'completed'`) when the page is loaded/refreshed and no tasks are running.
  - Render clickable task chips (`pending`, `running`, `completed`, `failed`) that open a **Sync Details Modal** with status badge, error/message box, copy-logs button, and auto-scrolling log viewer (`<pre>`).
- **Header `RESUME` Button**: Render inside the progress header when `syncState.status === 'in_progress'` (calling `e.stopPropagation()` so it doesn't toggle the accordion).

## 7. Reference Implementations

- **K8s Cluster**: `backend/src/citadel/tasks/k8s_cluster_status.py`, `backend/src/citadel/service/k8s_cluster/actions.py`, `frontend/src/pages/k8s_clusters/ServiceView.jsx`
- **Project**: `backend/src/citadel/tasks/project_tasks.py`, `backend/src/citadel/service/project/actions.py`, `frontend/src/pages/projects/ServiceView.jsx`
