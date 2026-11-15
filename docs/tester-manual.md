# Mindweaver Human Tester Manual (QA & Validation Guide)

This manual provides a comprehensive, step-by-step verification guide for human QA testers and developers to validate all core functionalities of **Mindweaver**.

---

## 1. Prerequisites & Test Environment Setup

Before starting manual validation, ensure the following environment and test fixtures are available:

### 1.1 Application Access
- **Development Stack**: Start backing services (`PostgreSQL`, `Redis`, `Nginx Proxy`) and the Mindweaver application (`Backend`, `Frontend`, `Celery Worker`, `Celery Beat`).
- **Entry URL**: Access the web UI through the unified proxy at `http://localhost:8080` (or the target deployment Ingress URL). Avoid testing directly against port `3000` or `8000` so that proxy routing and CORS behaviors are validated accurately.

### 1.2 External Backing Resources for End-to-End Tests
To test all connectivity and orchestration features end-to-end, prepare:
1. **Kubernetes Cluster**: A reachable cluster (`k3s` or standard Kubernetes v1.28+) with a valid `kubeconfig` and a LoadBalancer provider (e.g., MetalLB) or NodePort routing.
2. **S3-Compatible Object Storage**: An AWS S3 or MinIO endpoint with a valid Access Key, Secret Key, and at least one bucket.
3. **LDAP Server** *(Optional, for SSO/Role Mapping)*: An OpenLDAP or Active Directory test server (`ldap://` or `ldaps://`).
4. **External Database**: A reachable PostgreSQL or MySQL instance for testing **Database Sources**.
5. **Git Repository**: A reachable Git repository URL (HTTPS or SSH) for testing **Git Repositories** and Airflow DAGs Git-Sync.
6. **Container Registry**: Credentials for a Docker/OCI registry (e.g., Docker Hub, GHCR, or Harbor).
7. **PEM Certificate**: A valid X.509 certificate file (`-----BEGIN CERTIFICATE----- ... -----END CERTIFICATE-----`) and an expired/invalid PEM sample for negative testing.

### 1.3 Test User Accounts
Prepare or create the following accounts during testing:
- **Superadmin User**: Default bootstrap administrator (`is_superadmin = true`).
- **Standard / Read-Only User**: A non-superadmin local user (`is_superadmin = false`) with read-only (`<service>:read`) or specific service management (`<service>:manage`) permissions.
- **Inactive User**: A local user with `is_active = false`.

---

## 2. Authentication, Session & Global UI Controls

### 2.1 Login & Session Lifecycle (`/login`)
- [ ] **Brand Rendering**: Verify that the login screen loads the configured brand name, SVG logo, and brand background color from `/api/v1/_brand`.
- [ ] **Backend Unreachable Handling**: Stop the backend server and reload `/login`. Confirm the **Unable to Connect** card appears with a **RETRY CONNECTION** button. Restart the backend, click **RETRY CONNECTION**, and verify the sign-in form loads.
- [ ] **Local Sign-In (Positive)**: Log in with valid superadmin credentials (`username` and `password`). Verify redirection to the **Fleet Overview** (`/`) page.
- [ ] **Local Sign-In (Negative)**:
  - Attempt login with an incorrect password and confirm the error message `Invalid username or password.` is displayed.
  - Attempt login with an inactive user (`is_active = false`) and confirm access is rejected.
- [ ] **OIDC / SSO Toggle** *(when `oidc_enabled` is true in `/feature-flags`)*:
  - Verify **CONTINUE WITH SSO** is shown by default.
  - Click **Sign in with username/password** to switch to the local login form, and click **Back to SSO Sign In** to switch back.
  - Click **CONTINUE WITH SSO** and verify redirection to the OIDC provider and callback handling at `/callback`.
- [ ] **Protected Routes & Logout**:
  - Open the **User Profile Panel** at the bottom of the left sidebar and click **Log Out**.
  - Verify redirection to `/login` and confirm that navigating directly to protected routes (e.g., `/projects`, `/platform/pgsql`) while logged out redirects back to `/login`.

### 2.2 Global Layout, Sidebar & Header
- [ ] **Sidebar Collapse & Tooltips**:
  - Click the chevron toggle button on the sidebar border to collapse and expand the sidebar.
  - Reload the browser and verify the collapsed/expanded state persists via `localStorage`.
  - When collapsed, hover over navigation icons to verify right-side tooltips appear with the section/page names.
