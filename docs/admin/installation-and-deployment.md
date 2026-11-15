<!--
SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
SPDX-License-Identifier: AGPLv3+
-->

# Installation & Production Deployment

This chapter covers preparing your infrastructure and deploying the Mindweaver control plane using either the official **Helm Chart** (recommended for production) or **Docker / Docker Compose**.

---

## 1. Infrastructure & Kubernetes Prerequisites

### Control Plane Requirements
- **PostgreSQL**: v15+ (can be provisioned automatically via the CloudNativePG operator in the Mindweaver Helm chart, or provided externally).
- **Redis / Valkey**: Redis 7+ or Valkey 8+ for Celery task queueing and result storage (can be provisioned via the bundled Valkey subchart or provided externally).
- **CPU & Memory**: Minimum 2 vCPU and 4 GiB RAM for the Mindweaver control plane (API, Celery Worker, Celery Beat, PostgreSQL, and Valkey/Redis).

### Target Kubernetes Cluster Requirements
Clusters managed by Mindweaver (or hosting Mindweaver itself) require:
- **Kubernetes**: v1.28+ (tested with `k3s` and standard cloud distributions such as EKS, GKE, and AKS).
- **Default StorageClass**: A dynamic PersistentVolume provisioner (e.g., `local-path` on k3s, EBS CSI, Ceph/Rook, Longhorn) is required for stateful workloads (PostgreSQL, Kafka, Doris, NiFi).
- **LoadBalancer Controller**: Required when using `LoadBalancer` service types for Envoy Gateway and external service access.
  - **Cloud Providers**: Native cloud load balancer controller.
  - **Bare-Metal / Self-Hosted**: **[MetalLB](https://metallb.io/)** (Layer 2 or BGP/Layer 3 mode).
- **CloudNativePG Operator** *(Required if using the Mindweaver Helm chart's bundled PostgreSQL database)*: Because the Helm chart creates a `postgresql.cnpg.io/v1` `Cluster` resource when `postgresql.enabled: true`, the CloudNativePG operator must be installed in the cluster beforehand.

---

## 2. Preparing a Self-Hosted Kubernetes Cluster (k3s + MetalLB)

If you are deploying onto bare-metal or VMs using **k3s**, disable the built-in `traefik` ingress and `servicelb` (Klipper) so they do not conflict with **Envoy Gateway** and **MetalLB**:

```bash
# 1. Install k3s binary
curl -sfL https://get.k3s.io | sh -

# 2. Run k3s server with Traefik and ServiceLB disabled
k3s server \
    --disable traefik \
    --disable servicelb \
    --cluster-cidr 192.168.0.0/16,fd42:0:0/64 \
    --service-cidr 10.96.0.0/12,fd43:0:0/64
```

### Installing MetalLB

```bash
# Apply MetalLB manifest
kubectl apply -f https://raw.githubusercontent.com/metallb/metallb/main/manifests/metallb.yaml

# Wait for MetalLB pods to become ready
kubectl wait --for=condition=ready pod --selector app=metallb -n metallb-system --timeout=120s
```

After MetalLB is running, apply an `IPAddressPool` and `L2Advertisement` (or `BGPAdvertisement`) matching your network's routable IP range:

```yaml
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata:
  name: default-pool
  namespace: metallb-system
spec:
  addresses:
    - 192.168.1.200-192.168.1.250
---
apiVersion: metallb.io/v1beta1
kind: L2Advertisement
metadata:
  name: default-l2
  namespace: metallb-system
spec:
  ipAddressPools:
    - default-pool
```

---

## 3. Deploying Mindweaver on Kubernetes with Helm

The official Mindweaver Helm chart is located in `charts/mindweaver` (and published as an OCI artifact to `ghcr.io/kagesenshi/mindweaver`).

### Step 1: Generate Required Secrets

Mindweaver requires two cryptographic keys:
1. **`fernetKey`** (`MINDWEAVER_FERNET_KEY`): A 32-byte URL-safe base64-encoded Fernet key used to encrypt all database secrets (passwords, private keys, kubeconfigs).
2. **`jwtSecret`** (`MINDWEAVER_JWT_SECRET`): Secret key (at least 32 bytes) used to sign HS256 session JWTs.

Generate a Fernet key using Python or the Mindweaver CLI:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Or via the CLI:
uv run mindweaver crypto generate-key
```

Generate a random JWT secret:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

### Step 2: Install CloudNativePG (If Using Bundled PostgreSQL)

If `postgresql.enabled` is `true` (the default), ensure the CloudNativePG operator is installed on the cluster before installing the Mindweaver chart:

```bash
helm repo add cnpg https://cloudnative-pg.github.io/charts
helm repo update
helm upgrade --install cnpg cnpg/cloudnative-pg \
  --namespace cnpg-system \
  --create-namespace \
  --wait
```

### Step 3: Create a Production `values-prod.yaml`

Create a custom values file tailored to your environment:

```yaml
replicaCount: 2

image:
  repository: ghcr.io/kagesenshi/mindweaver/mindweaver
  pullPolicy: IfNotPresent
  tag: "" # Defaults to Chart appVersion

serviceAccount:
  create: true

rbac:
  # Grants ClusterRole permissions required when managing the hosting cluster via "in-cluster" mode
  create: true

service:
  type: NodePort
  port: 80
  nodePort: 31280

config:
  db:
    migrate: true # Runs `uv run mindweaver db migrate` in an initContainer before API startup
  timezone: "UTC"
  enableAuth: true

secret:
  jwtSecret: "<YOUR-STRONG-JWT-SECRET>"
  fernetKey: "<YOUR-GENERATED-FERNET-KEY>"
  oidc:
    issuer: "https://idp.example.com/realms/main"
    clientId: "mindweaver"
    clientSecret: "<YOUR-OIDC-CLIENT-SECRET>"
  # Only used when postgresql.enabled is false (note: also set config.db.host: true to render external DB secret keys)
  db:
    host: "external-postgres.example.com"
    port: 5432
    name: "mindweaver"
    user: "mindweaver"
    password: "<DB-PASSWORD>"
  # Only used when valkey.enabled is false
  redis:
    host: "external-redis.example.com"
    port: 6379

worker:
  replicaCount: 2
  resources:
    requests:
      cpu: 250m
      memory: 512Mi
    limits:
      cpu: 1000m
      memory: 1Gi

beat:
  enabled: true
  resources:
    requests:
      cpu: 100m
      memory: 256Mi
    limits:
      cpu: 500m
      memory: 512Mi

postgresql:
  enabled: true
  instances: 3
  storage:
    size: 10Gi

valkey:
  enabled: true
  auth:
    enabled: false
  replica:
    enabled: true
    replicas: 2
    persistence:
      enabled: true
      size: 2Gi
```

> [!IMPORTANT]
> Keep `beat.enabled: true` at a single replica (the chart enforces `replicas: 1` with `strategy.type: Recreate` in `templates/deployments/beat.yaml`). Running multiple Celery Beat schedulers simultaneously will cause duplicate polling tasks.

### Step 4: Install the Helm Chart

```bash
# Build/update chart dependencies (Valkey) if installing from local source
helm dependency build ./charts/mindweaver

# Install or upgrade Mindweaver
helm upgrade --install mindweaver ./charts/mindweaver \
  --namespace mindweaver \
  --create-namespace \
  -f values-prod.yaml
```

### Step 5: Import Default Component Stacks

After the deployment is running and migrations have completed, import the built-in component stack definitions into the Mindweaver database by executing `mindweaver stack import` inside the API pod:

```bash
kubectl exec -n mindweaver deploy/mindweaver -- uv run mindweaver stack import
```

---

## 4. Deploying with Docker Compose

For single-node evaluations, PoCs, or local staging environments, Mindweaver provides a multi-container `docker-compose.yml` and a production multi-stage `Dockerfile`.

### Container Architecture (`Dockerfile`)
The production image (`Dockerfile`) combines:
1. **Frontend Assets**: Built from `frontend/` via Node 20 and served statically by **Nginx** from `/usr/share/nginx/html`.
2. **Backend Runtime**: Python 3.13 slim image with `uv`, `helm` (v3.16.1), `kubectl` (v1.36.3), `libpq-dev`, and `nginx`.
3. **Entrypoint (`/app/start.sh`)**: Starts Uvicorn (`mindweaver.app:app` on `0.0.0.0:8000`) in the background and runs Nginx (`:8080`) in the foreground as non-root user `app`.

### Running with Docker Compose

1. Configure `backend/.env` with a valid Fernet key:
   ```bash
   python3 -c "from cryptography.fernet import Fernet; print(f'MINDWEAVER_FERNET_KEY={Fernet.generate_key().decode()}')" > backend/.env
   ```
2. Start the full application stack:
   ```bash
   docker compose --profile=app up -d
   ```
   This launches:
   - `db`: PostgreSQL 15 (`:5432`)
   - `redis`: Redis 7 Alpine (`:6379`)
   - `migrate`: One-shot container that executes `uv run mindweaver db migrate && uv run mindweaver stack import`
   - `web`: FastAPI backend (`:8000`)
   - `scheduler`: Celery Beat scheduler (`uv run mindweaver scheduler`)
   - `worker`: Celery Worker (`uv run mindweaver worker`)
   - `frontend`: Vite server (`:3000`)
   - `proxy`: Nginx reverse proxy listening on **`http://localhost:8080`**

---

## 5. Health Check & Verification

Verify that the control plane is healthy:

```bash
# 1. Check API health endpoint
curl -f http://localhost:8080/health
# Expected response: {"status":"ok"}

# 2. Check active feature flags
curl -s http://localhost:8080/feature-flags
# Expected response: {"oidc_enabled":false,"enable_dex":false}
```
