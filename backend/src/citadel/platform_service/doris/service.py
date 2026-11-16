# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

from datetime import datetime, timezone
import asyncio
import os
import secrets
import logging
from typing import Any
from kubernetes import client
from citadel.platform_service.base import PlatformService
from citadel.crypto import decrypt_password, encrypt_password
from .model import DorisPlatform, DorisPlatformState

logger = logging.getLogger(__name__)


class DorisPlatformService(PlatformService[DorisPlatform]):
    """Platform service for provisioning and managing Apache Doris clusters."""

    template_directory: str = os.path.join(os.path.dirname(__file__), "templates")
    state_model: type[DorisPlatformState] = DorisPlatformState

    @classmethod
    def model_class(cls) -> type[DorisPlatform]:
        """Returns the DorisPlatform model class."""
        return DorisPlatform

    @classmethod
    def service_path(cls) -> str:
        """Returns the base API path for this service."""
        return "/platform/doris"

    @classmethod
    def internal_fields(cls) -> list[str]:
        """Fields not exposed in standard resource representations."""
        return super().internal_fields() + ["admin_password", "operator_password"]

    @classmethod
    def redacted_fields(cls) -> list[str]:
        """Fields that are redacted in API responses."""
        return ["admin_password", "operator_password"]

    @classmethod
    def widgets(cls) -> dict[str, Any]:
        """Returns the DynamicForm widgets configuration for UI fields."""
        return {
            **super().widgets(),
            "fe_replicas": {
                "order": 5,
                "type": "range",
                "min": 1,
                "max": 9,
                "step": 2,
                "label": "FE Replicas",
            },
            "be_replicas": {
                "order": 6,
                "type": "range",
                "min": 1,
                "max": 16,
                "step": 1,
                "label": "BE Replicas",
            },
            "fe_storage_size": {
                "order": 7,
                "label": "FE Storage Size (Meta)",
            },
            "be_storage_size": {
                "order": 8,
                "label": "BE Storage Size (Data)",
            },
            "fe_cpu_request": {
                "order": 10,
                "type": "range",
                "min": 0.1,
                "max": 16,
                "step": 0.1,
                "label": "FE CPU Request",
            },
            "fe_cpu_limit": {
                "order": 11,
                "type": "range",
                "min": 0.1,
                "max": 16,
                "step": 0.1,
                "label": "FE CPU Limit",
            },
            "fe_mem_request": {
                "order": 12,
                "type": "range",
                "min": 0.5,
                "max": 64,
                "step": 0.5,
                "label": "FE Memory Request (Gi)",
            },
            "fe_mem_limit": {
                "order": 13,
                "type": "range",
                "min": 0.5,
                "max": 64,
                "step": 0.5,
                "label": "FE Memory Limit (Gi)",
            },
            "be_cpu_request": {
                "order": 14,
                "type": "range",
                "min": 0.1,
                "max": 16,
                "step": 0.1,
                "label": "BE CPU Request",
            },
            "be_cpu_limit": {
                "order": 15,
                "type": "range",
                "min": 0.1,
                "max": 16,
                "step": 0.1,
                "label": "BE CPU Limit",
            },
            "be_mem_request": {
                "order": 16,
                "type": "range",
                "min": 0.5,
                "max": 64,
                "step": 0.5,
                "label": "BE Memory Request (Gi)",
            },
            "be_mem_limit": {
                "order": 17,
                "type": "range",
                "min": 0.5,
                "max": 64,
                "step": 0.5,
                "label": "BE Memory Limit (Gi)",
            },
        }

    async def template_vars(self, model: DorisPlatform) -> dict:
        """Resolves template variables required to render Doris manifests."""
        vars = model.model_dump()

        if model.admin_password:
            try:
                vars["admin_password"] = decrypt_password(model.admin_password)
            except Exception:
                vars["admin_password"] = model.admin_password

        vars["operator_username"] = "doris_operator"
        operator_pass = model.operator_password
        if operator_pass:
            try:
                operator_pass = decrypt_password(operator_pass)
            except Exception:
                operator_pass = model.operator_password
        else:
            operator_pass = secrets.token_urlsafe(16)
        vars["operator_password"] = operator_pass

        # Resolve FE image & tag
        vars["fe_image"], vars["fe_image_tag"] = await self.resolve_image(
            model, "doris", "selectdb/doris.fe-ubuntu", "2.1.8", image_key="fe"
        )
        # Resolve BE image & tag
        vars["be_image"], vars["be_image_tag"] = await self.resolve_image(
            model, "doris", "selectdb/doris.be-ubuntu", "2.1.8", image_key="be"
        )

        chart_repo, chart_name, chart_version = await self.resolve_chart(
            model, "doris", "main", "https://charts.selectdb.com", "doris", "25.8.0"
        )
        vars["chart_repo"] = chart_repo
        vars["chart_name"] = chart_name
        vars["chart_version"] = chart_version

        vars["namespace"] = await self._resolve_namespace(model)
        project = await self.project(model)
        vars["ingress_domain"] = project.ingress_domain

        return vars

    async def restart_service(self, model: DorisPlatform) -> dict:
        """Trigger a rolling restart of Doris FE and BE StatefulSets."""
        kubeconfig = await self.kubeconfig(model)
        namespace = await self._resolve_namespace(model)
        restarted_at = datetime.now(tz=timezone.utc).isoformat()

        def _restart() -> dict:
            k8s_client = self._build_k8s_client(kubeconfig)
            apps_api = client.AppsV1Api(k8s_client)
            restarted: list[str] = []

            try:
                stateful_sets = apps_api.list_namespaced_stateful_set(
                    namespace=namespace
                )
                for sts in stateful_sets.items:
                    if sts.metadata and sts.metadata.name and sts.metadata.name.startswith(f"{model.name}-"):
                        self._patch_workload_restarted_at(
                            apps_api, namespace, "StatefulSet", sts.metadata.name, restarted_at
                        )
                        restarted.append(f"StatefulSet/{sts.metadata.name}")
            except client.exceptions.ApiException as e:
                logger.error(f"Failed to restart Doris cluster {model.name}: {e}")
                raise RuntimeError(f"Failed to restart {model.name}: {e.reason}")

            if not restarted:
                raise RuntimeError(
                    f"No restartable workloads found for {model.name} in namespace {namespace}"
                )

            logger.info(f"Triggered rolling restart for {model.name}: {restarted}")
            return {"status": "success", "restarted": restarted}

        return await asyncio.to_thread(_restart)
