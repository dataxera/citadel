# K3s Quickstart Setup (Cilium + OpenEBS LVM)

This guide sets up a **K3s** Kubernetes cluster tailored for Citadel's data and AI workloads (PostgreSQL, Doris, Kafka, Trino, NiFi, Airflow, Elasticsearch/Solr). It replaces Flannel/ServiceLB with **Cilium CNI** and replaces `local-path-provisioner` with **OpenEBS `lvm-localpv`** for hard volume quotas and capacity visibility.

---

## 1. Minimum & Recommended Requirements

### Minimum (Lab / Evaluation)
- **CPU**: 8 vCPU
- **RAM**: 32 GB
- **OS Disk**: 50 GB SSD/NVMe
- **Data Disk**: 100 GB+ raw unformatted block device (e.g., `/dev/sdb` or `/dev/nvme1n1`) for LVM
- **OS**: Ubuntu 22.04/24.04 LTS, Rocky Linux 9, or Debian 12 (Linux kernel **5.10+** for Cilium eBPF)

### Recommended (Single-Node Enterprise / Full Data Stack)
- **CPU**: 32 vCPU
- **RAM**: 128 GB
- **OS Disk**: 100 GB+ NVMe (`/`, `/var/lib/rancher/k3s`, `/var/lib/kubelet`)
- **Data Disk**: Dedicated NVMe/RAID volume (e.g., 1 TB+ on `/dev/nvme1n1`) dedicated to the LVM VolumeGroup so workload data never fills the root filesystem.

### Required Tools on the Node (or Admin Workstation)
- `curl`, `lvm2`, `helm` (v3.14+), `kubectl`, `cilium` CLI

```bash
# Ubuntu/Debian
sudo apt-get update && sudo apt-get install -y curl lvm2 jq open-iscsi

# RHEL/Rocky
sudo dnf install -y curl lvm2 jq iscsi-initiator-utils
```

---

## 2. OS Tuning & `ulimits` (32 vCPU / 128 GB RAM Node)

Data platform components (Elasticsearch/Solr `mmap`, Kafka open file descriptors, Apache Doris BE, NiFi, and PostgreSQL) quickly exhaust default Linux limits on a 32 vCPU / 128 GB RAM node. Apply these settings **before** installing K3s.

### Kernel `sysctl` Parameters

Create `/etc/sysctl.d/99-citadel-k8s.conf`:

```bash
sudo tee /etc/sysctl.d/99-citadel-k8s.conf <<'EOF'
# Required for Elasticsearch / OpenSearch / Doris BE mmap allocations
vm.max_map_count = 2621440

# Reduce swap aggressiveness (or disable swap completely)
vm.swappiness = 1

# File descriptors & inotify watches for many containers/pods (32 vCPU / 128 GB)
fs.file-max = 2097152
fs.nr_open = 2097152
fs.inotify.max_user_watches = 1048576
fs.inotify.max_user_instances = 8192
fs.aio-max-nr = 1048576

# Network & connection tracking tuning for high-throughput Kafka/Trino/Cilium
net.core.somaxconn = 32768
net.core.netdev_max_backlog = 16384
net.ipv4.ip_local_port_range = 1024 65535
net.ipv4.tcp_max_syn_backlog = 8192
net.ipv4.ip_forward = 1
net.ipv6.conf.all.forwarding = 1
EOF

sudo sysctl --system
```

### PAM / Shell `ulimits`

Create `/etc/security/limits.d/99-citadel.conf`:

```bash
sudo tee /etc/security/limits.d/99-citadel.conf <<'EOF'
* soft nofile 1048576
* hard nofile 1048576
* soft nproc  65536
* hard nproc  65536
* soft memlock unlimited
* hard memlock unlimited
root soft nofile 1048576
root hard nofile 1048576
root soft nproc  65536
root hard nproc  65536
EOF
```

### Systemd Limits for `k3s`

Systemd services do **not** inherit `/etc/security/limits.d/`. Configure a systemd drop-in for `k3s` so containerd and all pods inherit elevated limits:

```bash
sudo mkdir -p /etc/systemd/system/k3s.service.d
sudo tee /etc/systemd/system/k3s.service.d/limits.conf <<'EOF'
[Service]
LimitNOFILE=1048576
LimitNPROC=65536
LimitMEMLOCK=infinity
TasksMax=infinity
EOF

sudo systemctl daemon-reload
```

### Disable Swap

```bash
sudo swapoff -a
# Comment out swap entries in /etc/fstab so swap stays off across reboots
sudo sed -i.bak '/\sswap\s/s/^/#/' /etc/fstab
```

---

## 3. Install K3s

Install K3s with:
- `--flannel-backend=none` and `--disable-network-policy` (so Cilium provides CNI and NetworkPolicy)
- `--disable=kube-proxy` (optional; recommended if using Cilium eBPF kube-proxy replacement)
- `--disable=traefik` and `--disable=servicelb` (Citadel uses Envoy Gateway and Cilium L2 LoadBalancer)
- `--disable=local-storage` (since we will use OpenEBS `lvm-localpv` instead of `local-path-provisioner`)
- `--cluster-init` (enables embedded `etcd` instead of SQLite, required for snapshots and DR)

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
  --service-cidr=10.43.0.0/16 \
  --write-kubeconfig-mode=644" sh -
