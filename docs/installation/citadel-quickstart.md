# Citadel Quickstart (Single Node using Docker)

This guide shows how to run the **Citadel** control plane on a single host using Docker and Docker Compose. Citadel itself is lightweight; it orchestrates heavy data platform components (PostgreSQL, Kafka, Doris, Trino, Airflow, NiFi, etc.) onto one or more target Kubernetes clusters.

## Prerequisites

- **Docker Engine** 24.0+ and **Docker Compose** v2 (`docker compose`)
- Minimum host resources for Citadel control plane: **2 vCPU, 4 GB RAM, 20 GB disk**
- Network access to your target Kubernetes cluster's API server (port `6443`)

---

## Option A: Run with Docker Compose (Recommended for Quickstart)

The repository's `docker-compose.yml` runs PostgreSQL 15, Redis 7, database migrations + stack import, the FastAPI backend, Celery worker/scheduler, and the frontend.

### 1. Clone the Repository

```bash
git clone <your-citadel-repo-url> citadel
cd citadel
```

### 2. Generate the Encryption Key

Citadel encrypts sensitive credentials (kubeconfigs, S3 keys, database passwords) using Fernet symmetric encryption. Generate a key and save it to `backend/.env`:

```bash
mkdir -p backend
python3 -c "from cryptography.fernet import Fernet; print('CITADEL_FERNET_KEY=' + Fernet.generate_key().decode())" > backend/.env
```

> [!IMPORTANT]
> Back up `CITADEL_FERNET_KEY` securely. If you lose this key, previously stored credentials (such as cluster kubeconfigs and S3 secrets) cannot be decrypted.

### 3. Start Citadel

Start the full stack using the `app` profile:

```bash
docker compose --profile app up -d
```

This starts:
- `db` (`postgres:15`) on port `5432`
- `redis` (`redis:7-alpine`) on port `6379`
- `migrate` (runs `dxc db migrate` and `dxc stack import`, then exits)
- `web` (FastAPI API) on port `8000`
- `scheduler` & `worker` (Celery Beat & Worker)
- `frontend` (React UI) on port `3000`

### 4. Verify & Log In

Check that all services are healthy:

```bash
docker compose --profile app ps
```

Open the Citadel UI at:
- **UI**: `http://<host-ip>:3000`
- **API**: `http://<host-ip>:8000`

Default credentials (configured in `docker-compose.yml`):
- **Username**: `admin`
- **Password**: `password`

> [!WARNING]
> Change the default admin password immediately after first login, or override `CITADEL_DEFAULT_ADMIN_USERNAME` and `CITADEL_DEFAULT_ADMIN_PASSWORD` in `backend/.env` before starting.

---

## Option B: Single Production Container Image

If you prefer building and running the all-in-one production image defined in `Dockerfile` (Nginx + Uvicorn on port `8080`), you still need PostgreSQL and Redis reachable from the container:

### 1. Build the Image

```bash
docker build -t citadel:latest .
```

### 2. Start PostgreSQL and Redis

```bash
docker compose up -d db redis
```

### 3. Run Migrations & Start Citadel

```bash
export CITADEL_FERNET_KEY="<your-generated-fernet-key>"

# Run DB migrations and import default platform stacks
docker run --rm --network citadel_default \
  -e CITADEL_DB_HOST=db \
  -e CITADEL_DB_USER=postgres \
  -e CITADEL_DB_PASS=password \
  -e CITADEL_DB_NAME=citadel \
  -e CITADEL_FERNET_KEY="$CITADEL_FERNET_KEY" \
  citadel:latest sh -c "uv run dxc db migrate && uv run dxc stack import"

# Start the Citadel web + UI container (Nginx proxies /api/v1 -> Uvicorn)
docker run -d --name citadel-app --network citadel_default \
  -p 8080:8080 \
  -e CITADEL_DB_HOST=db \
  -e CITADEL_DB_USER=postgres \
  -e CITADEL_DB_PASS=password \
  -e CITADEL_DB_NAME=citadel \
  -e CITADEL_CELERY_BROKER_URL=redis://redis:6379/0 \
  -e CITADEL_CELERY_RESULT_BACKEND=redis://redis:6379/0 \
  -e CITADEL_FERNET_KEY="$CITADEL_FERNET_KEY" \
  citadel:latest
```

Access Citadel at `http://<host-ip>:8080`.

---

## Next Steps

Once Citadel is running, set up a compatible Kubernetes cluster using the **[K3s Quickstart Setup](k3s-quickstart.md)** and register its kubeconfig in Citadel under **K8s Clusters**.
