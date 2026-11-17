# Production Cluster Hardware Requirements

This guide defines the recommended hardware specifications, cluster topologies, networking, and disk partitioning layouts for running **Citadel** and its data/AI platform workloads in production on Kubernetes (K3s + Cilium + OpenEBS `lvm-localpv`).

---

## 1. Topology Options

Citadel supports two production cluster topologies depending on your isolation and operational requirements:

| Topology | Description | Best For |
| :--- | :--- | :--- |
| **Standard (Converged)** | Minimum **3 nodes** where each node runs both Kubernetes control-plane (`etcd` + API server) and data workloads. | Most production deployments; maximizes hardware utilization and keeps footprint compact. |
| **Separate Control Plane** | **3 dedicated control-plane nodes** (for HA `etcd` quorum) isolated from dedicated worker nodes (**minimum 3 nodes**). | Strict workload isolation, larger clusters, or environments where heavy data/AI jobs must never contend with `etcd`/API server resources. |

---

## 2. Standard Setup (Converged Cluster)

Minimum **3 nodes** (required for 3-member `etcd` high-availability quorum and distributed workload placement).

### Per-Node Hardware Specification (Minimum 3 Nodes)

| Resource | Specification | Purpose |
| :--- | :--- | :--- |
| **CPU** | **32 vCore** | Runs Kubernetes control plane + data/AI workloads (Trino, Doris, Kafka, Airflow, PostgreSQL, etc.). |
| **RAM** | **128 GB – 256 GB** *(4–8 GB per vCore)* | **128 GB** minimum for moderate stacks (~112 GB allocatable after OS/kubelet); **256 GB** recommended for concurrent OLAP/JVM engines or local AI/vector DB workloads. |
| **OS & `etcd`** | **2x 256 GB Enterprise SSD/NVMe** (RAID 1) | Mirrored boot/OS and `etcd` state, isolated from log and container I/O. |
| **Ephemeral & Logs** | **1 TB Enterprise NVMe/SSD** | Container images (`containerd`), writable container layers, `kubelet` `emptyDir` scratch/spill space, and `/var/log`. |
| **PVC Storage** | **2x 2 TB Enterprise NVMe/SSD** | Dedicated raw block storage for `vg_citadel` (OpenEBS `lvm-localpv`) serving persistent databases and message queues. |
| **Network** | **2x 10 GbE** *(2x 25 GbE recommended)* | LACP (`802.3ad`) bonded NICs for redundancy and high-throughput shuffle/replication traffic. |

**Cluster Totals (3-Node Minimum):** 96 vCore, 384 GB – 768 GB RAM, ~12 TB raw PVC storage (across `vg_citadel`).

---

## 3. Separate Control Plane Setup

Separating the control plane prevents CPU, memory, and I/O spikes from data workloads (such as compaction, shuffle, or OOM events) from destabilizing `etcd` or `kube-apiserver`.

### 3.1 Control Plane Nodes (3 Nodes Required for Production HA)

Dedicated control-plane nodes are tainted (`node-role.kubernetes.io/control-plane:NoSchedule`) so they run only Kubernetes control-plane components, `etcd`, Cilium Operator, ArgoCD, and Citadel control-plane services.

| Resource | Specification | Purpose |
| :--- | :--- | :--- |
| **Node Count** | **3 nodes** | Required for `etcd` quorum and zero-downtime control-plane maintenance. |
| **CPU** | **4 vCore** | `kube-apiserver`, `etcd`, `kube-controller-manager`, `kube-scheduler`, Cilium Operator. |
| **RAM** | **16 GB** | Comfortable headroom for `etcd` memory-mapped DB, API server caches, and ArgoCD/Citadel control plane. |
| **OS & `etcd`** | **2x 256 GB Enterprise SSD/NVMe** (RAID 1) | Mirrored OS and `etcd` WAL/DB. |
| **Ephemeral & Logs** | **256 GB Enterprise NVMe/SSD** *(optional separate disk)* | Control-plane container images, `/var/lib/rancher/k3s` state, and `/var/log`. Can be omitted and placed on the `2x 256 GB` RAID 1 OS mirror if desired. |
| **Network** | **2x 10 GbE** (LACP bonded) | Redundant control-plane and `etcd` peer communication. |

### 3.2 Worker Nodes (Minimum 3 Nodes)

