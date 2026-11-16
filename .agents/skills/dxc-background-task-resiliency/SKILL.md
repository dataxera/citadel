---
name: Citadel Background Task Resiliency
description: Patterns and rules for building crash-resilient, idempotent, and resumable long-running Celery background tasks that survive backend and worker restarts.
---

# Citadel Background Task Resiliency

Long-running or multi-step background workflows (e.g., cluster integration sync, platform provisioning, multi-stage pipelines) **must** survive FastAPI backend restarts, Celery worker restarts, and pod evictions without getting stuck in `in_progress`.

## 1. Core Principles

1. **Database as Source of Truth**:
   - Persist workflow and per-step progress in PostgreSQL (e.g., a JSON state column like `sync_state` on `K8sClusterStatus`), **not** in process memory or Celery result backends alone.
   - Always include `status`, `updated_at` (ISO 8601 UTC timestamp), and per-step `status`, `updated_at`, and `attempts`.
   - Update persisted state under a row lock (`select(...).with_for_update()`) and `flag_modified(model, "<json_col>")`.
2. **Idempotency & Step Skipping**:
   - Every task and underlying action (e.g. `helm upgrade --install`, `kubectl apply`, ArgoCD Application upsert) must be safe to re-run if interrupted mid-flight.
   - Before executing a step, check the persisted state: if the step (or overall workflow) is already `completed` (or `error`), return early without re-running it.
3. **Celery At-Least-Once Delivery**:
   - Configure `@app.task(acks_late=True, reject_on_worker_lost=True)` (and `task_acks_late=True`, `task_reject_on_worker_lost=True`, `worker_prefetch_multiplier=1` in `backend/src/citadel/celery_app.py`) so unacknowledged tasks are re-queued if a worker dies unexpectedly.
4. **Distributed Locking with Heartbeat (`tasks/resiliency.py`)**:
   - Use `acquire_task_lock`, `run_with_lock_heartbeat`, `release_task_lock`, and `is_task_locked` from `backend/src/citadel/tasks/resiliency.py`.
   - Locking prevents duplicate concurrent execution across workers or recovery sweeps, while the heartbeat (default TTL `120s`, refreshed every `30s`) ensures a crashed worker's lock expires automatically.
   - Always release the lock in a `finally` block.

## 2. Recovery Architecture

Every resumable workflow must implement a recovery task (e.g., `recover_stuck_sync_tasks(stale_seconds: int = 60)`) wired into **all four** recovery triggers:

1. **FastAPI Startup (`backend/src/citadel/app.py`)**:
   - In `lifespan`, enqueue recovery with `stale_seconds=0` (wrapped in `try/except` so startup never fails if the broker is temporarily unreachable).
2. **Celery Worker Ready (`backend/src/citadel/celery_app.py`)**:
   - Connect `@worker_ready.connect` to dispatch recovery via `app.send_task(..., kwargs={"stale_seconds": 0})`.
3. **Periodic Beat Watchdog (`backend/src/citadel/celery_app.py`)**:
   - Register a periodic task in `beat_schedule` (e.g. every `60.0` seconds) with `stale_seconds=60` so tasks sitting briefly in the Celery queue are not prematurely re-dispatched, while orphaned tasks are recovered automatically.
4. **Manual Resume Action & UI Trigger**:
   - Expose a `resume_*` action (e.g., `resume_sync_core_integrations`) available only when `status == "in_progress"`, and provide a UI `RESUME` button so operators can manually nudge recovery if needed.

## 3. Recovery Algorithm Checklist

When writing `_recover_stuck_*_tasks(stale_seconds: int = 60)`:

1. Query rows where `state["status"] == "in_progress"`.
2. If all steps are already in `{"completed", "failed"}`, reconcile totals and finalize top-level `status` (`"completed"` or `"error"`) and `completed_at`.
3. For each incomplete step (`"pending"` or `"running"`):
   - Skip if `is_task_locked(lock_key)` is `True` (a live worker is actively running it).
   - Skip if `stale_seconds > 0` and `step["updated_at"]` is newer than `stale_seconds` (recently queued/updated).
   - Touch `step["updated_at"] = ts_now().isoformat()` and commit **before** calling `.delay(...)` to prevent duplicate dispatches on overlapping sweeps.
   - Respect dependency order (e.g., ensure prerequisite like ArgoCD completes before dispatching parallel subtasks).

## 4. Reference Implementation

- Resiliency primitives: `backend/src/citadel/tasks/resiliency.py`
- Cluster sync tasks & recovery: `backend/src/citadel/tasks/k8s_cluster_status.py`
- Actions: `backend/src/citadel/service/k8s_cluster/actions.py`
- Startup & beat hooks: `backend/src/citadel/app.py`, `backend/src/citadel/celery_app.py`

## 5. Required Unit Tests

Every resilient background workflow must include `pytest` tests verifying:
1. **Partial-progress resume**: Completed steps are skipped; interrupted `"running"` and `"pending"` steps are re-dispatched.
2. **Active-lock protection**: Steps currently locked by a live worker are not duplicated by recovery.
3. **Idempotent duplicate delivery**: Re-running a task for an already-completed or locked step is a no-op.
4. **State reconciliation**: If all steps finished before the top-level status was finalized, recovery reconciles and closes the workflow.
5. **Manual resume action**: Action is available only while `in_progress` and enqueues immediate recovery (`stale_seconds=0`).