- [ ] **Theme Toggle (Dark / Light Mode)**:
  - Click the Sun/Moon toggle button in the top header to switch between Dark Mode and Light Mode.
  - Reload the browser and confirm the selected theme persists.
- [ ] **Global Project Context Switcher**:
  - In the top header, click the **Context** selector (`Context: All Projects` or a specific project name).
  - Select a specific project and verify that project-scoped pages (**Fleet Overview**, **Connectivity**, **Data Sources**, **Infrastructure**) immediately filter their listed resources to only those belonging to the selected project.
  - Reload the browser and verify the selected project context persists.
  - Switch back to **Show All Projects** and verify resources across all projects are displayed.

---

## 3. Fleet Overview Dashboard (`/`)

- [ ] **KPI Summary Cards**:
  - Verify **Total Deployments** displays the exact count of platform instances matching the current project filter.
  - Verify **Active Projects** displays the total number of projects (or `1` when a single project is selected in the header context).
- [ ] **Platform Breakdown Grid**:
  - Verify cards are shown for all 8 platform services: **CloudNative PG**, **Apache Doris**, **Hive Metastore**, **Apache Kafka**, **Trino Cluster**, **Apache Airflow**, **Apache NiFi**, and **Apache Superset**.
  - Confirm the badge count on each card matches the number of instances for that service.
  - Click any card (`Manage ->`) and verify navigation to the corresponding `/platform/<service>` page.
- [ ] **Empty State**:
  - Select a newly created project with zero platform deployments and verify the empty state (`Quiet in the sector`) is rendered.

---

## 4. Administration: Local User Management (`/users`)

- [ ] **Superadmin Visibility**:
  - Log in as a **Superadmin** and confirm the **Administration -> Users** item is visible in the sidebar.
  - Log in as a **non-superadmin** user and confirm the **Administration** section is hidden and direct navigation to `/users` is restricted.
- [ ] **Create Local User**:
  - Click **CREATE USER** and fill in `name` (username), `display_name`, `email`, `title`, `password`, `is_active`, and `is_superadmin`.
  - Submit the form and verify the user appears in the list with appropriate badges (`SUPERADMIN`, `ACTIVE`, or `INACTIVE`).
- [ ] **Edit Local User**:
  - Click the **Edit** (pencil) icon on a user row, modify `display_name`, `title`, or role/permission assignments, save, and verify the updated values appear in the list.
- [ ] **Change Password**:
  - Click the **Change Password** (key) icon on a user row.
  - **Negative Validation**:
    - Enter a password shorter than 8 characters -> verify `Password must be at least 8 characters long.` error.
    - Enter mismatched `New Password` and `Confirm New Password` -> verify `Passwords do not match.` error.
  - **Positive Validation**: Enter matching valid passwords (`>= 8` characters), submit, and verify the success notification and that the user can log in with the new password.
- [ ] **Delete Local User**:
  - Click the **Delete** (trash) icon on a test user.
  - Verify the confirmation modal requires typing the exact username before the **CONFIRM / DELETE** button becomes enabled.
  - Confirm deletion and verify the user is removed from the list.

---

## 5. Environment Management

### 5.1 Kubernetes Clusters (`/k8s_clusters`)
- [ ] **Register Cluster**:
  - Click to create a new K8s Cluster. Test both `remote` (pasting a valid `kubeconfig` YAML) and `in-cluster` types.
  - Verify that on edit, `kubeconfig` is redacted as `__REDACTED__`.
- [ ] **Cluster Health & Detail View (`/k8s_clusters/:id`)**:
  - Click a cluster row to open its **Cluster Health** view.
  - Verify the status indicator (`ONLINE`, `OFFLINE`, or `ERROR`), Kubernetes version (`K8S v1.x.x`), **Total CPU Allocation** (Cores), **Total RAM Capacity** (GiB), and **Node Topology** badges (`Ready` in green vs `NotReady` in red).
  - Click **REFRESH** and confirm the state refreshes without error.
- [ ] **Core Integrations Sync**:
  - In the **Core Integrations** panel, click **SYNC INTEGRATIONS** (`sync_core_integrations`).
  - Verify background installation and status updates (`INACTIVE` -> `ACTIVE` / version badge) for:
    - **ArgoCD**
    - **Cert Manager**
    - **CNPG Operator**
    - **Envoy Gateway**
    - **Kafka Operator**
    - **NiFi Operator**
    - **Doris Operator**