| Resource | Specification | Purpose |
| :--- | :--- | :--- |
| **Node Count** | **Minimum 3 nodes** | Distributed scheduling, PodDisruptionBudgets, and application-level replication across failure domains. |
| **CPU** | **32 vCore** | Data and AI platform workloads. |
| **RAM** | **128 GB – 256 GB** *(4–8 GB per vCore)* | **128 GB** minimum; **256 GB** recommended for heavy concurrent OLAP/JVM or self-hosted AI/vector workloads. |
| **OS** | **2x 256 GB Enterprise SSD/NVMe** (RAID 1) | Mirrored OS. |
| **Ephemeral & Logs** | **1 TB Enterprise NVMe/SSD** | Container image cache (`containerd`), `kubelet` `emptyDir`, runtime scratch space, and `/var/log`. |
| **PVC Storage** | **2x 2 TB Enterprise NVMe/SSD** | Dedicated to `vg_citadel` for OpenEBS `lvm-localpv` persistent volumes. |
| **Network** | **2x 10 GbE** *(2x 25 GbE recommended)* | LACP (`802.3ad`) bonded NICs for cluster, shuffle, and storage replication traffic. |

---

## 4. Drive & Network Standards

### 4.1 SSD / NVMe Requirements
Do **not** use consumer SATA or QLC SSDs in production:
- **Power Loss Protection (PLP):** Mandatory for OS/`etcd` and PVC drives. `etcd` is highly sensitive to `fsync` latency; drives without PLP stall `fsync` calls and cause `etcd` leader elections or cluster instability.
- **Endurance:** Use **Enterprise NVMe** (recommended) or Enterprise SAS/SATA SSDs rated for **≥ 1–3 DWPD** (Drive Writes Per Day) to handle sustained writes from Kafka, Apache Doris BE, PostgreSQL WAL, and container logs.
- **Interface:** NVMe PCIe Gen4 (or Gen3) is strongly preferred over SATA for PVC and `etcd` volumes.

### 4.2 Network Requirements
- **Minimum:** **2x 10 GbE** per node configured in an **LACP (`802.3ad`) bond** for link redundancy and aggregated bandwidth.
- **Recommended for Heavy Data/AI Stacks:** **2x 25 GbE** (LACP bonded) when running high-throughput Trino/Doris distributed joins, Kafka cross-broker replication, and large model/image pulls.
- **Traffic Isolation:** Separate VLANs for Kubernetes/management traffic and data/replication traffic where network infrastructure permits.

---

## 5. Recommended Disk Partitioning

Separating OS/`etcd`, ephemeral/logs, and persistent volumes onto distinct physical devices prevents runaway logs or `emptyDir` spikes from starving `etcd` `fsync` latency or filling the root filesystem.

### 5.1 OS & `etcd` Disks (`2x 256 GB` — RAID 1)

Configure the two 256 GB drives in **RAID 1** (hardware RAID or Linux `mdadm`), with an LVM Volume Group `vg_os` on the root partition:

| Partition / LV | Size | Filesystem | Mount Point | Notes |
| :--- | :--- | :--- | :--- | :--- |
| `efi` (on each disk) | `512 MB – 1 GB` | `vfat` (FAT32) | `/boot/efi` | EFI System Partition. |
| `md0` (`/boot`) | `1 GB – 2 GB` | `ext4` | `/boot` | Kernel and initramfs (`mdadm` metadata 1.0 or 1.2). |
| `vg_os/lv_root` | `80 GB` | `ext4` or `xfs` | `/` | Operating system binaries and packages. |
| `vg_os/lv_etcd` *(converged / CP)* | `30 GB` | `ext4` or `xfs` | `/var/lib/rancher/k3s/server/db` | Isolates `etcd` WAL/DB and snapshots on dedicated mirrored drives, free from `/var/log` contention. *(Omit on worker-only nodes.)* |
| `vg_os/lv_swap` *(optional)* | `4 GB – 8 GB` | `swap` | `swap` | Only if using `vm.swappiness=1` with kubelet swap support; omit if swap is disabled. |
| *Unallocated in `vg_os`* | `~130–140 GB` | — | — | Free buffer for online `lvextend` if `/` grows. |

### 5.2 Ephemeral & Logs Disk (`1 TB` on Workers/Converged, `256 GB` on Control Plane)

