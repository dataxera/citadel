# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

import pytest
from sqlmodel import SQLModel, Field
from typing import Optional
from citadel.fw.service import Service
from citadel.fw.registry import SERVICE_REGISTRY
from citadel.fw.model import NamedBase
from sqlalchemy_utils import JSONType


class MockTarget(NamedBase):
    pass


class MockTargetService(Service[MockTarget]):
    @classmethod
    def model_class(cls) -> type[MockTarget]:
        return MockTarget


class MockModel(NamedBase):
    project_id: int = Field(foreign_key="dxc_project.id")
    knowledge_db_ids: list[int] = Field(
        default=[], sa_type=JSONType(), foreign_key="dxc_knowledge_db.id"
    )
    datasource_ids: list[int] = Field(
        default=[], sa_type=JSONType(), foreign_key="dxc_datasource.id"
    )
    s3_storage_id: int = Field(default=None, foreign_key="dxc_s3_storage.id")
    custom_field: str = Field(default="test")


class MockService(Service[MockModel]):
    @classmethod
    def model_class(cls) -> type[MockModel]:
        return MockModel


def test_relationship_label_generation():
    # Backup registry
    original_registry = SERVICE_REGISTRY.copy()

    try:
        # Register mock services to registry
        SERVICE_REGISTRY["dxc_project"] = MockTargetService
        SERVICE_REGISTRY["dxc_datasource"] = MockTargetService
        SERVICE_REGISTRY["dxc_knowledge_db"] = MockTargetService
        SERVICE_REGISTRY["dxc_s3_storage"] = MockTargetService

        widgets = MockService.get_widgets()

        # Check relationship detection and label generation
        assert widgets["project_id"]["type"] == "relationship"
        assert widgets["project_id"]["label"] == "Project"

        assert widgets["s3_storage_id"]["type"] == "relationship"
        assert widgets["s3_storage_id"]["label"] == "S3 Storage"

        assert widgets["knowledge_db_ids"]["type"] == "relationship"
        assert widgets["knowledge_db_ids"]["label"] == "Knowledge DB"

        assert widgets["datasource_ids"]["type"] == "relationship"
        assert widgets["datasource_ids"]["label"] == "Datasource"
    finally:
        # Restore registry
        SERVICE_REGISTRY.clear()
        SERVICE_REGISTRY.update(original_registry)
