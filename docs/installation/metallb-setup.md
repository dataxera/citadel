# MetalLB LoadBalancer Setup

For self-hosted or bare-metal Kubernetes clusters (such as K3s with `--disable servicelb` and `--disable traefik`) that do not use a cloud provider LoadBalancer or Cilium L2 announcements, **[MetalLB](https://metallb.io/)** provides `LoadBalancer` IP assignment for Envoy Gateway and external service access.

!!! warning
    Do not run MetalLB L2 mode simultaneously with K3s `servicelb` (Klipper) or Cilium `l2announcements` on the same IP range. Choose either Cilium L2 LoadBalancer IPAM or MetalLB.

---

## 1. Prerequisites

- **Kubernetes**: v1.28+ (with K3s `servicelb` disabled).
- **IP Range**: An unused contiguous IP range or CIDR on your L2 subnet (outside your DHCP range) or a BGP-routed range for Layer 3 mode.

---

## 2. Install MetalLB

Apply the official MetalLB manifest and wait for the controller and speaker pods to become ready:

```bash
kubectl apply -f https://raw.githubusercontent.com/metallb/metallb/main/manifests/metallb.yaml

kubectl wait --for=condition=ready pod \
  --selector app=metallb \
  -n metallb-system \
  --timeout=120s
```

Verify all MetalLB pods are running:

```bash
kubectl get pods -n metallb-system
```

---

## 3. Configure IP Address Pool

Create an `IPAddressPool` and an advertisement resource (`L2Advertisement` for Layer 2 mode) so MetalLB can assign external IPs to `LoadBalancer` services:

```bash
kubectl apply -f - <<EOF
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata:
  name: default-pool
  namespace: metallb-system
spec:
  addresses:
    # Replace with an unused IP range or CIDR on your network (outside your DHCP range)
    - 192.168.1.240-192.168.1.250
---
apiVersion: metallb.io/v1beta1
kind: L2Advertisement
metadata:
  name: default-l2
  namespace: metallb-system
spec:
  ipAddressPools:
    - default-pool
EOF
```

- **`addresses`**: Specify one or more IP ranges (e.g., `192.168.1.240-192.168.1.250`) or CIDRs (e.g., `192.168.1.240/28`) reachable on your network and not used by your DHCP server or other hosts.
- **Layer 3 (BGP) mode**: If using BGP instead of Layer 2, configure `BGPPeer` and `BGPAdvertisement` resources referencing `default-pool` in place of `L2Advertisement`.

---

## 4. Verify Configuration

Confirm the `IPAddressPool` and `L2Advertisement` resources are active:

```bash
kubectl get ipaddresspools,l2advertisements -n metallb-system
```

When Envoy Gateway or any `LoadBalancer` service is deployed, check that `EXTERNAL-IP` is populated from `default-pool`:

```bash
kubectl get svc -A --field-selector spec.type=LoadBalancer
```

<!--
SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
SPDX-License-Identifier: AGPLv3+
-->
