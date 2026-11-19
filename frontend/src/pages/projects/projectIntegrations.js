/*
SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
SPDX-License-Identifier: AGPLv3+
*/

export const PROJECT_INTEGRATIONS_CONFIG = [
    { key: 'namespace', name: 'Namespace', resource: 'Namespace' },
    { key: 'argocd_project', name: 'ArgoCD Project', resource: 'AppProject' },
    { key: 'self_signed_issuer', name: 'Self-Signed Issuer', resource: 'Issuer' },
    { key: 'trusted_certs', name: 'Trusted Certs', resource: 'Secret' },
    { key: 'envoy_gateway', name: 'Envoy Gateway', resource: 'Gateway', requiresIngressDomain: true },
    { key: 'wildcard_certificate', name: 'Wildcard Certificate', resource: 'Certificate', requiresIngressDomain: true },
];

/**
 * Determine whether a project on an online cluster requires integration syncing.
 *
 * @param {Object} project - Project record.
 * @param {Object|null} projectState - Project state from the backend _state endpoint.
 * @param {Object} [options]
 * @param {Object|null} [options.certData=null] - Optional Cert Manager status data.
 * @returns {boolean} True when project integrations need to be installed or updated.
 */
export const projectNeedsIntegrationSync = (
    project,
    projectState,
    { certData = null } = {}
) => {
    if (!project?.k8s_cluster_id || !project?.ingress_domain) return false;
    if (!projectState || projectState.cluster?.status !== 'online') return false;

    const integrationsStatus = projectState.integrations_status;
    if (integrationsStatus && Object.keys(integrationsStatus).length > 0) {
        return PROJECT_INTEGRATIONS_CONFIG.some((item) => {
            if (item.requiresIngressDomain && !project.ingress_domain) {
                return false;
            }
            const status = integrationsStatus[item.key]?.status;
            if (status === 'online' || status === 'pending') {
                return false;
            }
            return !status || status === 'offline' || status === 'error';
        });
    }

    const hasGateway = Boolean(projectState.ingress_ports && projectState.ingress_ports.length > 0);
    const hasMissingOrUnhealthyIssuer = Boolean(
        certData && (
            (certData.issuers || []).length === 0 ||
            (certData.issuers || []).some((issuer) => issuer.status !== 'Ready')
        )
    );

    return !hasGateway || hasMissingOrUnhealthyIssuer;
};
