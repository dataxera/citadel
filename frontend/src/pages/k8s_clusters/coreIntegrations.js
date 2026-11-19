/*
SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
SPDX-License-Identifier: AGPLv3+
*/

export const CORE_INTEGRATIONS_CONFIG = [
    { key: 'argocd', name: 'ArgoCD', installedField: 'argocd_installed', versionField: 'argocd_version' },
    { key: 'cert_manager', name: 'Cert Manager', installedField: 'cert_manager_installed', versionField: 'cert_manager_version' },
    { key: 'cnpg', name: 'CNPG Operator', installedField: 'cnpg_installed', versionField: 'cnpg_version' },
    { key: 'envoy_gateway', name: 'Envoy Gateway', installedField: 'envoy_gateway_installed', versionField: 'envoy_gateway_version' },
    { key: 'kafka_operator', name: 'Kafka Operator', installedField: 'kafka_operator_installed', versionField: 'kafka_operator_version' },
    { key: 'nifikop', name: 'NiFi Operator', installedField: 'nifikop_installed', versionField: 'nifikop_version' },
    { key: 'doris_operator', name: 'Doris Operator', installedField: 'doris_operator_installed', versionField: 'doris_operator_version' },
    { key: 'kube_prometheus_stack', name: 'Kube Prometheus Stack', installedField: 'kube_prometheus_stack_installed', versionField: 'kube_prometheus_stack_version' },
];

/**
 * Determine whether an online cluster has core integrations that need to be installed or updated.
 *
 * @param {Object} clusterState - Cluster state object from the backend _state endpoint.
 * @returns {boolean} True when at least one core integration is missing or in error state.
 */
export const clusterNeedsIntegrationSync = (clusterState) => {
    if (!clusterState || clusterState.status !== 'online') return false;
    if (clusterState.sync_state?.status === 'in_progress') return false;
    if (
        clusterState.sync_state?.status === 'completed_with_errors' ||
        clusterState.sync_state?.status === 'error'
    ) {
        return true;
    }

    return CORE_INTEGRATIONS_CONFIG.some((item) => {
        const integrationStatus = clusterState.integrations_status?.[item.key]?.status;
        if (integrationStatus === 'pending' || integrationStatus === 'online') {
            return false;
        }
        return (
            !clusterState[item.installedField] ||
            integrationStatus === 'offline' ||
            integrationStatus === 'error'
        );
    });
};
