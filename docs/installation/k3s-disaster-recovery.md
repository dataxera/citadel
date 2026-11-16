# K3s Disaster Recovery Guide

This guide covers two complementary layers of resilience for Citadel's Kubernetes infrastructure:
1. **Multi-Cluster Connectivity (Cilium ClusterMesh)**: Connecting two independent K3s clusters over Cilium so workloads and data services can communicate cross-cluster or fail over.
2. **etcd Backup & Restore**: Automated off-cluster `etcd` snapshots and recovery procedures for restoring cluster state after node or control-plane failure.

---

## Part 1: Connecting Two K3s Clusters with Cilium ClusterMesh

### Prerequisites & Network Planning

For Cilium ClusterMesh to route pod-to-pod and service-to-service traffic between two clusters, **Pod CIDRs, Service CIDRs, and Cluster IDs must NOT overlap**:

| Parameter | Cluster 1 (`citadel-primary`) | Cluster 2 (`citadel-dr`) |
| :--- | :--- | :--- |
| **Cluster Name** | `citadel-primary` | `citadel-dr` |
| **Cluster ID** (`1`–`255`) | `1` | `2` |
| **Pod CIDR** | `10.42.0.0/16` | `10.44.0.0/16` |
| **Service CIDR** | `10.43.0.0/16` | `10.45.0.0/16` |

### Required Firewall Ports Between Clusters
Ensure nodes in both clusters can reach each other on:
- `2379–2380/tcp` (ClusterMesh `etcd` / API if exposed via NodePort/LB)
- `32379/tcp` (or LoadBalancer port `2379` for `clustermesh-apiserver`)
- `8472/udp` (VXLAN) or `51871/udp` (WireGuard, if Cilium encryption is enabled)
- `4240/tcp` (Cilium health checks)

### Step 1: Install K3s on Both Clusters with Non-Overlapping CIDRs

**On Cluster 1 (`citadel-primary`)**:
```bash
curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="server \
  --cluster-init \
  --flannel-backend=none \
  --disable-network-policy \
  --disable-kube-proxy \
  --disable=traefik \
  --disable=servicelb \
  --disable=local-storage \
  --cluster-cidr=10.42.0.0/16 \
  --service-cidr=10.43.0.0/16" sh -
```

**On Cluster 2 (`citadel-dr`)**:
```bash
curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="server \
  --cluster-init \
  --flannel-backend=none \
  --disable-network-policy \
  --disable-kube-proxy \
  --disable=traefik \
  --disable=servicelb \
  --disable=local-storage \
  --cluster-cidr=10.44.0.0/16 \
  --service-cidr=10.45.0.0/16" sh -
```

### Step 2: Install Cilium with Unique Cluster IDs

Save both kubeconfigs locally with distinct context names (`citadel-primary` and `citadel-dr`) in `~/.kube/config`.

**Install Cilium on Cluster 1**:
```bash
helm install cilium cilium/cilium \
  --kube-context citadel-primary \
  --namespace kube-system \
  --set cluster.name=citadel-primary \
  --set cluster.id=1 \
  --set kubeProxyReplacement=true \
  --set k8sServiceHost="<CLUSTER1_NODE_IP>" \
  --set k8sServicePort=6443 \
  --set l2announcements.enabled=true \
  --set externalIPs.enabled=true \
  --set ipam.operator.clusterPoolIPv4PodCIDRList="10.42.0.0/16"
```