- [ ] **Delete Cluster**:
  - Delete an unused test cluster by typing its exact name in the confirmation modal.

### 5.2 LDAP Configurations (`/ldap-configs`)
- [ ] **Create & Validate LDAP Config**:
  - Create a new LDAP config with `server_url`, `bind_dn`, `bind_password`, `user_search_base`, `user_search_filter`, `username_attr`, and optional group attributes.
  - **Negative Validation**: Enter a `server_url` that does not start with `ldap://` or `ldaps://` and verify validation error.
- [ ] **Test Connection**:
  - Click **TEST CONNECTION** inside the create/edit modal (and from the listing view).
  - Verify a green success banner is shown for a reachable LDAP server and a red error banner is shown when credentials or host are invalid.
- [ ] **Secret Redaction**:
  - Re-open the LDAP config in Edit mode and confirm `bind_password` shows `__REDACTED__`.

### 5.3 Stacks (`/stacks`)
- [ ] **Inspect Certified Stacks**:
  - Navigate to **Environment -> Stacks**.
  - Verify the certified stack list loads (e.g., `mindweaver-0.1.0-alpha.1`).
  - Click a stack card on the left pane and verify the **Details** pane displays every locked component, its **Image Repository**, **Locked Tag**, and **Chart Version**.

### 5.4 Projects (`/projects`)
- [ ] **Create Project**:
  - Create a project specifying `name`, `title`, `description`, `k8s_cluster_id` (relationship dropdown), `k8s_namespace`, optional `ldap_config_id`, `ingress_domain`, `envoy_gateway_service_type` (`LoadBalancer` or `NodePort`), and `stack_id`.
- [ ] **Edit Project & Immutable Fields**:
  - Edit the project and verify immutable fields (such as `name`) are disabled and cannot be modified.
- [ ] **Project Fleet Overview (`/projects/:id`)**:
  - Click a project to open its **Fleet Overview** page.
  - Verify the 7 resource counter cards (**PostgreSQL**, **Trino**, **Hive Metastore**, **Superset**, **Airflow**, **Kafka**, **NiFi**) match the deployed instances in that project.
  - Click **SYNC INTEGRATIONS** (`sync_project_integrations`) when `ingress_domain` is configured and verify the sync notification.
- [ ] **Envoy Gateway & HAProxy Certificate**:
  - When Envoy Gateway is active for the project, verify the **Envoy Gateway** card shows `ACTIVE`, external access ports/IPs, and the DNS or HAProxy configuration guide.
  - Click **DOWNLOAD PEM CERT** and verify `envoy-<project-name>.pem` downloads cleanly.
- [ ] **Dex OIDC & Project Local Users** *(when `enable_dex` is enabled)*:
  - In the **Dex OIDC Integration** card, click **INSTALL DEX OIDC** (or **UPDATE DEX**) and verify the OIDC Discovery URL link is displayed once active.
  - In **Local User Management**, click **ADD LOCAL USER**, enter `username`, `email`, `password`, and `password_confirm`.
  - Verify mismatching passwords trigger a validation error, and matching passwords create the user. Test editing and deleting the project local user.
- [ ] **Cert Manager Resources Inspection & Renewal**:
  - In the **Cert Manager Resources** card, verify Issuers and Issued Certificates are grouped by issuer with `Ready` / `Expired` status badges.
  - Click **CA CERT** on an issuer to download its `<issuer>-ca.crt` file.
  - Click **DETAILS** on an issued certificate to open the modal and verify Subject, Issuer, Validity Period, Serial Number, Signature Algorithm, and raw PEM copy/toggle.
  - Click **RENEW** on a certificate and verify renewal is triggered and status refreshes.

---

## 6. Connectivity Management (Project-Scoped)

### 6.1 S3 Storages (`/s3-storages`)
- [ ] **Create & Edit S3 Storage**:
  - Create an S3 Storage resource linked to a Project (`region`, `access_key`, `secret_key`, `endpoint_url`, `verify_ssl`).
  - **Negative Validation**: Test an `endpoint_url` without `http://` or `https://` and verify the validation error.
  - Click **TEST CONNECTION** in the modal to verify connectivity before saving.
