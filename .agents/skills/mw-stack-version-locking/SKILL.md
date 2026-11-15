---
name: MindWeaver Stack Version Locking
description: Checklist and patterns for keeping platform services, Kubernetes integrations, stack YAMLs, and unit tests aligned when adding services/image roles or updating stack versions.
---
# MindWeaver Stack Version Locking

Use this skill whenever you:
- Introduce a new platform service (`backend/src/mindweaver/platform_service/<service>/`)
- Introduce a new Kubernetes cluster integration (`backend/src/mindweaver/service/k8s_cluster/`)
- Add a new container, initContainer, sidecar, or pooler to an existing service or integration
- Update chart or image versions in a stack file (`backend/src/mindweaver/resources/stacks/*.yml`)

---

## 1. Stack YAML (`backend/src/mindweaver/resources/stacks/*.yml`)

Every platform service and Kubernetes integration must have an entry under `configuration.components.<component>`:

```yaml
    my_service:
      package_type: helm
      charts:
        main:
          repo: https://charts.example.com
          chart: my-chart
          version: "1.2.3"
      images:
        main:
          repository: registry.example.com/org/my-service
          tag: "1.2.3"
        sidecar_or_init:
          repository: registry.example.com/org/helper
          tag: "0.4.5"
```

Rules:
- All chart `version` and image `tag` values must be pinned (never `latest` or `*-latest`).
- Every container, initContainer, sidecar, or operator-managed workload (e.g. `pgbouncer`, `redis`, `statsd_exporter`, `git_sync`, `init`, `prepare_tls`, `envoy`, `dex`) must have its own image role under `images`.

---

## 2. Platform Services (`backend/src/mindweaver/platform_service/<service>/`)

### `service.py` (`template_vars`)
1. Resolve the Helm chart using `self.resolve_chart(...)` with pinned fallback defaults matching the current stack:
   ```python
   chart_repo, chart_name, chart_version = await self.resolve_chart(
       model, "<component>", "main", "<default_repo>", "<default_chart>", "<default_version>"
   )
   ```
2. Resolve **every** image role using `self.resolve_image(..., image_key="<role>")` with pinned fallback defaults:
   ```python
   main_img, main_tag = await self.resolve_image(
       model, "<component>", "<default_repo>:<default_tag>"
   )
   helper_img, helper_tag = await self.resolve_image(
       model, "<component>", "<helper_repo>", "<helper_tag>", image_key="<role>"
   )
   ```

### `templates/*.yml.j2`
- Pass `chart_repo`, `chart_name`, and `chart_version` to `spec.source` (`repoURL`, `chart`, `targetRevision`).
- Pass every resolved image variable into the Helm `values` (or CR `spec`) so no container or initContainer falls back to an operator/chart default or hardcoded tag.
- Shared initContainer templates (such as `backend/src/mindweaver/resources/templates/trusted_cert_pod.yml.j2`) must accept a resolved variable (e.g. `prepare_tls_image`) rather than hardcoding an image.

---

## 3. Kubernetes Integrations (`backend/src/mindweaver/service/k8s_cluster/`)

### `actions.py`
In each `Install*Action.run`:
1. Resolve the chart via `await self.resolve_integration_chart("<component>", "main", ...)`.
2. Resolve **every** image role via `await self.resolve_integration_image("<component>", "<role>", ...)`.
3. Pass all resolved chart and image variables into `self._apply_template(...)` (for ArgoCD-managed integrations) or `set_vals` in `self._install_helm_chart(...)` (for direct Helm installs like `argocd`).

### `templates/*.yml.j2`
- Ensure `repoURL`, `chart`, `targetRevision`, and all Helm `values` / CR `spec` image fields render the resolved variables.
- Watch out for chart-specific image structures (e.g. Strimzi splits `image.registry`, `image.repository`, `image.name`, `image.tag`; Envoy Proxy image is set on `EnvoyProxy.spec.provider.kubernetes.envoyDeployment.container.image`).

---

## 4. Unit Testing (`backend/tests/`)

- **Do NOT** read `backend/src/mindweaver/resources/stacks/mindweaver-*.yml` or hardcode production stack versions in unit tests. Updating the production stack should never break unit tests.
- Use the dedicated test stack file `backend/tests/resources/test-stack.yml` and the `test_stack` / `test_stack_session` fixtures in `backend/tests/conftest.py`.
- Whenever you add a new component or image role:
  1. Add it to `backend/tests/resources/test-stack.yml` using distinct test-only values (e.g. `test.registry/...` and `*.99*` tags).
  2. Add the component name to `expected_components` in `backend/tests/service/test_stack.py`.
  3. Add or update unit tests for the service/integration using `test_stack` or `test_stack_session` to verify all chart versions and image roles are resolved and rendered into the manifest/Helm args.

---

## 5. Verification

1. Run backend tests:
   ```bash
   uv run --package mindweaver pytest backend/tests/platform_service/ backend/tests/service/test_stack.py backend/tests/service/k8s_cluster/test_k8s_cluster.py
   ```
2. When a Kubernetes cluster is available, inspect running pods and initContainers to verify no untracked or `latest` images are deployed:
   ```bash
   kubectl get pods -A -o custom-columns="NAMESPACE:.metadata.namespace,NAME:.metadata.name,INIT:.spec.initContainers[*].image,IMAGE:.spec.containers[*].image"
   ```
