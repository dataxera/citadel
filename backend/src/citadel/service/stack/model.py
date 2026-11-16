# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

from typing import Any
from sqlmodel import Field
from sqlalchemy_utils import JSONType
from citadel.fw.model import NamedBase


class Stack(NamedBase, table=True):
    __tablename__ = "dxc_stack"

    version: str = Field(sa_column_kwargs={"unique": True})
    configuration: dict[str, Any] = Field(default_factory=dict, sa_type=JSONType())

    def get_image_for_component(self, component_name: str, image_key: str = "main") -> tuple[str | None, str | None]:
        """
        Returns (image_repository, image_tag) for the given component and image key.
        """
        components = self.configuration.get("components", {})
        comp = components.get(component_name)
        if not comp:
            return None, None
        images = comp.get("images", {})
        img_info = images.get(image_key)
        if not img_info:
            return None, None
        return img_info.get("repository"), img_info.get("tag")

    def get_package_type_for_component(self, component_name: str) -> str | None:
        """
        Returns the package type ('helm' or 'yml') for the given component, or None if not found.
        """
        components = self.configuration.get("components", {})
        comp = components.get(component_name)
        if not comp:
            return None
        package_type = comp.get("package_type")
        if package_type in ("helm", "yml"):
            return package_type
        if comp.get("charts") or comp.get("chart_version"):
            return "helm"
        return "yml"

    def get_custom_config(self, component_name: str) -> dict[str, Any]:
        """
        Returns custom configuration dict for the given component.
        """
        components = self.configuration.get("components", {})
        comp = components.get(component_name)
        if not comp:
            return {}
        return comp.get("custom_config", {})

    def get_chart_version_for_component(self, component_name: str) -> str | None:
        """
        Returns the chart version for the given component.
        """
        components = self.configuration.get("components", {})
        comp = components.get(component_name)
        if not comp:
            return None
        version = comp.get("chart_version")
        if not version:
            charts = comp.get("charts", {})
            main_chart = charts.get("main", {})
            version = main_chart.get("version")
        return version

    def get_chart_for_component(
        self, component_name: str, chart_key: str = "main"
    ) -> tuple[str | None, str | None, str | None]:
        """
        Returns (repo_url, chart_name, chart_version) for the given component and chart key.
        """
        components = self.configuration.get("components", {})
        comp = components.get(component_name)
        if not comp:
            return None, None, None
        charts = comp.get("charts", {})
        chart_info = charts.get(chart_key)
        if not chart_info:
            return None, None, None
        return chart_info.get("repo"), chart_info.get("chart"), chart_info.get("version")


