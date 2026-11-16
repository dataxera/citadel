---
name: Citadel Status Polling & Deduplication
description: Rules and patterns for frontend visibility-aware polling (max once every 3s) and backend Redis-deduplicated Celery polling across multiple users.
---

# Citadel Status Polling & Deduplication

When adding or updating live status/state views (e.g., `k8s_cluster`, platform services) that poll external systems such as Kubernetes:

## 1. Core Rules

1. **Page-Loaded & Visibility-Gated Only**:
   - Polling must **only** run while the detail/status page is mounted/active and the browser tab is visible (`!document.hidden`).
   - Do **not** schedule periodic background polling (e.g., Celery Beat) for UI status views when no user is viewing the page.
2. **3-Second Maximum Cadence**:
   - Frontend polling interval must be at least **3 seconds** (`DEFAULT_POLL_INTERVAL_MS = 3000`).
   - Backend cooldown must enforce `settings.status_polling_interval` (`3` seconds) per resource.
3. **Multi-User Deduplication**:
   - Multiple users (or multiple tabs) viewing the same resource simultaneously must **not** trigger duplicate Kubernetes/external polls.
   - `GET .../_state` must return cached database state immediately and enqueue a background Celery task via `poll_coordinator.py` **only** if no in-flight lock exists and the cooldown key can be acquired atomically.

## 2. Frontend Pattern

Use `useVisibilityPolling` from `frontend/src/hooks/useStatePolling.js`:

```jsx
import { useVisibilityPolling } from '../../hooks/useStatePolling';

const pollState = useCallback(() => {
    if (!selectedId || !getState) return;
    getState(selectedId).then(setState).catch(console.error);
}, [selectedId, getState]);

useVisibilityPolling(pollState, Boolean(selectedId && getState));
```

- `DEFAULT_POLL_INTERVAL_MS` is `3000` ms.
- Automatically stops on unmount and pauses when `document.hidden` is `true`.

## 3. Backend Pattern

1. **Service Hook (`on_state_requested`)**:
   - In the service class (e.g. `K8sClusterService.on_state_requested` in `backend/src/citadel/service/k8s_cluster/service.py`), trigger deduplicated polling via `backend/src/citadel/tasks/poll_coordinator.py` (`schedule_k8s_cluster_poll` or `schedule_platform_poll`).
2. **Coordinator (`backend/src/citadel/tasks/poll_coordinator.py`)**:
   - Uses Redis keys:
     - `mw:poll:lock:{resource_key}` (TTL `settings.status_polling_expiry = 60`s) — prevents concurrent duplicate tasks while a poll is in flight.
     - `mw:poll:cooldown:{resource_key}` (`SET ... NX EX settings.status_polling_interval`, `3`s) — enforces at most one poll every 3 seconds across all users/tabs.
   - Celery task acquires the lock via `acquire_poll_lock(resource_key)` and always releases it in `finally` via `release_poll_lock(resource_key)`.
3. **Preserve State on Error**:
   - If a background poll fails (e.g. cluster unreachable), update `status = "error"` and `message`, and **preserve** existing cached metrics/topology fields (`nodes_status`, `nodes_details`, `cpu_total`, etc.).