- [ ] **S3 File Browser (`/s3-storages/:id`)**:
  - Click an S3 Storage row (or browse action) to open the **S3 File Browser**.
  - **Bucket & Folder Navigation**:
    - Verify available buckets are listed at the root level.
    - Click a bucket to view its folders and files; click a folder to drill down.
    - Use the breadcrumb bar and the **Up one level** (`^`) button to navigate back up to the bucket root and storage root.
  - **Upload File**: Inside a bucket/folder, click the **Upload** button, select a local file, and verify the upload succeeds and the file appears in the list with size and timestamp.
  - **Download File**: Hover over a file row, click the **Download** icon, and verify the file downloads via presigned URL.
  - **Delete File**: Hover over a file row, click the **Delete** (trash) icon, type the file name in the confirmation modal, and verify the file is permanently removed from the bucket.

### 6.2 SSH Keys (`/ssh-keys`)
- [ ] **Create & Manage SSH Keys**:
  - Create an SSH Key resource choosing `algorithm` (`rsa` or `ed25519`) and `key_size` (`2048` or `4096`).
  - Verify the public key is generated/accessible while `private_key` is redacted (`__REDACTED__`) when editing.
  - Test deleting an unused SSH key.

### 6.3 Git Repositories (`/git-repos`)
- [ ] **Register & Test Git Repository**:
  - Create a Git Repository resource using an HTTPS URL (`https://...`) with username/password or an SSH URL (`git@...` or `ssh://...`) linked to an **SSH Key** (`ssh_key_id`).
  - **Negative Validation**: Provide a malformed URL (e.g., `ftp://example.com`) and verify validation fails.
  - Click **TEST CONNECTION** and verify repository reachability and authentication.

### 6.4 Container Registries (`/container-registries`)
- [ ] **Register & Test Container Registry**:
  - Create a Container Registry resource (`url`, `username`, `password`).
  - Click **TEST CONNECTION** with valid and invalid credentials and verify the result banner.

### 6.5 Trusted Certificates (`/trusted-certs`)
- [ ] **Upload & Decode Certificate**:
  - Create a Trusted Certificate resource by pasting a PEM-encoded certificate.
  - **Negative Validation**: Paste plain text that does not begin with `-----BEGIN CERTIFICATE-----` and end with `-----END CERTIFICATE-----` and confirm validation fails.
  - Click the created certificate to open its detail view (`/trusted-certs/:id`).
  - Verify the decoded X.509 metadata is displayed:
    - **Active & Valid** (green) vs **Invalid / Expired** (red) status card.
    - **Subject (Owner)** fields (`CN`, `O`, `OU`, `C`, `ST`, `L`) and **Subject Alt Names (SANs)**.
    - **Issuer (Authority)** fields.
    - **Validity Period** (`Valid From`, `Valid Until`) and **Technical Details** (`Serial Number`, `Signature Algorithm`, `Version`).

---

## 7. Data Sources Management (`/database-sources`)

- [ ] **Register External Database Source**:
  - Navigate to **Data Sources -> Database Sources** and click **REGISTER SOURCE**.
  - Fill in `project_id`, `name`, `title`, `engine` (e.g., `postgresql`, `mysql`), `host`, `port`, `database`, `schema_name`, `username`, and `password`.
- [ ] **Inline Test Connection**:
  - In the Database Sources list, click the **Test Connection** (link) icon on the resource row.
  - Verify the spinner appears during testing and an inline green (`Connection successful`) or red (`Connection failed`) banner renders directly below the item.
- [ ] **Edit & Delete**:
  - Edit the database source, verify password redaction (`__REDACTED__`), update the host/port, save, and test deletion via the confirmation modal.

---

## 8. Infrastructure: Platform Components (`/platform/*`)

All 8 platform services share a unified orchestration lifecycle and 3-tab detail interface (**Connection & Access**, **Configuration**, **Administrative**).

### 8.1 Common Platform Service Test Checklist
Perform these checks across platform services:
- [ ] **Auto-Generated Name & Uniqueness**:
  - Open the Create modal for any platform service and verify a default name (`<service>-<hash>`) is pre-populated.
  - Attempt to create two platform services with the exact same `name` (even across different service types) and verify `NameTracker` rejects the duplicate name.
- [ ] **Resource Request vs. Limit Validation**:
  - Set `cpu_request > cpu_limit` or `mem_request > mem_limit` and verify form submission fails with a validation error.
