<!--
SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
SPDX-License-Identifier: AGPLv3+
-->

# Configuration, Authentication & Security

This chapter details all environment variables supported by Mindweaver, how authentication (local and OIDC) works, how user accounts and permissions are managed, and how encrypted secrets are handled and rotated.

---

## 1. Environment Variables Reference

Mindweaver loads configuration using Pydantic Settings (`backend/src/mindweaver/config.py`). All settings can be specified via environment variables prefixed with `MINDWEAVER_` (case-insensitive) or inside `backend/.env`.

### Database Settings

| Environment Variable | Default | Description |
| :--- | :--- | :--- |
| `MINDWEAVER_DB_TYPE` | `postgresql` | Database type. |
| `MINDWEAVER_DB_DRIVER` | `postgresql+psycopg2` | Synchronous SQLAlchemy driver (used by Alembic and CLI commands). |
| `MINDWEAVER_DB_ASYNC_DRIVER` | `postgresql+asyncpg` | Asynchronous SQLAlchemy driver (used by FastAPI and async tasks). |
| `MINDWEAVER_DB_HOST` | `localhost` | PostgreSQL server hostname or IP. |
| `MINDWEAVER_DB_PORT` | `5432` | PostgreSQL server port. |
| `MINDWEAVER_DB_NAME` | `mindweaver` | Database name. |
| `MINDWEAVER_DB_USER` | `postgres` | Database username. |
| `MINDWEAVER_DB_PASS` | `password` | Database password. |
| `MINDWEAVER_DB_POOL_SIZE` | `20` | SQLAlchemy connection pool size per process. |
| `MINDWEAVER_DB_MAX_OVERFLOW` | `20` | Maximum overflow connections beyond `db_pool_size`. |
| `MINDWEAVER_DB_POOL_RECYCLE` | `1800` | Seconds before recycling idle database connections. |
| `MINDWEAVER_DB_POOL_PRE_PING` | `true` | Test connections for liveness before checkout. |
| `MINDWEAVER_DB_POOL_TIMEOUT` | `30.0` | Seconds to wait before giving up on getting a connection from the pool. |

### Security & Authentication Settings

| Environment Variable | Default | Description |
| :--- | :--- | :--- |
| `MINDWEAVER_ENABLE_AUTH` | `true` | Enforces authentication and RBAC across all API endpoints. **Never set to `false` in production.** |
| `MINDWEAVER_FERNET_KEY` | `None` *(Required)* | 32-byte URL-safe base64-encoded key used to encrypt sensitive fields in the database. Application startup and Celery workers validate this key on initialization. |
| `MINDWEAVER_JWT_SECRET` | `unsafe-jwt-secret-key-...` | Secret key (minimum 32 bytes) used to sign HS256 session tokens (24-hour expiration). **Must be overridden in production.** |
| `MINDWEAVER_DEFAULT_ADMIN_USERNAME` | `None` | If set alongside `MINDWEAVER_DEFAULT_ADMIN_PASSWORD`, automatically creates a Superadmin user on application startup if one does not already exist. |
| `MINDWEAVER_DEFAULT_ADMIN_PASSWORD` | `None` | Password for the bootstrap Superadmin user created at startup. |
| `MINDWEAVER_OIDC_ISSUER` | `None` | OpenID Connect Issuer URL (e.g., `https://keycloak.example.com/realms/master`). Enables OIDC login when set. |
| `MINDWEAVER_OIDC_CLIENT_ID` | `None` | OIDC Client ID registered with the identity provider. |
| `MINDWEAVER_OIDC_CLIENT_SECRET` | `None` | OIDC Client Secret registered with the identity provider. |

### Celery & Background Task Settings

