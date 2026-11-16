# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

from datetime import datetime, timezone
import os
import logging
import asyncio
import tempfile
from typing import Any, Optional
from kubernetes import client, config
from mindweaver.platform_service.base import PlatformService
from mindweaver.fw.model import ts_now

from .model import KafkaPlatform, KafkaPlatformState

logger = logging.getLogger(__name__)


class KafkaPlatformService(PlatformService[KafkaPlatform]):
    """Platform service for Apache Kafka."""

    template_directory: str = os.path.join(os.path.dirname(__file__), "templates")
    state_model: type[KafkaPlatformState] = KafkaPlatformState

    @classmethod
    def model_class(cls) -> type[KafkaPlatform]:
        """Returns the model class managed by this service."""
        return KafkaPlatform

    @classmethod
    def service_path(cls) -> str:
        """Returns the REST path prefix for this service."""
        return "/platform/kafka"


    @classmethod
    def widgets(cls) -> dict[str, Any]:
        """Provides UI configuration widgets for metadata rendering."""
        return {
            **super().widgets(),
            "storage_size": {"order": 7, "label": "Storage Size"},
            "replica_count": {
                "order": 10,
                "type": "range",
                "min": 1,
                "max": 9,
                "step": 1,
            },
            "cpu_request": {
                "order": 11,
                "type": "range",
                "min": 0.1,
                "max": 16,
                "step": 0.1,
            },
            "cpu_limit": {
                "order": 12,
                "type": "range",
                "min": 0.1,
                "max": 16,
                "step": 0.1,
            },
            "mem_request": {
                "order": 13,
                "type": "range",
                "min": 0.5,
                "max": 64,
                "step": 0.5,
                "label": "Memory Request (Gi)",
            },
            "mem_limit": {
                "order": 14,
                "type": "range",
                "min": 0.5,
                "max": 64,
                "step": 0.5,
                "label": "Memory Limit (Gi)",
            },
            "enable_loadbalancer": {
                "order": 15,
                "type": "boolean",
                "label": "Enable Load Balancer",
            },
            "additional_properties": {
                "order": 100,
                "label": "Additional Properties",
                "type": "key-value",
            },
        }

    async def template_vars(self, model: KafkaPlatform) -> dict:
        """Resolves template variables required for rendering manifests."""
        vars = model.model_dump()
        self.populate_scheduling_vars(
            model, vars, pod_labels={"strimzi.io/cluster": model.name}
        )
        vars["image"], vars["image_tag"] = await self.resolve_image(
            model, "kafka", "ghcr.io/kagesenshi/mindweaver/kafka", "4.0.0-rev.1"
        )
        chart_repo, chart_name, chart_version = await self.resolve_chart(
            model, "kafka", "main", "ghcr.io/kagesenshi/mindweaver/charts", "kafka", "0.1.3"
        )
        vars["chart_repo"] = chart_repo
        vars["chart_name"] = chart_name
        vars["chart_version"] = chart_version
        vars["override_image"] = True
        vars["namespace"] = await self._resolve_namespace(model)
        project = await self.project(model)
        vars["ingress_domain"] = project.ingress_domain
        return vars

    async def restart_service(self, model: KafkaPlatform) -> dict:
        """Trigger a rolling restart of StrimziPodSets and Kafka Deployments."""
        kubeconfig = await self.kubeconfig(model)
        namespace = await self._resolve_namespace(model)
        restarted_at = datetime.now(tz=timezone.utc).isoformat()

        def _restart() -> dict:
            k8s_client = self._build_k8s_client(kubeconfig)
            custom_api = client.CustomObjectsApi(k8s_client)
            apps_api = client.AppsV1Api(k8s_client)
            restarted: list[str] = []

            try:
                pod_sets = custom_api.list_namespaced_custom_object(
                    group="core.strimzi.io",
                    version="v1beta2",
                    namespace=namespace,
                    plural="strimzipodsets",
                    label_selector=f"strimzi.io/cluster={model.name}",
                )
                for pod_set in pod_sets.get("items") or []:
                    ps_name = (pod_set.get("metadata") or {}).get("name")
                    if not ps_name:
                        continue
                    custom_api.patch_namespaced_custom_object(
                        group="core.strimzi.io",
                        version="v1beta2",
                        namespace=namespace,
                        plural="strimzipodsets",
                        name=ps_name,
                        body={
                            "metadata": {
                                "annotations": {
                                    "strimzi.io/manual-rolling-update": "true"
                                }
                            }
                        },
                    )
                    restarted.append(f"StrimziPodSet/{ps_name}")

                deployments = apps_api.list_namespaced_deployment(
                    namespace=namespace,
                    label_selector=f"strimzi.io/cluster={model.name}",
                )
                for dep in deployments.items:
                    if dep.metadata and dep.metadata.name:
                        self._patch_workload_restarted_at(
                            apps_api, namespace, "Deployment", dep.metadata.name, restarted_at
                        )
                        restarted.append(f"Deployment/{dep.metadata.name}")
            except client.exceptions.ApiException as e:
                logger.error(f"Failed to restart Kafka cluster {model.name}: {e}")
                raise RuntimeError(f"Failed to restart {model.name}: {e.reason}")

            if not restarted:
                raise RuntimeError(
                    f"No restartable workloads found for {model.name} in namespace {namespace}"
                )

            logger.info(f"Triggered rolling restart for {model.name}: {restarted}")
            return {"status": "success", "restarted": restarted}

        return await asyncio.to_thread(_restart)


router = KafkaPlatformService.router()

# Register the poller class
from .poller import KafkaPoller
