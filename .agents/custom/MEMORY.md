# Agent Memory / Lessons Learned

## NiFiKop: JKS Secret Cleanup on Decommission (2026-06-25)

When NiFiKop uses `sslSecrets.create: true` with an external `issuerRef`, the `FinalizePKI` 
function does NOT clean up the per-node JKS password secrets (e.g., `{name}-0-server-certificate`).
These secrets must be manually deleted before redeploying a NiFiCluster with the same name.

Symptoms of stale JKS secrets: 
- `"could not create secret with jks password: secrets already exists"`
- `"failed to decode x509 certificate from PEM"` (cascading error)

Fix: `kubectl delete secret {nifi-name}-{nodeId}-server-certificate -n {namespace}`

## Force Decommission vs Active Service Dependencies (2026-10-26)

Force decommission (`force=True`) is intended to bypass Kubernetes cluster communication issues (unreachable cluster or cluster resource deletion errors), but it MUST NOT bypass the dependency check when there are still active/deployed running services depending on this service. Decommissioning a dependency while consumers are still running orphans the consumers and prevents them from rendering manifests or decommissioning cleanly. Only when dependent services are inactive (`active=False`) or already decommissioned should decommissioning proceed.

## Container Management: start.sh and stop.sh (2026-11-15)

Always use `./stop.sh` and `./start.sh` in the project root to stop and start the local development containers rather than manual `docker compose` or `docker compose restart` commands.
- `./stop.sh`: invokes `docker compose --profile=app down` ensuring all profiled services (`web`, `worker`, `scheduler`, `frontend`, `proxy`, `migrate`) are cleanly brought down.
- `./start.sh`: invokes `docker compose --profile=app up -d` ensuring the full stack and migration checks run properly.