```

Configure `kubectl` for your user:

```bash
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown "$(id -u):$(id -g)" ~/.kube/config
export KUBECONFIG=~/.kube/config
```

> [!NOTE]
> The node will show `NotReady` until **Cilium CNI** is installed in the next step.

---

## 4. Install Cilium CNI

### Install Cilium CLI & Helm Repo

```bash
CILIUM_CLI_VERSION=$(curl -s https://raw.githubusercontent.com/cilium/cilium-cli/main/stable.txt)
curl -L --fail --remote-name-all "https://github.com/cilium/cilium-cli/releases/download/${CILIUM_CLI_VERSION}/cilium-linux-amd64.tar.gz"
sudo tar xzvfC cilium-linux-amd64.tar.gz /usr/local/bin
rm -f cilium-linux-amd64.tar.gz

helm repo add cilium https://helm.cilium.io/
helm repo update
```

### Deploy Cilium with eBPF Kube-Proxy Replacement & L2 LoadBalancer

Replace `<NODE_IP>` with your node's primary IP (e.g., `10.210.14.10`):

```bash
NODE_IP="<NODE_IP>"

helm install cilium cilium/cilium \
  --namespace kube-system \
  --set kubeProxyReplacement=true \
  --set k8sServiceHost="${NODE_IP}" \
  --set k8sServicePort=6443 \
  --set l2announcements.enabled=true \
  --set externalIPs.enabled=true \
  --set ipam.operator.clusterPoolIPv4PodCIDRList="10.42.0.0/16" \
  --set hubble.relay.enabled=true \
  --set hubble.ui.enabled=true
```

Wait for Cilium and the node to become ready:

```bash
cilium status --wait
kubectl get nodes
```

### Configure Cilium L2 LoadBalancer IP Pool

!!! note
    If you prefer **MetalLB** instead of Cilium L2 announcements (for example, on clusters using Flannel or BGP), skip `l2announcements.enabled=true` and follow the **[MetalLB LoadBalancer Setup](metallb-setup.md)** guide.

Create an IP pool using an unused IP range on your node's L2 subnet (adjust `10.210.14.230-10.210.14.240` and `eth0` to match your network):

```bash
kubectl apply -f - <<EOF
apiVersion: cilium.io/v2alpha1
kind: CiliumLoadBalancerIPPool
metadata:
  name: citadel-pool
spec:
  blocks:
    - start: 10.210.14.230
      stop: 10.210.14.240
---
apiVersion: cilium.io/v2alpha1
kind: CiliumL2AnnouncementPolicy
metadata:
  name: citadel-l2-policy
spec:
  externalIPs: true
  loadBalancerIPs: true
  interfaces:
    - ^eth0$
EOF
```

---

## 5. Install OpenEBS `lvm-localpv` (Standalone)

Using `openebs/lvm-localpv` standalone avoids installing the full OpenEBS umbrella while giving you **hard LVM volume size enforcement** and **capacity-aware scheduling**.

### 5.1 Prepare the LVM VolumeGroup on Your Data Disk

Identify your dedicated data disk (e.g., `/dev/nvme1n1` or `/dev/sdb`) and create a VolumeGroup named `vg_citadel`:

```bash
# WARNING: Ensure /dev/nvme1n1 has no existing data you need!
sudo pvcreate /dev/nvme1n1
sudo vgcreate vg_citadel /dev/nvme1n1

# Verify the VolumeGroup
sudo vgs
```

### 5.2 Install `openebs/lvm-localpv` via Helm

```bash
helm repo add openebs-lvm https://openebs.github.io/lvm-localpv
helm repo update

helm install openebs-lvm openebs-lvm/lvm-localpv \
  --namespace openebs \
  --create-namespace \
  --set lvmNode.kubeletDir="/var/lib/kubelet"
```

Verify the CSI pods are running:

```bash
kubectl get pods -n openebs
```

### 5.3 Create the Default `StorageClass`

Create a `StorageClass` pointing to `vg_citadel` with `WaitForFirstConsumer` (ensures pods are scheduled to a node with enough free LVM space) and `allowVolumeExpansion: true`:

```bash
kubectl apply -f - <<EOF
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: openebs-lvm
  annotations:
    storageclass.kubernetes.io/is-default-class: "true"
provisioner: local.csi.openebs.io
volumeBindingMode: WaitForFirstConsumer
reclaimPolicy: Delete
allowVolumeExpansion: true
parameters:
  storage: "lvm"
  volgroup: "vg_citadel"
  fsType: "ext4"
EOF
```

Verify `CSIStorageCapacity` and default StorageClass:

```bash
kubectl get sc
kubectl get csistoragecapacities -A
```

---

## 6. DNS Configuration (Pointing to Ingress / Gateway)

Citadel exposes deployed services (Airflow, Superset, Trino, Ranger, etc.) via Kubernetes Ingress / Envoy Gateway using subdomains under your project's `ingress_domain` (for example, `*.apps.citadel.example.com`).

### 6.1 Find Your Ingress / Gateway External IP

After installing your Ingress / Envoy Gateway controller, check its `LoadBalancer` IP assigned by Cilium:

```bash
kubectl get svc -A --field-selector spec.type=LoadBalancer
```

Assume the assigned `EXTERNAL-IP` is `10.210.14.230`.

### 6.2 Production DNS (Corporate DNS / Route53 / CoreDNS)

Create a wildcard `A` record in your DNS provider:

```text
*.apps.citadel.example.com.   IN A   10.210.14.230
```

### 6.3 Lab / On-Premise Quick DNS (`dnsmasq`)

If you do not have a corporate DNS server for a lab environment, you can run `dnsmasq` on your jumpbox/router or configure `/etc/NetworkManager/dnsmasq.d/citadel.conf`:

```text
address=/.apps.citadel.local/10.210.14.230
```

Verify resolution from a client machine:

```bash
dig +short test.apps.citadel.example.com
# Expected output: 10.210.14.230
```