**Install Cilium on Cluster 2** (sharing Cluster 1's Cilium CA so mTLS between `clustermesh-apiserver` instances works seamlessly):
```bash
# Export Cilium CA secret from Cluster 1 and import into Cluster 2
kubectl --context citadel-primary get secret -n kube-system cilium-ca -o yaml \
  | kubectl --context citadel-dr apply -f -

helm install cilium cilium/cilium \
  --kube-context citadel-dr \
  --namespace kube-system \
  --set cluster.name=citadel-dr \
  --set cluster.id=2 \
  --set kubeProxyReplacement=true \
  --set k8sServiceHost="<CLUSTER2_NODE_IP>" \
  --set k8sServicePort=6443 \
  --set l2announcements.enabled=true \
  --set externalIPs.enabled=true \
  --set ipam.operator.clusterPoolIPv4PodCIDRList="10.44.0.0/16"
```

*(Optional but recommended over untrusted WAN links)*: Add `--set encryption.enabled=true --set encryption.type=wireguard` to both Helm installs.

### Step 3: Enable & Connect ClusterMesh

Enable ClusterMesh on both clusters (using `LoadBalancer` if your Cilium L2 pool is configured, or `NodePort` if connecting across routed subnets):

```bash
cilium clustermesh enable --context citadel-primary --service-type LoadBalancer
cilium clustermesh enable --context citadel-dr --service-type LoadBalancer

cilium clustermesh status --context citadel-primary --wait
cilium clustermesh status --context citadel-dr --wait
```

Connect the two clusters:

```bash
cilium clustermesh connect \
  --context citadel-primary \
  --destination-context citadel-dr
```

Verify cross-cluster connectivity:

```bash
cilium clustermesh status --context citadel-primary --wait
```

Both clusters should report `ClusterMesh: OK` and show the peer cluster connected.

### Step 4: Exposing Services Cross-Cluster (Global Services)

To make a Kubernetes `Service` reachable from both clusters (or provide active-passive / active-active failover), add the Cilium global service annotation to the `Service` in both clusters:

```yaml
metadata:
  annotations:
    service.cilium.io/global: "true"
    # Optional: prefer local cluster endpoints unless none are healthy
    service.cilium.io/affinity: "local"
```

> [!NOTE]
> Cilium ClusterMesh provides **network-level** cross-cluster routing and service discovery. Stateful data components (PostgreSQL, Kafka, Doris) still require application-level replication or off-cluster backups (such as S3 WAL archiving for CNPG PostgreSQL) for zero-data-loss DR.

---

## Part 2: K3s `etcd` Backup & Restore

Because K3s was installed with `--cluster-init`, cluster state is stored in embedded `etcd`. Always store snapshots **off-cluster** (e.g., S3-compatible object storage) in addition to local disk.

### 1. Configure Automated `etcd` Snapshots (Local + S3)

Create or update `/etc/rancher/k3s/config.yaml` on your K3s server node(s):

```yaml
# Snapshot every 6 hours, keep last 10 snapshots
etcd-snapshot-schedule-cron: "0 */6 * * *"
etcd-snapshot-retention: 10
etcd-snapshot-dir: "/var/lib/rancher/k3s/server/db/snapshots"

# Off-cluster S3 backup (recommended for DR)
etcd-s3: true
etcd-s3-endpoint: "s3.example.com"
etcd-s3-bucket: "citadel-k3s-etcd-backups"
etcd-s3-folder: "citadel-primary"
etcd-s3-access-key: "<YOUR_S3_ACCESS_KEY>"
etcd-s3-secret-key: "<YOUR_S3_SECRET_KEY>"
# Set to true only if using self-signed TLS or HTTP MinIO in a private lab
# etcd-s3-insecure: false
```

Apply the configuration by restarting K3s:

```bash
sudo systemctl restart k3s
```

### 2. Trigger & Verify a Manual Snapshot

Before any major upgrade or maintenance:

```bash
sudo k3s etcd-snapshot save --name "pre-upgrade-$(date +%Y%m%d-%H%M)"
sudo k3s etcd-snapshot ls
```

### 3. Restore `etcd` from a Snapshot

> [!WARNING]
> Restoring `etcd` rolls back all Kubernetes API objects (Deployments, PVCs, Secrets, ArgoCD Applications) to the state at snapshot time. Ensure `CITADEL_FERNET_KEY` and your Citadel PostgreSQL backup match if you are performing a full platform restore.

#### Option A: Restore on the Same Node (Corrupted `etcd` State)

1. Stop K3s:
   ```bash
   sudo systemctl stop k3s
   ```
2. Reset the cluster from the chosen snapshot:
   ```bash
   sudo k3s server \
     --cluster-reset \
     --cluster-reset-restore-path=/var/lib/rancher/k3s/server/db/snapshots/<SNAPSHOT_FILENAME>
   ```
   *(If restoring from S3, add `--etcd-s3` flags or download the snapshot file first.)*
3. Once `k3s server --cluster-reset` completes and exits cleanly, start K3s normally:
   ```bash
   sudo systemctl start k3s
   kubectl get nodes,pods -A
   ```

#### Option B: Restore onto a New / Replacement Node

1. Provision the replacement node with the same OS tuning (`ulimits`/`sysctl`) and LVM VolumeGroup (`vg_citadel`) if migrating disks.
2. Install K3s with the **exact same flags** used originally (`--cluster-init`, `--flannel-backend=none`, `--cluster-cidr`, `--service-cidr`, etc.).
3. Stop K3s on the new node:
   ```bash
   sudo systemctl stop k3s
   ```
4. Copy the snapshot file (and `/var/lib/rancher/k3s/server/token` from the original cluster backup, if available) to `/var/lib/rancher/k3s/server/db/snapshots/`.
5. Run the cluster reset & restore:
   ```bash
   sudo k3s server \
     --cluster-reset \
     --cluster-reset-restore-path=/var/lib/rancher/k3s/server/db/snapshots/<SNAPSHOT_FILENAME>
   ```
6. Start K3s and verify all system pods (Cilium, OpenEBS `lvm-localpv`, ArgoCD) recover:
   ```bash
   sudo systemctl start k3s
   cilium status --wait
   kubectl get pods -A
   ```