| Environment Variable | Default | Description |
| :--- | :--- | :--- |
| `MINDWEAVER_CELERY_BROKER_URL` | `redis://localhost:6379/0` | Redis/Valkey URL for the Celery message broker. |
| `MINDWEAVER_CELERY_RESULT_BACKEND` | `redis://localhost:6379/0` | Redis/Valkey URL for storing Celery task results. |
| `MINDWEAVER_EMBEDDED_WORKER` | `true` | When `true`, running `mindweaver scheduler` automatically spawns an embedded Celery worker subprocess. Set to `false` in Docker Compose and Kubernetes where `worker` and `scheduler` run in separate containers. |
| `MINDWEAVER_STATUS_POLLING_EXPIRY` | `60` | Expiration time (in seconds) for periodic cluster and platform status polling tasks in the queue. |
| `MINDWEAVER_TIMEZONE` | `Asia/Kuala_Lumpur` | Timezone used by Celery Beat and application timestamps. |

### Feature Flags, Branding & Developer Toggles

| Environment Variable | Default | Description |
| :--- | :--- | :--- |
| `MINDWEAVER_ENABLE_DEX` | `false` | Enables the `install_dex` project action to deploy per-project Dex OIDC instances. |
| `MINDWEAVER_BRAND_NAME` | `Mindweaver` | Custom brand title displayed in the UI sidebar and login screen. |
| `MINDWEAVER_BRAND_LOGO` | `logo.svg` | Filename of the SVG logo in `backend/src/mindweaver/resources/assets/` (e.g., `logo.svg`, `citadel.svg`). |
| `MINDWEAVER_BRAND_BGCOLOR` | `None` | Optional hex background color for the brand logo badge (e.g., `#ffffff`). |
| `MINDWEAVER_ENABLE_DB_RESET` | `false` | Enables the destructive `mindweaver db reset` CLI command. Keep `false` in production. |
| `MINDWEAVER_ENABLE_TEST_VIEWS` | `false` | Exposes internal `_verify-encrypted` endpoints used only by automated test suites. Keep `false` in production. |

---

## 2. Authentication Architecture

Mindweaver supports two authentication mechanisms that issue a 24-hour HS256 JWT bearer token signed with `MINDWEAVER_JWT_SECRET`:

### Local Username & Password Authentication
1. **Bootstrap Superadmin**: On FastAPI startup (`lifespan` in `backend/src/mindweaver/app.py`), if `MINDWEAVER_DEFAULT_ADMIN_USERNAME` and `MINDWEAVER_DEFAULT_ADMIN_PASSWORD` are configured, Mindweaver checks if the user exists in `mw_user`. If not, it creates the user with `is_superadmin=True` and a hashed password.
2. **Login Endpoint**: `POST /api/v1/auth/login` verifies the username and password against `mw_user` and returns a Bearer token.

### OpenID Connect (OIDC) Authentication
When `MINDWEAVER_OIDC_ISSUER`, `MINDWEAVER_OIDC_CLIENT_ID`, and `MINDWEAVER_OIDC_CLIENT_SECRET` are set:
1. `/feature-flags` reports `"oidc_enabled": true`, enabling the **Sign in with SSO** option on the login page.
2. `GET /api/v1/auth/login?redirect_url=...` performs OIDC discovery (`/.well-known/openid-configuration`) against `MINDWEAVER_OIDC_ISSUER` and redirects the browser to the provider's `authorization_endpoint` with scope `openid profile email`.
3. `POST /api/v1/auth/callback` exchanges the authorization code at the provider's `token_endpoint` and extracts the user's `email`, `name`, and `preferred_username` from the `id_token`.
4. **Just-In-Time (JIT) User Provisioning**:
   - If no user with that `email` exists in `mw_user`, Mindweaver automatically creates a standard user (`is_superadmin=False`, `is_active=True`). If the `preferred_username` collides with an existing username, a random 4-digit suffix (`username#1234`) is appended.
   - If the user already exists, their `display_name` is synchronized from the ID token.

---

## 3. User Management & Role-Based Access Control (RBAC)