Initialize the ephemeral disk as an LVM Volume Group `vg_ephemeral` so `containerd` images, `kubelet` `emptyDir` usage, and `/var/log` cannot starve each other or impact `vg_os`:

#### Worker / Converged Node (`1 TB` SSD/NVMe)

| Logical Volume | Size | Filesystem | Mount Point | Notes |
| :--- | :--- | :--- | :--- | :--- |
| `vg_ephemeral/lv_k3s` | `550 GB` | `xfs` or `ext4` (`noatime`) | `/var/lib/rancher/k3s` | Stores `containerd` images, snapshots, and writable container layers. |
| `vg_ephemeral/lv_kubelet` | `250 GB` | `xfs` or `ext4` (`noatime`) | `/var/lib/kubelet` | Stores pod `emptyDir` volumes, configmap/secret mounts, and kubelet state. |
| `vg_ephemeral/lv_var_log` | `100 GB` | `xfs` or `ext4` (`noatime`) | `/var/log` | Isolates `journald`, audit logs, and container logs from the OS/`etcd` mirror. |
| *Unallocated in `vg_ephemeral`* | `~100 GB` | — | — | Headroom for online expansion of any volume above. |

*(On converged nodes where `/var/lib/rancher/k3s/server/db` is mounted from `vg_os/lv_etcd`, ensure `lv_etcd` is mounted **after** `/var/lib/rancher/k3s` in `/etc/fstab`.)*

#### Dedicated Control Plane Node (`256 GB` SSD/NVMe, if separate)

| Logical Volume | Size | Filesystem | Mount Point | Notes |
| :--- | :--- | :--- | :--- | :--- |
| `vg_ephemeral/lv_k3s` | `120 GB` | `xfs` or `ext4` (`noatime`) | `/var/lib/rancher/k3s` | Control-plane images and K3s state. |
| `vg_ephemeral/lv_kubelet` | `50 GB` | `xfs` or `ext4` (`noatime`) | `/var/lib/kubelet` | Control-plane pod mounts and kubelet state. |
| `vg_ephemeral/lv_var_log` | `50 GB` | `xfs` or `ext4` (`noatime`) | `/var/log` | Control-plane and API audit logs. |
| *Unallocated in `vg_ephemeral`* | `~36 GB` | — | — | Headroom for online expansion. |

*(If you omit the separate `256 GB` disk on dedicated control-plane nodes, create `vg_os/lv_var_log` at `50 GB` on the `2x 256 GB` RAID 1 OS mirror and use the remaining `vg_os` buffer for `/var/lib/rancher/k3s` and `/var/lib/kubelet`.)*

### 5.3 PVC Storage Disks (`2x 2 TB` on Workers/Converged)

Do **not** create a filesystem or mount these disks directly. Citadel uses **OpenEBS `lvm-localpv`** (Volume Group `vg_citadel`) to dynamically provision Logical Volumes with hard size quotas per PVC.

Because Citadel's stateful data platform components (Kafka, Apache Doris BE, Elasticsearch, CloudNativePG, MinIO, etc.) provide **native application-layer replication** across nodes, local LVM volumes do not require hardware/software RAID mirroring:

```bash
# Add both raw NVMe/SSD devices directly to vg_citadel (~4 TB usable per node)
sudo pvcreate /dev/nvme2n1 /dev/nvme3n1
sudo vgcreate vg_citadel /dev/nvme2n1 /dev/nvme3n1
```

- **Usable Capacity:** **~4 TB per node** (**~12 TB** across a 3-node cluster).
- **Optional RAID 1:** Only needed if you deploy an un-replicated single-instance stateful service where local single-drive redundancy is required (~2 TB usable per node).

---

## 6. OS & Kernel Tuning

- **Filesystem Mount Options:** Mount `/var/lib/rancher/k3s`, `/var/lib/kubelet`, and `/var/log` with `noatime` to reduce SSD write amplification.
- **TRIM / Discard:** Enable periodic `fstrim.timer` on SSD/NVMe drives (`sudo systemctl enable --now fstrim.timer`).
- **Kernel & `ulimits`:** Apply the `sysctl` and `ulimits` configuration in the [K3s Quickstart Setup](k3s-quickstart.md) before joining nodes to the cluster.

<!--
SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
SPDX-License-Identifier: AGPLv3+
-->
