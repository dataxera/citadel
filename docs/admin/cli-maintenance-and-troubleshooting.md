<!--
SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
SPDX-License-Identifier: AGPLv3+
-->

# CLI Reference, Maintenance & Troubleshooting

This chapter provides a complete reference for the `mindweaver` command-line interface, routine maintenance procedures, background task management, and troubleshooting runbooks for known operational issues.

---

## 1. Mindweaver CLI Reference

All CLI commands are executed from the `backend/` directory (or inside the Mindweaver container at `/app`) using `uv run mindweaver <command>`:

### Application & Worker Commands

| Command | Options | Description |
| :--- | :--- | :--- |
| `uv run mindweaver run` | `-b, --bind <host>` (default `127.0.0.1`)<br>`-p, --port <port>` (default `8000`)<br>`-l, --log-file <path>` (default `logs/mindweaver.log`) | Starts the FastAPI application with Uvicorn and file/console logging. |
| `uv run mindweaver scheduler` | `--reload` | Starts the Celery Beat scheduler (`mindweaver.celery_app`). If `MINDWEAVER_EMBEDDED_WORKER=true`, also spawns a background Celery worker. |
| `uv run mindweaver worker` | `--reload` | Starts the Celery worker process (`--pool=solo --loglevel=info`). |
| `uv run mindweaver queue flush` | *(None)* | Purges all pending tasks from the Celery task queue in Redis/Valkey. |

### Database Migration Commands (`db`)

All `db` subcommands accept `-f / --config <path/to/alembic.ini>` before the subcommand if `alembic.ini` is not in the current working directory.

| Command | Options | Description |
| :--- | :--- | :--- |
| `uv run mindweaver db migrate` | *(None)* | Upgrades the PostgreSQL schema to the latest Alembic `heads`. Safe to run idempotently on every deployment. |
| `uv run mindweaver db downgrade` | `-r, --revision <rev>` *(Required)* | Downgrades the database schema to a specific revision ID, `base`, or relative step (e.g., `-1`). |
| `uv run mindweaver db history` | `-v, --verbose`<br>`-c, --current` | Lists the Alembic migration history and optionally highlights the current revision. |
| `uv run mindweaver db revision` | `-m, --message <msg>` *(Required)*<br>`-a, --autogenerate` | Generates a new Alembic migration script in `backend/migration/versions/`. |
| `uv run mindweaver db reset` | *(None)* | **Destructive (Dev Only)**: Drops and recreates the `public` schema. Only registered when `MINDWEAVER_ENABLE_DB_RESET=true`. |

### Cryptography Commands (`crypto`)

| Command | Options | Description |
| :--- | :--- | :--- |
| `uv run mindweaver crypto generate-key` | *(None)* | Generates a new Fernet key and prints `MINDWEAVER_FERNET_KEY=<key>`. |
| `uv run mindweaver crypto rotate-key` | `--old-key <key>` *(Required)*<br>`--new-key <key>` *(Required)* | Decrypts stored data source passwords using `--old-key` and re-encrypts them using `--new-key`. |

### Stack Commands (`stack`)

| Command | Options | Description |
| :--- | :--- | :--- |
| `uv run mindweaver stack import` | `--path <dir>` (optional) | Imports or updates stack YAML definitions from `backend/src/mindweaver/resources/stacks/` (or the specified `--path`). |

---

## 2. Background Tasks & Queue Maintenance

Mindweaver's `celery_app.py` configures three periodic tasks executed by **Celery Beat**:

| Schedule Name | Task Path | Interval | Purpose |
| :--- | :--- | :--- | :--- |
| `poll-all-platforms-15s` | `mindweaver.tasks.platform_status.poll_all_platforms` | Every `15s` | Queries Kubernetes for the live readiness, endpoints, node ports, and credentials of all active platform services. Expires after `MINDWEAVER_STATUS_POLLING_EXPIRY` (`60s`). |
| `poll-all-k8s-clusters-15s` | `mindweaver.tasks.k8s_cluster_status.poll_all_k8s_clusters` | Every `15s` | Queries all registered Kubernetes clusters for node readiness, CPU/RAM metrics, and installed operator versions. Expires after `60s`. |
| `scan-and-clean-names-daily` | `mindweaver.tasks.name_tracker.scan_and_clean_names_task` | Every `24h` (`86400s`) | Reconciles `mw_name_tracker` against all platform tables and removes orphaned names. |

### Flushing a Backlogged Queue
If a Celery worker was offline for an extended period and you want to clear queued tasks before restarting workers:

```bash
uv run mindweaver queue flush
```

---

## 3. Database Backup & Recovery

Because Mindweaver stores all platform metadata, encrypted credentials, and cluster configurations in its PostgreSQL database (`mindweaver`), regular backups of PostgreSQL and secure offline storage of `MINDWEAVER_FERNET_KEY` are critical.

