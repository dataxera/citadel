/*
SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
SPDX-License-Identifier: AGPLv3+
*/

import React, { useState, useEffect, useCallback } from 'react';
import { Database } from 'lucide-react';
import { useNotification } from '../../providers/NotificationProvider';
import PlatformServiceView from '../../components/PlatformServiceView';
import { InternalNetworkAccessBlock, ExternalNetworkAccessBlock, CredentialBlock } from '../../components/ServiceBlocks';
import { useVisibilityPolling } from '../../hooks/useStatePolling';

const ServiceView = ({
    darkMode,
    selectedPlatformId,
    selectedPlatform,
    onBack,
    initialTab = 'connect',
    doris
}) => {
    const { getPlatformState, refreshPlatformState, updatePlatformState, fetchPlatforms, fetchActions, executeAction, deletePlatform } = doris;
    const [platformState, setPlatformState] = useState(null);
    const [isRefreshing, setIsRefreshing] = useState(false);

    const { showSuccess, showError } = useNotification();

    const pollPlatformState = useCallback(() => {
        if (!selectedPlatformId) return;
        getPlatformState(selectedPlatformId).then(setPlatformState).catch(console.error);
    }, [selectedPlatformId, getPlatformState]);

    useEffect(() => {
        if (!selectedPlatformId) {
            setPlatformState(null);
        }
    }, [selectedPlatformId]);

    useVisibilityPolling(pollPlatformState, Boolean(selectedPlatformId));

    const handleRefresh = async () => {
        if (!selectedPlatformId) return;
        setIsRefreshing(true);
        try {
            const updated = await refreshPlatformState(selectedPlatformId);
            setPlatformState(updated);
            showSuccess("Status refreshed");
        } finally {
            setIsRefreshing(false);
        }
    };

    const toggleActive = async () => {
        if (!selectedPlatformId || !platformState) return;
        setPlatformState({ ...platformState, active: true, status: 'pending', message: 'Triggering deployment...' });
        try {
            const response = await updatePlatformState(selectedPlatformId, { active: true });
            if (response) setPlatformState(response);
            await handleRefresh();
        } catch (err) {
            showError(`Failed to trigger deployment: ${err.message}`);
            const original = await getPlatformState(selectedPlatformId);
            setPlatformState(original);
        }
    };

    const handleDecommission = async (name, options = {}) => {
        if (!selectedPlatformId) return;
        const force = Boolean(options?.force);
        setPlatformState({
            ...platformState,
            active: false,
            status: 'offline',
            message: force ? 'Force decommissioning...' : 'Decommissioning...'
        });
        try {
            const response = await updatePlatformState(
                selectedPlatformId,
                { active: false, force },
                { 'X-RESOURCE-NAME': name }
            );
            if (response) setPlatformState(response);
            showSuccess(force ? 'Doris cluster force-decommissioned successfully' : 'Doris cluster decommissioned successfully');
            await handleRefresh();
        } catch (err) {
            let errorMsg = err.message;
            if (err.response?.data?.detail) {
                const detail = err.response.data.detail;
                if (Array.isArray(detail) && detail.length > 0) {
                    errorMsg = detail[0].msg || errorMsg;
                } else if (typeof detail === 'string') {
                    errorMsg = detail;
                }
            } else if (err.response?.data?.message) {
                errorMsg = err.response.data.message;
            }
            if (err.response?.status !== 422) {
                showError(`Failed to decommission: ${errorMsg}`);
            }
            const original = await getPlatformState(selectedPlatformId);
            setPlatformState(original);
        }
    };

    const handleDelete = async (name) => {
        if (!selectedPlatformId) return;
        try {
            await deletePlatform(selectedPlatformId, name);
            showSuccess('Doris cluster deleted successfully');
            if (onBack) onBack();
        } catch (err) {
            let errorMsg = err.message;
            if (err.response?.data?.detail) {
                const detail = err.response.data.detail;
                if (Array.isArray(detail) && detail.length > 0) {
                    errorMsg = detail[0].msg || errorMsg;
                } else if (typeof detail === 'string') {
                    errorMsg = detail;
                }
            } else if (err.response?.data?.message) {
                errorMsg = err.response.data.message;
            }
            if (err.response?.status !== 422) {
                showError(`Failed to delete cluster: ${errorMsg}`);
            }
        }
    };

    const renderConnectTab = () => {
        const endpoints = [];
        const ns = platformState?.extra_data?.namespace || 'default';
        if (selectedPlatform) {
            endpoints.push({
                title: 'MySQL Protocol (Direct)',
                subtitle: 'Internal Only',
                code: `${selectedPlatform.name}-fe-service.${ns}.svc.cluster.local:9030`,
                description: 'Internal MySQL query port (9030) for connecting applications and analytics engines.'
            });
            endpoints.push({
                title: 'Frontend Web UI / REST',
                subtitle: 'Internal Only',
                code: `http://${selectedPlatform.name}-fe-service.${ns}.svc.cluster.local:8030`,
                description: 'Internal HTTP endpoint for Web Console and Stream Load operations.'
            });
        }

        const ports = [];
        let isIngressUsed = false;
        const ingressDomain = platformState?.extra_data?.ingress_domain;

        if (ingressDomain) {
            ports.push({
                label: 'Web UI (Ingress)',
                port: 443,
                scheme: 'https',
                url: `https://${selectedPlatform.name}.${ingressDomain}`
            });
            isIngressUsed = true;
        }

        const lbIps = platformState?.extra_data?.load_balancer_ips || [];
        ports.push({
            label: 'MySQL Query (LoadBalancer)',
            port: 3306,
            load_balancer_ips: lbIps
        });

        const cliInfo = lbIps.length > 0 ? {
            command: () => `mysql -h ${lbIps[0]} -P 3306 -u root -p`,
            languageButtons: []
        } : null;

        const adminPassword = platformState?.db_pass || platformState?.admin_password || selectedPlatform.admin_password;

        return (
            <div className="space-y-6">
                {endpoints.length > 0 && (
                    <InternalNetworkAccessBlock
                        darkMode={darkMode}
                        icon={Database}
                        endpoints={endpoints}
                    />
                )}

                {ports.length > 0 && (
                    <ExternalNetworkAccessBlock
                        darkMode={darkMode}
                        ports={ports}
                        clusterNodes={platformState?.cluster_nodes || []}
                        cliInfo={cliInfo}
                        isIngressUsed={isIngressUsed}
                        icon={Database}
                    />
                )}

                {adminPassword && (
                    <CredentialBlock
                        darkMode={darkMode}
                        credentials={[
                            { label: 'Admin Username', value: platformState?.db_user || platformState?.admin_user || 'root' },
                            { label: 'Admin Password', value: adminPassword, isMasked: true },
                        ]}
                    />
                )}
            </div>
        );
    };

    return (
        <PlatformServiceView
            darkMode={darkMode}
            selectedPlatformId={selectedPlatformId}
            selectedPlatform={selectedPlatform}
            platformState={platformState}
            onBack={onBack}
            onRefresh={handleRefresh}
            fetchActions={fetchActions}
            executeAction={executeAction}
            isRefreshing={isRefreshing}
            onToggleActive={toggleActive}
            onDecommission={handleDecommission}
            onDelete={handleDelete}
            deleteModalTitle="Delete Doris Cluster"
            deleteWarningText="Permanently delete this Doris cluster, all FE/BE nodes, and associated storage. The cluster must be decommissioned before it can be deleted. This action cannot be undone."
            icon={Database}
            iconClassName="text-cyan-400"
            entityPath="/platform/doris"
            fetchPlatforms={fetchPlatforms}
            renderConnectTab={renderConnectTab}
            initialTab={initialTab}
            decommissionWarningText="Permanently delete all associated Kubernetes resources and data for this Doris cluster. This action cannot be undone."
            notDeployedTitle="Apache Doris Not Deployed"
            notDeployedDescription="Deploy the Apache Doris cluster to start querying and access the web console."
            deployButtonText="DEPLOY DORIS"
        />
    );
};

export default ServiceView;
