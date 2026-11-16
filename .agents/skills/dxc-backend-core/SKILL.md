---
name: Citadel Backend Core
description: Basic model and service definitions in Citadel.
---
# Citadel Backend Core

This skill covers the fundamental patterns for creating standard services and models.

## Creating a New Backend Service

To create a new backend service that provides standard CRUD operations:

1.  **Define the Model**: Create a SQLModel class inheriting from `NamedBase` (or `ProjectScopedNamedBase` if it belongs to a project).
    ```python
    from citadel.fw.model import NamedBase
    from sqlmodel import Field

    class MyModel(NamedBase, table=True):
        __tablename__ = "my_model"
        some_field: str = Field(default="default")
    ```

2.  **Define the Service**: Create a Service class inheriting from `Service` (or `ProjectScopedService`).
    ```python
    from citadel.fw.service import Service

    class MyModelService(Service[MyModel]):
        @classmethod
        def model_class(cls):
            return MyModel
    ```

3.  **Register the Router**: Add the service router to `backend/src/citadel/app.py`.
    ```python
    from .service.my_service import MyModelService
    # ...
    app.include_router(MyModelService.router(), prefix="/api/v1")
    ```

This automatically provides endpoints for `GET`, `POST`, `PUT`, `DELETE`, and list operations, along with dynamic form schemas.

## Project Scoping and Multi-tenancy

For models that belong to a project, use the specialized base classes and services.

1.  **Models**: Inherit from `ProjectScopedNamedBase`.
    ```python
    from citadel.service.base import ProjectScopedNamedBase
    from sqlmodel import Field

    class ProjectResource(ProjectScopedNamedBase, table=True):
        __tablename__ = "project_resource"
        # project_id is automatically added
    ```

2.  **Services**: Inherit from `ProjectScopedService`.
    ```python
    from citadel.service.base import ProjectScopedService

    class ProjectResourceService(ProjectScopedService[ProjectResource]):
        @classmethod
        def model_class(cls):
            return ProjectResource
    ```

This ensures that the `X-Project-ID` header is required and automatically handled for filtering and injection.

## Database Migrations

Citadel uses Alembic for database migrations with the following CLI commands:

- **Generate a migration revision**: `uv run dxc db revision --autogenerate -m "<description>"`
- **Apply pending migrations**: `uv run dxc db migrate`

When adding new fields to existing models, always generate and apply a migration after updating the model definition.
