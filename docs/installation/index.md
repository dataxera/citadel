# Citadel Installation & Kubernetes Operations Guide

This section covers deploying **Citadel** and setting up a production-ready **K3s** Kubernetes cluster with **Cilium CNI**, **OpenEBS LocalPV-LVM**, OS tuning, DNS, and **Disaster Recovery**.

## Guides

1. **[Citadel Quickstart (Single-Node Docker)](citadel-quickstart.md)**
   - Run the Citadel control plane (PostgreSQL, Redis, API, Celery Worker/Scheduler, and UI) on a single host using Docker / Docker Compose.
2. **[K3s Quickstart Setup](k3s-quickstart.md)**
   - Hardware & disk requirements.
   - OS `ulimits` and `sysctl` tuning for a **32 vCPU / 128 GB RAM** node running data platform workloads.
   - K3s installation (with embedded `etcd`, Flannel/Traefik/ServiceLB disabled).
   - **Cilium CNI** installation (eBPF kube-proxy replacement + L2 LoadBalancer IPAM).
   - **OpenEBS `lvm-localpv`** standalone installation for hard volume quotas and capacity-aware scheduling.
   - Wildcard DNS configuration pointing to your cluster Ingress / Gateway.
3. **[MetalLB LoadBalancer Setup](metallb-setup.md)**
   - Installing MetalLB on bare-metal / K3s clusters and configuring `IPAddressPool` and `L2Advertisement` (or BGP) for `LoadBalancer` services.
4. **[K3s Disaster Recovery Guide](k3s-disaster-recovery.md)**
   - Connecting two K3s clusters with **Cilium ClusterMesh**.
   - Automated & S3-backed **etcd snapshots** and full cluster restore procedures.