### Administering Control Plane Users
Superadministrators (`is_superadmin=True`) have access to the **Administration > Users** section (`/users` in the UI, `/api/v1/users` in the API):
- **Create User**: Define `name` (username, immutable), `email` (immutable), `display_name`, `title`, initial `password`, `is_active`, and `is_superadmin`.
- **Update User**: Modify `display_name`, `title`, `is_active`, or promote/demote `is_superadmin`.
- **Change Password**:
  - Superadmins can reset any user's password via `POST /api/v1/users/{id}/_change_password` (minimum 8 characters).
  - Regular users can change their own password via the same endpoint for their own user ID, and update their own `display_name`/`title` via `PUT /api/v1/auth/me`.

> [!NOTE]
> Control plane users (`/users`) are distinct from **Project Local Users** (`ProjectLocalUser`), which are scoped to individual projects and used to populate static credentials in project-deployed services such as Dex.

### Permission Hierarchy
Mindweaver uses a class-based permission hierarchy (`backend/src/mindweaver/fw/permission.py`):
- **Superadmins (`is_superadmin = True`)**: Granted the root `All` (`Admin`) permission, which satisfies all permission checks across all services.
- **Standard Authenticated Users**: Default to the framework `Read` permission (`List` and `View`), allowing read-only inspection across services unless granted specific service-level permissions.
- **Service-Specific Permissions**: Every service defines a granular permission hierarchy under `<service>:*`:
  - `<service>:manage` (`Manage`): Root permission for the service, covering all read, write, and execute actions.
  - `<service>:read` (`Read`): Covers `<service>:list` and `<service>:view`.
  - `<service>:write` (`Write`): Covers `<service>:create`, `<service>:update`, and `<service>:delete`.
  - `<service>:execute` (`Execute`): Covers operational actions such as `_deploy`, `_decommission`, `_test-connection`, `_renew_certificate`, and cluster operator installations.

---

## 4. Secret Encryption & Redaction Policy

Mindweaver enforces strict handling of sensitive credentials (database passwords, S3 secret keys, LDAP bind passwords, SSH private keys, container registry tokens, and Kubernetes `kubeconfig` files) via `SecretHandlerMixin` and `mindweaver.crypto`.

### How Encryption Works
- All sensitive fields are encrypted at rest in PostgreSQL using **Fernet symmetric encryption** (`cryptography.fernet.Fernet`) with `MINDWEAVER_FERNET_KEY`.
- User passwords in `mw_user` are one-way hashed (not encrypted), whereas service credentials that Mindweaver must pass to Kubernetes manifests or external connections are encrypted with Fernet so the backend can decrypt them when rendering templates or testing connections.

### API Redaction Conventions
Whenever a resource containing sensitive fields is retrieved via `GET` endpoints:
- Sensitive fields are never returned in plain text or ciphertext; they are replaced with the literal string `__REDACTED__`.
- When updating a resource via `PUT`:
  - **Keep existing secret**: Pass `"__REDACTED__"` (the default behavior of the UI form when a password field is left untouched).
  - **Clear secret**: Pass `"__CLEAR__"` to set the stored value to an empty string.
  - **Replace secret**: Pass any other string to encrypt and store the new secret value.

### Rotating the Encryption Key (`MINDWEAVER_FERNET_KEY`)

If your security policy requires periodic key rotation or if a key needs to be replaced:

1. **Generate a new Fernet key**:
   ```bash
   uv run mindweaver crypto generate-key
   ```
2. **Run the key rotation command** while the database is accessible:
   ```bash
   uv run mindweaver crypto rotate-key \
     --old-key "<CURRENT-FERNET-KEY>" \
     --new-key "<NEW-FERNET-KEY>"
   ```
3. **Update `MINDWEAVER_FERNET_KEY`** in your environment (`.env` or Kubernetes Secret) and restart the API, Celery Worker, and Celery Beat pods/processes.