> [!CAUTION]
> A database backup is **unrecoverable** for encrypted fields (`kubeconfig`, passwords, private keys) without the matching `MINDWEAVER_FERNET_KEY` that was active when the backup was taken. Always back up your `MINDWEAVER_FERNET_KEY` in a secure enterprise vault alongside your database snapshots.

### Backing Up PostgreSQL
```bash
pg_dump -h <db-host> -U <db-user> -d mindweaver -Fc -f mindweaver_$(date +%Y%m%d_%H%M%S).dump
```

### Restoring PostgreSQL
```bash
pg_restore -h <db-host> -U <db-user> -d mindweaver --clean --if-exists mindweaver_<timestamp>.dump
# Run migrations in case the control plane image was upgraded since the backup:
uv run mindweaver db migrate
```

---

## 4. Troubleshooting Runbook

### Issue 1: NiFi Cluster Fails to Redeploy with JKS Secret or X.509 PEM Error

**Symptoms:**
When deploying an Apache NiFi cluster with the **same name** as a previously decommissioned NiFi cluster, the NiFiKop operator fails with one of the following errors:
- `"could not create secret with jks password: secrets already exists"`
- `"failed to decode x509 certificate from PEM"`

**Root Cause:**
When NiFiKop uses `sslSecrets.create: true` with an external `issuerRef`, its `FinalizePKI` cleanup routine does not delete the per-node JKS password secrets (`{nifi-name}-{nodeId}-server-certificate`) upon decommissioning.

**Resolution:**
Manually delete the stale per-node certificate secret(s) in the project's Kubernetes namespace before redeploying:

```bash
kubectl delete secret <nifi-name>-0-server-certificate -n <project-namespace>
# If replica_count > 1, delete for each node index (0, 1, 2, ...):
kubectl get secrets -n <project-namespace> | grep "<nifi-name>-.*-server-certificate"
```

---

### Issue 2: Cannot Decommission a Platform Service (Dependency or Unreachable Cluster)

**Case A: Active Dependent Services Exist**
- **Symptom**: Decommissioning PostgreSQL or Hive Metastore returns:
  `Cannot decommission <name>: dependent service(s) '<consumer>' (<type>) are not decommissioned yet.`
- **Resolution**: Even with **Force Decommission** (`force=True`), Mindweaver prohibits decommissioning a service while downstream consumers are still active. Decommission the listed consumer services first (e.g., Superset, Airflow, Trino), and then decommission the underlying database or metastore.

**Case B: Target Kubernetes Cluster is Offline or Deleted**
- **Symptom**: Standard decommissioning fails with `Kubernetes cluster is unreachable: ...`.
- **Resolution**: Ensure all dependent services are decommissioned first, then use the **Force Decommission** option in the UI (or pass `{"force": true}` with header `X-RESOURCE-NAME: <name>` to `POST /api/v1/platform/{service}/{id}/_decommission`). This bypasses the unreachable cluster error and marks the service as decommissioned in Mindweaver so its record can be cleaned up.

---

### Issue 3: Project Certificate Shows `INVALID_SIGNATURE` or `CA_INVALID`

**Symptoms:**
In the Project Certificate Manager view (`/_cert_manager` or `/_certificate_details`), one or more service TLS certificates show `Invalid` / `INVALID_SIGNATURE` with the message:
`"Certificate AKI does not match active Project CA SKI"` or `"Cryptographic signature verification failed: Certificate was not signed by the current Project CA."`

**Root Cause:**
The project's CA secret (`{project}-ca-secret`) was recreated or rotated, leaving older leaf certificates signed by the previous CA.

**Resolution:**
1. In the Project's **Certificates** tab, click **Renew** (`POST /api/v1/projects/{id}/_renew_certificate`) on each affected certificate, **or**
2. Trigger a re-deploy (`_deploy`) on the affected platform service, which automatically invokes `reconcile_manifest_certificates` to detect the CA mismatch and reissue the certificate via Cert-Manager.

---

### Issue 4: Celery Worker or API Fails on Startup with Encryption / Fernet Error

**Symptoms:**
The FastAPI backend, Celery Worker, or Celery Beat exits during startup inside `_get_fernet_instance()`.

**Root Cause:**
`MINDWEAVER_FERNET_KEY` is missing, empty, or not a valid 32-byte URL-safe base64-encoded Fernet key, or the Worker and API containers have different `MINDWEAVER_FERNET_KEY` values configured.

**Resolution:**
Generate a valid key via `uv run mindweaver crypto generate-key` and ensure the exact same `MINDWEAVER_FERNET_KEY` value is provided to the `web`, `worker`, and `scheduler` (beat) deployments.