- [ ] **Deploy Lifecycle (`Connection & Access` Tab)**:
  - Before deployment, verify the **Connection & Access** tab shows the empty state (`Cluster Not Deployed`) with a **DEPLOY** button.
  - Click **DEPLOY** and verify the status badge transitions to `PENDING` and then to `RUNNING` / `ONLINE` once ArgoCD and Kubernetes pods are healthy.
  - Click the status message pill in the header to open the **Service Status Details** modal; verify the timestamp and the **Copy** button for the status message.
  - Click **REFRESH** in the top-right header to trigger an immediate status poll (`_refresh`).
- [ ] **Live Reconfiguration (`Configuration` Tab)**:
  - Switch to the **Configuration** tab (`?tab=configure`), modify a mutable parameter (e.g., replica count or CPU limit), and click **SAVE CHANGES**.
  - Verify that updating an active platform automatically triggers a redeploy to the Kubernetes cluster.
- [ ] **Decommission & Delete (`Administrative` Tab)**:
  - Switch to the **Administrative** tab (`?tab=admin`).
  - Verify that while the service is active, **DECOMMISSION CLUSTER** is enabled and **DELETE CLUSTER** is disabled.
  - Click **DECOMMISSION CLUSTER**, verify the confirmation modal requires typing the exact resource name, and test:
    1. **Standard Decommission**: Unchecked force box -> cleanly removes ArgoCD application and K8s resources.
    2. **Force Decommission**: Checked **Force decommission (ignore cluster errors)** box -> marks the service offline even if the cluster is unreachable.
  - Once decommissioned (`STOPPED` / `OFFLINE`), verify **DELETE CLUSTER** becomes enabled. Click **DELETE CLUSTER**, type the resource name, and confirm the metadata record is deleted.
- [ ] **Dependency Protection (`DependencyTracker`)**:
  - When a PostgreSQL instance is actively used by **Hive Metastore**, **Airflow**, or **Superset**, attempt to decommission or delete that PostgreSQL instance.
  - Verify the backend blocks the operation with a dependency error indicating which downstream service depends on it.

---

### 8.2 Component-Specific Validation Scenarios

#### 1. PostgreSQL (`/platform/pgsql`)
- [ ] **Quorum Validation**: Attempt to create a cluster with an even number of `instances` (e.g., `2` or `4`). Verify validation fails with `Instances must be an odd number (1, 3, 5, ...)`.
- [ ] **PgBouncer Settings**: Configure `pgbouncer_pool_mode` (`transaction`, `session`, or `statement`) and `pgbouncer_pool_size`.
- [ ] **S3 Barman Backup**:
  - Enable `enable_backup`, select an `s3_storage_id`, and use the **S3 Path Widget** (`backup_destination`) to browse/select an `s3://<bucket>/<path>` destination.
  - Verify `backup_destination` rejects paths not starting with `s3://`.
- [ ] **On-Demand Backup Action**:
  - On an active PostgreSQL cluster, click the **ACTIONS** dropdown in the top header and click `backup`.
  - Verify the toast notification confirms the CNPG `Backup` custom resource was triggered.
- [ ] **Connection Endpoints**:
  - Verify Internal Network Access shows Read-Write (`-rw`), Read-Only (`-ro`), Read (`-r`), and PgBouncer (`-pooler`) URIs.
  - Verify External Network Access displays the `psql` CLI connection command, credentials (`db_user`, `db_pass`), and CA certificate download button.

#### 2. Apache Doris (`/platform/doris`)
- [ ] **FE Quorum & BE Replicas Validation**:
  - Attempt to set `fe_replicas` to an even number (e.g., `2`) and verify validation fails (`FE replicas must be an odd positive number (1, 3, 5, ...)`).
  - Verify separate resource request/limit validations for both Frontend (`fe_*`) and Backend (`be_*`) nodes.
- [ ] **Connection Endpoints**:
  - Deploy Doris and verify internal and external endpoints for the MySQL protocol port (`9030`) and FE HTTP UI port (`8030`), along with `root` and `doris_operator` credentials.

#### 3. Hive Metastore (`/platform/hive-metastore`)
- [ ] **Dependencies & S3 Warehouse Path**:
  - Select a deployed PostgreSQL instance (`database_id`) and an S3 Storage (`s3_storage_id`).
  - Use the S3 path selector to set `warehouse_dir` (e.g., `s3a://metastore/warehouse/`) and toggle `iceberg_enabled`.
