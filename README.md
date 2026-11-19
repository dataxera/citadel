# Dataxera Citadel

Dataxera Citadel is a 100% open-source data & AI orchestration platform, providing an all-in-one solution for data warehousing, data lakes, and AI platforms.

- **Orchestration**: Currently provides orchestration capabilities to deploy key data platform components such as PostgreSQL, Trino, Airflow, Superset, Kafka, and others.
- **Future Roadmap**:
    - **GraphRAG Platform**: Comprehensive support for GraphRAG and ontology management.
    - **SQL RAG**: Implementing SQL RAG with Trino integration.
    - **AI Visualization**: AI-powered dashboard and visualization creation.
    - **Advanced Modeling**: Data Vault modeling support.
- **Roadmap Targets**:
    - **Version 0.1**: Focus on Data Platform deployment orchestration capability.
    - **Version 0.2**: Introduction of Data Ingestion support.
    - **Version 0.3**: Introduction of RAG support.
    - **Version 0.4**: Introduction of Data Vault support.
- **Current Focus**: Priority is placed on streamlining the deployment of dependency components to establish a robust foundation.

## Prerequisites

*   **Python 3.13+**
*   **Node.js** (v18+ recommended) and **npm**
*   **uv** (Python package manager): [Installation instructions](https://github.com/astral-sh/uv)
*   **Docker** and **Docker Compose** (for running backing services)
*   **CloudNativePG Operator** (for Kubernetes deployments): [Installation guide](https://cloudnative-pg.io/documentation/current/installation_operator/)

## Kubernetes Deployment Setup

For Kubernetes cluster setup and Citadel deployment instructions, see the [Installation & Kubernetes Operations Guide](docs/installation/index.md):

*   **[Production Cluster Hardware Requirements](docs/installation/production-hardware-requirements.md)**: Recommended hardware, disk partitioning, and networking specs for production clusters.
*   **[K3s Quickstart Setup](docs/installation/k3s-quickstart.md)**: Setting up a K3s cluster with Cilium CNI (L2 LoadBalancer IPAM), OpenEBS `lvm-localpv`, OS tuning, and wildcard DNS.
*   **[K3s Disaster Recovery Guide](docs/installation/k3s-disaster-recovery.md)**: Multi-cluster Cilium ClusterMesh and automated S3-backed `etcd` backup/restore.
*   **[Citadel Quickstart (Single-Node Docker)](docs/installation/citadel-quickstart.md)**: Running the Citadel control plane with Docker Compose.

For the full documentation index, see [docs/index.md](docs/index.md).

## Development Environment Setup

### 1. Start Development Containers

Start PostgreSQL and Redis (the backing services) using Docker Compose:

```bash
docker compose --profile=app up -d --build
```

This will start:
*   PostgreSQL on `localhost:5432` (User: `postgres`, Password: `password`, DB: `citadel`)
*   Redis on `localhost:6379`
*   Citadel Development Proxy on `http://localhost:8080` (Nginx proxy routing to both frontend and backend)

You should access the application via the development proxy at **`http://localhost:8080`** rather than connecting to the frontend port (`3000`) or backend port (`8000`) directly.

The backend and frontend are running with local source code mounted into the container for development and support hot-reloading. 

### 2. Application Setup

Run the unified setup script from the root directory:

```bash
python setup-dev.py
```

This will automatically:
- Install backend dependencies using `uv`.
- Install frontend dependencies using `npm`.
- Run database migrations.
- Suggest an encryption key.

## Running Tests

### Backend

To run backend tests:

```bash
uv run --package citadel pytest backend/tests
```