- [ ] **Connection Endpoints**:
  - Once deployed, verify the `Thrift HMS` endpoint (`thrift://<name>.<ns>.svc.cluster.local:9083`) is shown.
  - If `iceberg_enabled` is true, verify the `Iceberg REST` endpoint (`http://<name>-iceberg.<ns>.svc.cluster.local:9001/iceberg`) is also displayed.

#### 4. Trino (`/platform/trino`)
- [ ] **Catalog Requirement Validation**:
  - Attempt to create a Trino cluster with both `hms_ids` and `database_source_ids` empty. Verify validation fails with `At least one catalog (Hive Metastore or Database Source) must be defined`.
- [ ] **Rules JSON Validation**:
  - In the `rules` JSON field, enter malformed JSON and confirm client/server validation highlights the JSON syntax error.
- [ ] **Deployment & Catalogs**:
  - Deploy Trino linked to a Hive Metastore and/or Database Source. Verify the Coordinator endpoints, CLI command, and Trino Web UI access details are displayed on the **Connection & Access** tab.

#### 5. Apache Kafka (`/platform/kafka`)
- [ ] **Replica & Properties Validation**:
  - Test `replica_count` boundaries (must be between `1` and `9`).
  - Add custom broker configurations using the `additional_properties` **Key-Value Widget** (add, edit, and remove key-value pairs).
  - Toggle `enable_loadbalancer` and verify external bootstrap server endpoints appear when deployed.

#### 6. Apache NiFi (`/platform/nifi`)
- [ ] **Role Mapping & Properties**:
  - Add LDAP/OIDC mappings using the **Auth Role Mapping Widget** (`auth_role_mapping`) and custom properties via `additional_properties`.
  - Deploy NiFi and verify the HTTPS Web UI endpoint and access instructions on the **Connection & Access** tab.

#### 7. Apache Airflow (`/platform/airflow`)
- [ ] **Configuration & Integrations**:
  - Select a mandatory PostgreSQL instance (`platform_pgsql_id`).
  - Configure S3 remote logging (`s3_storage_id` and `logs_s3_bucket`).
  - Enable `dags_git_sync_enabled`, select a `git_repo_id`, and specify `dags_git_branch` and `dags_git_subpath`.
  - Add role mappings in `auth_role_mapping` (valid roles: `Admin`, `User`, `Op`, `Viewer`, `Public`).
- [ ] **Deployment & Webserver Access**:
  - Deploy Airflow and verify the Airflow Webserver URI and initial `admin` user password are displayed and functional.

#### 8. Apache Superset (`/platform/superset`)
- [ ] **Metadata DB & Auto-Registered Data Sources**:
  - Select a mandatory PostgreSQL instance (`platform_pgsql_id`).
  - Select one or more `database_source_ids`, `trino_ids`, and `doris_ids` to be automatically registered as Superset databases.
  - Toggle `sqllab_enabled` and `load_examples`.
  - Configure `auth_role_mapping` (valid roles: `Admin`, `Alpha`, `Gamma`, `sql_lab`, `Public`).
- [ ] **Deployment & UI Verification**:
  - Deploy Superset, open the Superset Web UI URL from the **Connection & Access** tab, log in with the displayed `admin` credentials, and verify that the selected Trino/Doris/Database sources are pre-configured.

---

## 9. Cross-Cutting Security & RBAC Verification

- [ ] **Sensitive Field Redaction (`SecretHandlerMixin`)**:
  - Across all forms with secrets (K8s `kubeconfig`, LDAP `bind_password`, S3 `secret_key`, SSH `private_key`, Git `password`, Container Registry `password`, Database Source `password`), verify:
    1. `GET` API responses and Edit forms always display `__REDACTED__` instead of plaintext secrets.
    2. Saving an Edit form while leaving the field as `__REDACTED__` preserves the existing encrypted secret in the database.
    3. Entering `__CLEAR__` clears the secret to an empty string.
    4. Entering a new string replaces and re-encrypts the secret.
- [ ] **Permission Hierarchy & RBAC (`permission.py`)**:
  - Assign a test user only `<service>:read` permission (e.g., `project:read` or `pgsql:read`).
  - Verify the user can list and view the resource details (`GET`), including status polling, but receives `403 Forbidden` when attempting to create (`POST`), update (`PUT`), delete (`DELETE`), deploy/decommission, or execute operational actions (`_test-connection`, `_renew_certificate`).

---
SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
SPDX-License-Identifier: AGPLv3+
