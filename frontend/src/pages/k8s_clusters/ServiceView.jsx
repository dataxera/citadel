import React, { useState, useEffect, useCallback } from 'react';
import {
    Activity, Monitor, RefreshCw, CheckCircle2, AlertCircle, Loader2, Clock, Copy, Check,
    Network, SlidersHorizontal, Cpu, Layers, Table2, GitBranch, ExternalLink, Eye, EyeOff
} from 'lucide-react';
import { useNotification } from '../../providers/NotificationProvider';
import Modal from '../../components/Modal';
import { cn } from '../../utils/cn';
import { useVisibilityPolling } from '../../hooks/useStatePolling';
import { useResourcePermissions } from '../../hooks/usePermissions';
import NodeConfigModal from './NodeConfigModal';
import RackTopologyModal from './RackTopologyModal';
import TopologyPresetsModal from './TopologyPresetsModal';
import NodeHierarchyView from './NodeHierarchyView';

const CORE_INTEGRATIONS_CONFIG = [
    { key: 'argocd', name: 'ArgoCD', installedField: 'argocd_installed', versionField: 'argocd_version' },
    { key: 'cert_manager', name: 'Cert Manager', installedField: 'cert_manager_installed', versionField: 'cert_manager_version' },
    { key: 'cnpg', name: 'CNPG Operator', installedField: 'cnpg_installed', versionField: 'cnpg_version' },
    { key: 'envoy_gateway', name: 'Envoy Gateway', installedField: 'envoy_gateway_installed', versionField: 'envoy_gateway_version' },
    { key: 'kafka_operator', name: 'Kafka Operator', installedField: 'kafka_operator_installed', versionField: 'kafka_operator_version' },
    { key: 'nifikop', name: 'NiFi Operator', installedField: 'nifikop_installed', versionField: 'nifikop_version' },
    { key: 'doris_operator', name: 'Doris Operator', installedField: 'doris_operator_installed', versionField: 'doris_operator_version' },
    { key: 'kube_prometheus_stack', name: 'Kube Prometheus Stack', installedField: 'kube_prometheus_stack_installed', versionField: 'kube_prometheus_stack_version' },
];

const IntegrationStatusBadge = ({ status }) => {
    const styles = {
        online: 'dxc-badge-success',
        pending: 'dxc-badge-warning',
        offline: 'dxc-badge-neutral',
        error: 'dxc-badge-danger',
    };
    return (
        <span className={cn(styles[status] || 'dxc-badge-neutral')}>
            {(status || 'unknown').toUpperCase()}
        </span>
    );
};

const formatNodeAge = (creationTimestamp) => {
    if (!creationTimestamp) return '—';
    const createdMs = new Date(creationTimestamp).getTime();
    if (Number.isNaN(createdMs)) return '—';
    const diffSec = Math.max(0, Math.floor((Date.now() - createdMs) / 1000));
    if (diffSec < 60) return `${diffSec}s`;
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin}m`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 48) return `${diffHr}h`;
    return `${Math.floor(diffHr / 24)}d`;
};

const NodeResourceCell = ({ requested, total, unit, barClass }) => {
    const hasMetrics = typeof total === 'number' && total > 0;
    if (!hasMetrics) {
        return <span className="text-xs text-slate-400">—</span>;
    }
    const reqVal = typeof requested === 'number' ? requested : 0;
    const pct = Math.min(100, Math.round((reqVal / total) * 100));
    return (
        <div className="min-w-[140px] space-y-1">
            <div className="flex items-center justify-between gap-2 text-xs">
                <span className="font-semibold text-slate-700 dark:text-slate-200 tabular-nums">
                    {reqVal.toFixed(2)} / {total.toFixed(1)} {unit}
                </span>
                <span className="text-[11px] font-bold text-slate-400 tabular-nums">{pct}%</span>
            </div>
            <div className="h-1.5 w-full bg-slate-200 dark:bg-slate-800 rounded-full overflow-hidden">
                <div
                    className={cn('h-full transition-all duration-500', barClass)}
                    style={{ width: `${pct}%` }}
                />
            </div>
        </div>
    );
};

const ServiceView = ({
    selectedClusterId,
    selectedCluster,
    onBack,
    clustersHook
}) => {
    const { getClusterState, refreshClusterState, updateNodeLabels, getClusterTopology, updateClusterTopology } = clustersHook;
    const { canUpdate, canExecute } = useResourcePermissions('/k8s_clusters', {
        resourceId: selectedClusterId,
    });
    const canConfigureNodes = canUpdate || canExecute;
    const [clusterState, setClusterState] = useState(null);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const [installingActions, setInstallingActions] = useState({});
    const [selectedSyncTask, setSelectedSyncTask] = useState(null);
    const [copiedLogs, setCopiedLogs] = useState(false);
    const [showArgoPassword, setShowArgoPassword] = useState(false);
    const [copiedArgoField, setCopiedArgoField] = useState(null);
    const [selectedNodeForConfig, setSelectedNodeForConfig] = useState(null);
    const [isRackTopologyOpen, setIsRackTopologyOpen] = useState(false);
    const [isTopologyPresetsOpen, setIsTopologyPresetsOpen] = useState(false);
    const [topologyData, setTopologyData] = useState(null);
    const [nodeTopologyTab, setNodeTopologyTab] = useState('table');
    const { showSuccess, showError } = useNotification();


    const pollClusterState = useCallback(() => {
        if (!selectedClusterId || !getClusterState) return;
        getClusterState(selectedClusterId).then(setClusterState).catch(console.error);
    }, [selectedClusterId, getClusterState]);

    useEffect(() => {
        if (!selectedClusterId) {
            Promise.resolve().then(() => {
                setClusterState(null);
            });
        }
    }, [selectedClusterId]);

    useVisibilityPolling(pollClusterState, Boolean(selectedClusterId && getClusterState));

    const handleRefresh = async () => {
        if (!refreshClusterState) return;
        setIsRefreshing(true);
        try {
            const newState = await refreshClusterState(selectedClusterId);
            if (newState && typeof newState === 'object' && 'status' in newState && !('k8s_version' in newState) && Object.keys(newState).length === 1) {
                // Defensive guard: never overwrite state with bare action ack
                const fetched = getClusterState ? await getClusterState(selectedClusterId) : null;
                if (fetched) setClusterState(fetched);
            } else if (newState) {
                setClusterState(newState);
            }
            showSuccess("Cluster state refreshed");
        } catch (e) {
            console.error(e);
            showError("Failed to refresh cluster state");
        } finally {
            setIsRefreshing(false);
        }
    };

    const handleInstallAction = async (actionId) => {
        setInstallingActions(prev => ({ ...prev, [actionId]: true }));
        try {
            await clustersHook.executeAction(selectedClusterId, actionId);
            showSuccess("Core integrations synchronization triggered");
            pollClusterState();
        } catch (e) {
            console.error(e);
            showError("Failed to trigger core integrations sync");
        } finally {
            setInstallingActions(prev => ({ ...prev, [actionId]: false }));
        }
    };

    const loadTopology = useCallback(async () => {
        if (!selectedClusterId || !getClusterTopology) return;
        try {
            const data = await getClusterTopology(selectedClusterId);
            setTopologyData(data);
        } catch (e) {
            console.error("Failed to load cluster topology", e);
        }
    }, [selectedClusterId, getClusterTopology]);

    useEffect(() => {
        loadTopology();
    }, [loadTopology]);

    const handleOpenRackTopology = async () => {
        await loadTopology();
        setIsRackTopologyOpen(true);
    };

    const handleOpenTopologyPresets = async () => {
        await loadTopology();
        setIsTopologyPresetsOpen(true);
    };

    const handleSaveNodeConfig = async (nodeName, payload) => {
        try {
            await updateNodeLabels(selectedClusterId, nodeName, payload);
            showSuccess(`Updated configuration for node ${nodeName}`);
            pollClusterState();
            loadTopology();
        } catch (e) {
            const detail = e?.response?.data?.detail || "Failed to update node configuration";
            showError(detail);
            throw e;
        }
    };

    const handleSaveRackTopology = async (payload) => {
        try {
            const updated = await updateClusterTopology(selectedClusterId, payload);
            setTopologyData(updated);
            showSuccess("Rack hierarchy topology updated");
            pollClusterState();
        } catch (e) {
            const detail = e?.response?.data?.detail || "Failed to update rack topology";
            showError(detail);
            throw e;
        }
    };

    const handleCopyArgoValue = (field, value) => {
        if (!value) return;
        navigator.clipboard?.writeText(value);
        setCopiedArgoField(field);
        setTimeout(() => setCopiedArgoField(null), 2000);
    };

    if (!clusterState) {
        return (
            <div className="space-y-8 animate-in fade-in duration-500">
                <div className="dxc-page-header">
                    <div className="flex gap-4 items-center">
                        <div className="dxc-icon-box w-16 h-16 text-slate-400">
                            <Monitor size={32} />
                        </div>
                        <div>
                            <h2 className="text-4xl font-bold tracking-tight text-slate-900 dark:text-white">Loading Cluster State...</h2>
                        </div>
                    </div>
                    <div className="flex gap-3">
                        <button
                            onClick={onBack}
                            className="dxc-btn-secondary px-6 py-2.5"
                        >
                            BACK TO LIST
                        </button>
                    </div>
                </div>
            </div>
        );
    }

    const syncState = clusterState.sync_state;
    const isSyncInProgress = Boolean(
        installingActions['sync_core_integrations'] ||
        syncState?.status === 'in_progress'
    );

    return (
        <div className="space-y-8 animate-in fade-in duration-500">
            <div className="dxc-page-header">
                <div className="flex gap-4 items-center">
                    <div className="dxc-icon-box w-16 h-16 text-indigo-400">
                        <Monitor size={32} />
                    </div>
                    <div>
                        <div className="flex items-center gap-3">
                            <h2 className="text-4xl font-bold tracking-tight text-slate-900 dark:text-white">{selectedCluster.title} Health</h2>
                        </div>
                        <div className="flex items-center gap-4 mt-2">
                            <span className="flex items-center gap-1.5 text-sm text-slate-400">
                                Cluster ID: <span className="text-slate-500 font-mono font-bold uppercase tracking-tight">{selectedCluster.id}</span>
                            </span>
                        </div>
                    </div>
                </div>
                <div className="flex gap-3">
                    <button
                        onClick={handleRefresh}
                        disabled={isRefreshing}
                        className="dxc-btn-secondary px-6 py-2.5 flex items-center gap-2"
                    >
                        <RefreshCw size={16} className={isRefreshing ? "animate-spin" : ""} />
                        {isRefreshing ? 'REFRESHING...' : 'REFRESH'}
                    </button>
                    <button
                        id="sync-core-integrations-btn"
                        onClick={() => handleInstallAction('sync_core_integrations')}
                        disabled={isSyncInProgress}
                        className="dxc-btn-secondary px-6 py-2.5 flex items-center gap-2 disabled:opacity-60"
                    >
                        <RefreshCw size={16} className={isSyncInProgress ? "animate-spin" : ""} />
                        {isSyncInProgress ? 'SYNCING...' : 'SYNC INTEGRATIONS'}
                    </button>
                    <button
                        onClick={onBack}
                        className="dxc-btn-secondary px-6 py-2.5"
                    >
                        BACK TO LIST
                    </button>
                </div>
            </div>

            <div className="dxc-card p-8 space-y-8 animate-in slide-in-from-bottom duration-700">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <div className="dxc-icon-box text-blue-500">
                            <Activity size={24} />
                        </div>
                        <div>
                            <h3 className="text-2xl font-bold text-slate-900 dark:text-white">Cluster Health</h3>
                            <p className="text-sm text-slate-500 font-medium uppercase tracking-tight">Real-time infrastructure intelligence {clusterState.k8s_version && `• K8S ${clusterState.k8s_version}`}</p>
                        </div>
                    </div>
                    <div className="flex items-center gap-2 px-4 py-2 bg-slate-100 dark:bg-slate-800 rounded-full">
                        <div className={`w-3 h-3 rounded-full ${clusterState.status === 'online' ? 'bg-green-500' : 'bg-red-500'}`} />
                        <span className="text-sm font-bold uppercase tracking-tight text-slate-600 dark:text-slate-400">{clusterState.status}</span>
                    </div>
                </div>

                {clusterState.message && clusterState.status === 'error' && (
                    <div className="p-4 bg-red-500/10 border border-red-500/20 text-red-500 rounded-xl text-sm font-mono whitespace-pre-wrap">
                        {clusterState.message}
                    </div>
                )}

                {/* Resource Utilization */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 bg-slate-50/50 dark:bg-slate-900/50 p-6 rounded-2xl border border-slate-200/50 dark:border-slate-800/50">
                    <div className="space-y-4">
                        <div className="flex justify-between items-end">
                            <p className="text-xs font-bold uppercase tracking-widest text-slate-400">CPU Requests / Capacity</p>
                            <p className="text-sm font-bold text-slate-900 dark:text-white tabular-nums">
                                {(clusterState.cpu_allocated || 0).toFixed(2)} / {(clusterState.cpu_total || 0).toFixed(1)} Cores
                            </p>
                        </div>
                        <div className="h-2 w-full bg-slate-200 dark:bg-slate-800 rounded-full overflow-hidden">
                            <div
                                className="h-full bg-blue-500 transition-all duration-1000"
                                style={{
                                    width: `${clusterState.cpu_total > 0 ? Math.min(100, Math.round(((clusterState.cpu_allocated || 0) / clusterState.cpu_total) * 100)) : 0}%`
                                }}
                            />
                        </div>
                    </div>
                    <div className="space-y-4">
                        <div className="flex justify-between items-end">
                            <p className="text-xs font-bold uppercase tracking-widest text-slate-400">RAM Requests / Capacity</p>
                            <p className="text-sm font-bold text-slate-900 dark:text-white tabular-nums">
                                {(clusterState.ram_allocated || 0).toFixed(2)} / {(clusterState.ram_total || 0).toFixed(1)} GiB
                            </p>
                        </div>
                        <div className="h-2 w-full bg-slate-200 dark:bg-slate-800 rounded-full overflow-hidden">
                            <div
                                className="h-full bg-purple-500 transition-all duration-1000"
                                style={{
                                    width: `${clusterState.ram_total > 0 ? Math.min(100, Math.round(((clusterState.ram_allocated || 0) / clusterState.ram_total) * 100)) : 0}%`
                                }}
                            />
                        </div>
                    </div>
                </div>

                {/* Node Topology (Full-Width Widget) */}
                {(() => {
                    const nodeRows = Array.isArray(clusterState.nodes_details) && clusterState.nodes_details.length > 0
                        ? clusterState.nodes_details
                        : Object.entries(clusterState.nodes_status || {}).map(([hostname, status]) => ({
                            hostname,
                            status,
                        }));

                    return (
                        <div
                            id="node-topology-widget"
                            className="space-y-4 bg-slate-50/50 dark:bg-slate-900/50 p-6 rounded-2xl border border-slate-200/50 dark:border-slate-800/50"
                        >
                            <div className="flex flex-wrap items-center justify-between gap-3">
                                <div className="flex items-center gap-4">
                                    <p className="text-xs font-bold uppercase tracking-widest text-slate-400">
                                        Node Topology ({clusterState.node_count || nodeRows.length || 0})
                                    </p>
                                    <div className="inline-flex rounded-lg p-0.5 bg-slate-200/70 dark:bg-slate-800/80 border border-slate-300/60 dark:border-slate-700/60">
                                        <button
                                            id="node-topology-tab-table"
                                            type="button"
                                            onClick={() => setNodeTopologyTab('table')}
                                            className={cn(
                                                "px-2.5 py-1 rounded-md text-[11px] font-bold uppercase tracking-wider flex items-center gap-1.5 transition-all",
                                                nodeTopologyTab === 'table'
                                                    ? "bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-sm"
                                                    : "text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
                                            )}
                                        >
                                            <Table2 size={12} />
                                            Table
                                        </button>
                                        <button
                                            id="node-topology-tab-hierarchy"
                                            type="button"
                                            onClick={() => setNodeTopologyTab('hierarchy')}
                                            className={cn(
                                                "px-2.5 py-1 rounded-md text-[11px] font-bold uppercase tracking-wider flex items-center gap-1.5 transition-all",
                                                nodeTopologyTab === 'hierarchy'
                                                    ? "bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-sm"
                                                    : "text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
                                            )}
                                        >
                                            <GitBranch size={12} />
                                            Hierarchy
                                        </button>
                                    </div>
                                </div>
                                {canConfigureNodes && (
                                    <div className="flex items-center gap-2">
                                        <button
                                            id="configure-topology-presets-btn"
                                            type="button"
                                            onClick={handleOpenTopologyPresets}
                                            className="dxc-btn-secondary px-3 py-1.5 text-xs flex items-center gap-1.5"
                                        >
                                            <Layers size={14} />
                                            TOPOLOGY PRESETS
                                        </button>
                                        <button
                                            id="configure-rack-topology-btn"
                                            type="button"
                                            onClick={handleOpenRackTopology}
                                            className="dxc-btn-secondary px-3 py-1.5 text-xs flex items-center gap-1.5"
                                        >
                                            <Network size={14} />
                                            RACK TOPOLOGY
                                        </button>
                                    </div>
                                )}
                            </div>

                            {nodeRows.length === 0 ? (
                                <p className="text-sm text-slate-500">No nodes reported.</p>
                            ) : nodeTopologyTab === 'hierarchy' ? (
                                <NodeHierarchyView
                                    nodes={nodeRows}
                                    assignments={topologyData?.assignments || {}}
                                    onConfigureNode={(node) => {
                                        loadTopology();
                                        setSelectedNodeForConfig(node);
                                    }}
                                />
                            ) : (
                                <div className="overflow-x-auto">
                                    <table className="w-full text-left border-collapse">
                                        <thead>
                                            <tr className="border-b border-slate-200/70 dark:border-slate-800 text-[11px] font-bold uppercase tracking-wider text-slate-400">
                                                <th className="py-2.5 pr-4">Hostname</th>
                                                <th className="py-2.5 px-3">IP</th>
                                                <th className="py-2.5 px-3">Status</th>
                                                <th className="py-2.5 px-3">Roles</th>
                                                <th className="py-2.5 px-3">GPU</th>
                                                <th className="py-2.5 px-3">Topology</th>
                                                <th className="py-2.5 px-3">Age</th>
                                                <th className="py-2.5 px-3">Version</th>
                                                <th className="py-2.5 px-3">CPU (Req / Total)</th>
                                                <th className="py-2.5 px-3">RAM (Req / Total)</th>
                                                <th className="py-2.5 px-3">Ephemeral Storage (Req / Total)</th>
                                                <th className="py-2.5 pl-3 text-right">Actions</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-slate-200/50 dark:divide-slate-800/60 text-sm">
                                            {nodeRows.map((node) => {
                                                const isReady = node.status === 'Ready';
                                                return (
                                                    <tr
                                                        key={node.hostname}
                                                        className="hover:bg-slate-100/50 dark:hover:bg-slate-800/30 transition-colors"
                                                    >
                                                        <td className="py-3 pr-4 font-semibold text-slate-900 dark:text-white whitespace-nowrap">
                                                            {node.hostname}
                                                        </td>
                                                        <td className="py-3 px-3 font-mono text-xs text-slate-600 dark:text-slate-300 whitespace-nowrap">
                                                            {node.ip || '—'}
                                                        </td>
                                                        <td className="py-3 px-3 whitespace-nowrap">
                                                            <span
                                                                className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-bold border ${isReady
                                                                    ? 'bg-green-500/10 border-green-500/20 text-green-500'
                                                                    : 'bg-red-500/10 border-red-500/20 text-red-500'
                                                                    }`}
                                                            >
                                                                <span className={`w-1.5 h-1.5 rounded-full ${isReady ? 'bg-green-500' : 'bg-red-500'}`} />
                                                                {node.status || 'Unknown'}
                                                            </span>
                                                        </td>
                                                        <td className="py-3 px-3 whitespace-nowrap">
                                                            {Array.isArray(node.roles) && node.roles.length > 0 ? (
                                                                <div className="flex flex-wrap gap-1">
                                                                    {node.roles.map((role) => (
                                                                        <span
                                                                            key={role}
                                                                            className="px-2 py-0.5 rounded-md text-[11px] font-semibold bg-slate-200/70 dark:bg-slate-800 text-slate-700 dark:text-slate-300"
                                                                        >
                                                                            {role}
                                                                        </span>
                                                                    ))}
                                                                </div>
                                                            ) : (
                                                                <span className="text-xs text-slate-400">—</span>
                                                            )}
                                                        </td>
                                                        <td className="py-3 px-3 whitespace-nowrap">
                                                            {node.gpu_vendor ? (
                                                                <span
                                                                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-bold bg-emerald-500/10 border border-emerald-500/20 text-emerald-500 uppercase"
                                                                    title={node.gpu_product || `${node.gpu_vendor.toUpperCase()} GPU`}
                                                                >
                                                                    <Cpu size={11} />
                                                                    {node.gpu_count > 0 ? `${node.gpu_count}x ` : ''}{node.gpu_vendor}
                                                                </span>
                                                            ) : (
                                                                <span className="text-xs text-slate-400">—</span>
                                                            )}
                                                        </td>
                                                        <td className="py-3 px-3 whitespace-nowrap">
                                                            {node.topology && Object.keys(node.topology).length > 0 ? (
                                                                <div className="flex flex-wrap gap-1">
                                                                    {Object.entries(node.topology).map(([tier, val]) => (
                                                                        <span
                                                                            key={tier}
                                                                            className="px-2 py-0.5 rounded-md text-[11px] font-mono bg-indigo-500/10 border border-indigo-500/20 text-indigo-500 dark:text-indigo-400"
                                                                        >
                                                                            {tier}:{val}
                                                                        </span>
                                                                    ))}
                                                                </div>
                                                            ) : (
                                                                <span className="text-xs text-slate-400">—</span>
                                                            )}
                                                        </td>
                                                        <td
                                                            className="py-3 px-3 text-xs font-medium text-slate-600 dark:text-slate-300 whitespace-nowrap tabular-nums"
                                                            title={node.creation_timestamp || ''}
                                                        >
                                                            {formatNodeAge(node.creation_timestamp)}
                                                        </td>
                                                        <td className="py-3 px-3 font-mono text-xs text-slate-600 dark:text-slate-300 whitespace-nowrap">
                                                            {node.version || '—'}
                                                        </td>
                                                        <td className="py-3 px-3">
                                                            <NodeResourceCell
                                                                requested={node.cpu_requested}
                                                                total={node.cpu_total}
                                                                unit="Cores"
                                                                barClass="bg-blue-500"
                                                            />
                                                        </td>
                                                        <td className="py-3 px-3">
                                                            <NodeResourceCell
                                                                requested={node.ram_requested}
                                                                total={node.ram_total}
                                                                unit="GiB"
                                                                barClass="bg-purple-500"
                                                            />
                                                        </td>
                                                        <td className="py-3 px-3">
                                                            <NodeResourceCell
                                                                requested={node.ephemeral_storage_requested}
                                                                total={node.ephemeral_storage_total}
                                                                unit="GiB"
                                                                barClass="bg-amber-500"
                                                            />
                                                        </td>
                                                        <td className="py-3 pl-3 text-right whitespace-nowrap">
                                                            {canConfigureNodes && (
                                                                <button
                                                                    id={`configure-node-${node.hostname}-btn`}
                                                                    type="button"
                                                                    onClick={() => {
                                                                        loadTopology();
                                                                        setSelectedNodeForConfig(node);
                                                                    }}
                                                                    className="p-2 rounded-lg text-slate-400 hover:text-indigo-500 hover:bg-slate-200/60 dark:hover:bg-slate-800 transition-colors"
                                                                    title="Configure Node Labels, Roles & GPU"
                                                                >
                                                                    <SlidersHorizontal size={15} />
                                                                </button>
                                                            )}
                                                        </td>
                                                    </tr>
                                                );
                                            })}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </div>
                    );
                })()}

                {/* Core Integrations (Bottom Full-Width Widget) */}
                {(() => {
                    const hasSyncState = Boolean(
                        syncState &&
                        syncState.total > 0 &&
                        syncState.status !== 'completed'
                    );
                    const hasMissingIntegration = CORE_INTEGRATIONS_CONFIG.some(
                        (item) =>
                            !clusterState[item.installedField] ||
                            clusterState.integrations_status?.[item.key]?.status === 'offline'
                    );
                    const syncTasks = syncState?.tasks || {};
                    const completedCount = syncState?.completed || 0;
                    const totalCount = syncState?.total || CORE_INTEGRATIONS_CONFIG.length;
                    const progressPercent = totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0;
                    const runningTasks = Object.values(syncTasks).filter(t => t.status === 'running');

                    return (
                        <div id="core-integrations-widget" className="space-y-6 bg-slate-50/50 dark:bg-slate-900/50 p-6 rounded-2xl border border-slate-200/50 dark:border-slate-800/50">
                            <div className="flex flex-wrap items-center justify-between gap-4">
                                <div>
                                    <p className="text-xs font-bold uppercase tracking-widest text-slate-400">Core Integrations</p>
                                    <p className="text-xs text-slate-500 mt-1">Cluster-wide operators and platform dependencies</p>
                                </div>
                                {hasMissingIntegration && (
                                    <button
                                        id="widget-sync-core-integrations-btn"
                                        onClick={() => handleInstallAction('sync_core_integrations')}
                                        disabled={isSyncInProgress}
                                        className="dxc-btn-primary py-2 px-4 text-xs flex items-center gap-2 disabled:opacity-60"
                                    >
                                        <RefreshCw size={14} className={isSyncInProgress ? "animate-spin" : ""} />
                                        {isSyncInProgress ? 'SYNCING...' : 'SYNC INTEGRATIONS'}
                                    </button>
                                )}
                            </div>

                            {/* Persistent Sync Progress Bar */}
                            {hasSyncState && (
                                <div
                                    id="core-integrations-sync-progress"
                                    className="p-4 bg-white dark:bg-slate-800/90 rounded-xl border border-slate-200 dark:border-slate-700 space-y-3"
                                >
                                    <div className="flex flex-wrap items-center justify-between gap-2">
                                        <div className="flex items-center gap-2">
                                            {syncState.status === 'in_progress' && (
                                                <Loader2 size={16} className="text-indigo-500 animate-spin" />
                                            )}
                                            {syncState.status === 'completed' && (
                                                <CheckCircle2 size={16} className="text-green-500" />
                                            )}
                                            {syncState.status === 'error' && (
                                                <AlertCircle size={16} className="text-red-500" />
                                            )}
                                            <span className="text-sm font-bold text-slate-800 dark:text-slate-100">
                                                {syncState.status === 'in_progress'
                                                    ? runningTasks.length > 0
                                                        ? `Syncing: ${runningTasks.map(t => t.label).join(', ')}`
                                                        : 'Preparing core integration tasks...'
                                                    : syncState.status === 'completed'
                                                        ? 'All core integrations synced'
                                                        : 'Core integrations sync completed with errors'}
                                            </span>
                                        </div>
                                        <div className="flex items-center gap-3">
                                            {syncState.status === 'in_progress' && (
                                                <button
                                                    type="button"
                                                    id="resume-sync-core-integrations-btn"
                                                    onClick={() => handleInstallAction('resume_sync_core_integrations')}
                                                    disabled={Boolean(installingActions['resume_sync_core_integrations'])}
                                                    title="Resume any interrupted sync tasks"
                                                    className="dxc-btn-secondary py-1 px-2.5 text-[11px] flex items-center gap-1 disabled:opacity-60"
                                                >
                                                    <RefreshCw size={12} className={installingActions['resume_sync_core_integrations'] ? "animate-spin" : ""} />
                                                    {installingActions['resume_sync_core_integrations'] ? 'RESUMING...' : 'RESUME'}
                                                </button>
                                            )}
                                            <span className="text-xs font-mono font-bold text-slate-500 dark:text-slate-400">
                                                {completedCount}/{totalCount} ({progressPercent}%)
                                            </span>
                                        </div>
                                    </div>

                                    <div className="h-2.5 w-full bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
                                        <div
                                            className={cn(
                                                "h-full transition-all duration-500 rounded-full",
                                                syncState.status === 'error'
                                                    ? 'bg-red-500'
                                                    : syncState.status === 'completed'
                                                        ? 'bg-green-500'
                                                        : 'bg-indigo-500'
                                            )}
                                            style={{ width: `${progressPercent}%` }}
                                        />
                                    </div>

                                    <div className="flex flex-wrap gap-2 pt-1">
                                        {CORE_INTEGRATIONS_CONFIG.map(({ key, name }) => {
                                            const task = syncTasks[key];
                                            if (!task) return null;
                                            const hasDetails = Boolean(task.message || task.logs || task.status === 'failed');
                                            return (
                                                <button
                                                    type="button"
                                                    key={key}
                                                    id={`sync-task-chip-${key}`}
                                                    onClick={() => hasDetails && setSelectedSyncTask({ key, name, ...task })}
                                                    disabled={!hasDetails}
                                                    title={hasDetails ? "Click to view task details & logs" : task.status}
                                                    className={cn(
                                                        "px-2.5 py-1 rounded-lg text-[11px] font-semibold border flex items-center gap-1.5 transition-all",
                                                        hasDetails && "cursor-pointer hover:brightness-95 dark:hover:brightness-110",
                                                        !hasDetails && "cursor-default",
                                                        task.status === 'completed' && "bg-green-500/10 border-green-500/20 text-green-600 dark:text-green-400",
                                                        task.status === 'running' && "bg-indigo-500/10 border-indigo-500/20 text-indigo-600 dark:text-indigo-400",
                                                        task.status === 'failed' && "bg-red-500/10 border-red-500/30 text-red-600 dark:text-red-400 underline decoration-red-400/50 underline-offset-2",
                                                        task.status === 'pending' && "bg-slate-100 dark:bg-slate-700/50 border-slate-200 dark:border-slate-600 text-slate-500 dark:text-slate-400"
                                                    )}
                                                >
                                                    {task.status === 'running' && <Loader2 size={11} className="animate-spin" />}
                                                    {task.status === 'completed' && <CheckCircle2 size={11} />}
                                                    {task.status === 'failed' && <AlertCircle size={11} />}
                                                    {task.status === 'pending' && <Clock size={11} />}
                                                    <span>{name}</span>
                                                </button>
                                            );
                                        })}
                                    </div>
                                </div>
                            )}

                            {/* Integration Cards Grid */}
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                                {CORE_INTEGRATIONS_CONFIG.map((item) => {
                                    const info = clusterState.integrations_status?.[item.key];
                                    const isInstalled = Boolean(clusterState[item.installedField]);
                                    const status = info?.status || (isInstalled ? 'online' : 'offline');
                                    const version = info?.version || clusterState[item.versionField];
                                    const message = info?.message || (isInstalled ? 'Installed' : 'Not installed');
                                    const taskStatus = syncTasks[item.key]?.status;
                                    const isActiveIcon = status === 'online' || status === 'pending' || taskStatus === 'running';

                                    const isArgoCard = item.key === 'argocd';
                                    const argoUrl = info?.url;
                                    const argoLogin = info?.username || (isInstalled ? 'admin' : null);
                                    const argoPassword = info?.initial_admin_password;

                                    return (
                                        <div
                                            key={item.key}
                                            id={`core-integration-${item.key}`}
                                            className={cn(
                                                "flex flex-col justify-between gap-3 p-4 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700",
                                                isArgoCard && "col-span-full"
                                            )}
                                        >
                                            <div className="flex items-start justify-between gap-2">
                                                <div className="flex items-center gap-3 min-w-0">
                                                    <div className={cn(
                                                        "p-2 rounded-lg shrink-0",
                                                        isActiveIcon ? "bg-indigo-500 text-white" : "bg-slate-200 dark:bg-slate-700 text-slate-400"
                                                    )}>
                                                        {status === 'pending' || taskStatus === 'running' ? (
                                                            <Loader2 size={16} className="animate-spin" />
                                                        ) : (
                                                            <Activity size={16} />
                                                        )}
                                                    </div>
                                                    <div className="min-w-0">
                                                        <p className="text-sm font-bold text-slate-700 dark:text-white truncate">{item.name}</p>
                                                        {version && (
                                                            <p className="text-[11px] font-mono text-slate-400 truncate">{version}</p>
                                                        )}
                                                    </div>
                                                </div>
                                                <IntegrationStatusBadge status={status} />
                                            </div>
                                            <p className="text-xs text-slate-500 dark:text-slate-400 truncate" title={message}>
                                                {message}
                                            </p>

                                            {isArgoCard && isInstalled && (
                                                <div
                                                    id="argocd-access-details"
                                                    className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-3 mt-1 border-t border-slate-200/70 dark:border-slate-700/70"
                                                >
                                                    <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-900/60 border border-slate-200/70 dark:border-slate-700/60 space-y-1">
                                                        <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
                                                            LoadBalancer URL
                                                        </p>
                                                        <div className="flex items-center justify-between gap-2 min-w-0">
                                                            {argoUrl ? (
                                                                <a
                                                                    id="argocd-lb-url"
                                                                    href={argoUrl}
                                                                    target="_blank"
                                                                    rel="noopener noreferrer"
                                                                    className="text-xs font-mono font-semibold text-indigo-600 dark:text-indigo-400 hover:underline flex items-center gap-1.5 truncate"
                                                                    title={argoUrl}
                                                                >
                                                                    <span className="truncate">{argoUrl}</span>
                                                                    <ExternalLink size={12} className="shrink-0" />
                                                                </a>
                                                            ) : (
                                                                <span id="argocd-lb-url" className="text-xs font-mono text-slate-400">
                                                                    Pending LoadBalancer IP...
                                                                </span>
                                                            )}
                                                            {argoUrl && (
                                                                <button
                                                                    id="argocd-copy-url-btn"
                                                                    type="button"
                                                                    onClick={() => handleCopyArgoValue('url', argoUrl)}
                                                                    className="p-1 rounded text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-colors shrink-0"
                                                                    title="Copy URL"
                                                                >
                                                                    {copiedArgoField === 'url' ? (
                                                                        <Check size={13} className="text-green-500" />
                                                                    ) : (
                                                                        <Copy size={13} />
                                                                    )}
                                                                </button>
                                                            )}
                                                        </div>
                                                    </div>

                                                    <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-900/60 border border-slate-200/70 dark:border-slate-700/60 space-y-1">
                                                        <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
                                                            Login
                                                        </p>
                                                        <div className="flex items-center justify-between gap-2 min-w-0">
                                                            <span
                                                                id="argocd-login"
                                                                className="text-xs font-mono font-semibold text-slate-700 dark:text-slate-200 truncate"
                                                            >
                                                                {argoLogin || '—'}
                                                            </span>
                                                            {argoLogin && (
                                                                <button
                                                                    id="argocd-copy-login-btn"
                                                                    type="button"
                                                                    onClick={() => handleCopyArgoValue('username', argoLogin)}
                                                                    className="p-1 rounded text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-colors shrink-0"
                                                                    title="Copy Login"
                                                                >
                                                                    {copiedArgoField === 'username' ? (
                                                                        <Check size={13} className="text-green-500" />
                                                                    ) : (
                                                                        <Copy size={13} />
                                                                    )}
                                                                </button>
                                                            )}
                                                        </div>
                                                    </div>

                                                    <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-900/60 border border-slate-200/70 dark:border-slate-700/60 space-y-1">
                                                        <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
                                                            Initial Admin Password
                                                        </p>
                                                        <div className="flex items-center justify-between gap-2 min-w-0">
                                                            <span
                                                                id="argocd-initial-password"
                                                                className="text-xs font-mono font-semibold text-slate-700 dark:text-slate-200 truncate"
                                                            >
                                                                {argoPassword
                                                                    ? (showArgoPassword ? argoPassword : '••••••••••••')
                                                                    : 'Unavailable'}
                                                            </span>
                                                            {argoPassword && (
                                                                <div className="flex items-center gap-1 shrink-0">
                                                                    <button
                                                                        id="argocd-toggle-password-btn"
                                                                        type="button"
                                                                        onClick={() => setShowArgoPassword((prev) => !prev)}
                                                                        className="p-1 rounded text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-colors"
                                                                        title={showArgoPassword ? 'Hide Password' : 'Show Password'}
                                                                    >
                                                                        {showArgoPassword ? <EyeOff size={13} /> : <Eye size={13} />}
                                                                    </button>
                                                                    <button
                                                                        id="argocd-copy-password-btn"
                                                                        type="button"
                                                                        onClick={() => handleCopyArgoValue('password', argoPassword)}
                                                                        className="p-1 rounded text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-colors"
                                                                        title="Copy Password"
                                                                    >
                                                                        {copiedArgoField === 'password' ? (
                                                                            <Check size={13} className="text-green-500" />
                                                                        ) : (
                                                                            <Copy size={13} />
                                                                        )}
                                                                    </button>
                                                                </div>
                                                            )}
                                                        </div>
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    );
                })()}
            </div>

            <Modal
                isOpen={Boolean(selectedSyncTask)}
                onClose={() => {
                    setSelectedSyncTask(null);
                    setCopiedLogs(false);
                }}
                title={selectedSyncTask ? `${selectedSyncTask.name} Sync Details` : 'Sync Details'}
                maxWidth="max-w-3xl"
            >
                {selectedSyncTask && (
                    <div className="space-y-4">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                                <span className="text-xs font-bold uppercase tracking-widest text-slate-400">Status</span>
                                <span className={cn(
                                    "px-2.5 py-0.5 rounded-full text-xs font-bold uppercase",
                                    selectedSyncTask.status === 'failed' && "bg-red-500/10 text-red-500",
                                    selectedSyncTask.status === 'completed' && "bg-green-500/10 text-green-500",
                                    selectedSyncTask.status === 'running' && "bg-indigo-500/10 text-indigo-500",
                                    selectedSyncTask.status === 'pending' && "bg-slate-200 dark:bg-slate-700 text-slate-500"
                                )}>
                                    {selectedSyncTask.status}
                                </span>
                            </div>
                            {(selectedSyncTask.logs || selectedSyncTask.message) && (
                                <button
                                    type="button"
                                    onClick={() => {
                                        const text = selectedSyncTask.logs || selectedSyncTask.message || '';
                                        navigator.clipboard?.writeText(text);
                                        setCopiedLogs(true);
                                        setTimeout(() => setCopiedLogs(false), 2000);
                                    }}
                                    className="dxc-btn-secondary px-3 py-1.5 text-xs flex items-center gap-1.5"
                                >
                                    {copiedLogs ? <Check size={14} className="text-green-500" /> : <Copy size={14} />}
                                    {copiedLogs ? 'COPIED' : 'COPY LOGS'}
                                </button>
                            )}
                        </div>

                        {selectedSyncTask.message && (
                            <div className={cn(
                                "p-4 rounded-xl border text-sm font-mono whitespace-pre-wrap break-words",
                                selectedSyncTask.status === 'failed'
                                    ? "bg-red-500/10 border-red-500/20 text-red-500"
                                    : "bg-slate-100 dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300"
                            )}>
                                {selectedSyncTask.message}
                            </div>
                        )}

                        {selectedSyncTask.logs && (
                            <div className="space-y-2">
                                <p className="text-xs font-bold uppercase tracking-widest text-slate-400">Logs / Traceback</p>
                                <pre className="p-4 bg-slate-950 text-slate-200 rounded-xl border border-slate-800 text-xs font-mono overflow-x-auto max-h-96 whitespace-pre-wrap break-words">
                                    {selectedSyncTask.logs}
                                </pre>
                            </div>
                        )}

                        {!selectedSyncTask.message && !selectedSyncTask.logs && (
                            <p className="text-sm text-slate-500">No additional logs recorded for this task.</p>
                        )}
                    </div>
                )}
            </Modal>

            <NodeConfigModal
                isOpen={Boolean(selectedNodeForConfig)}
                onClose={() => setSelectedNodeForConfig(null)}
                node={selectedNodeForConfig}
                availableRoles={topologyData?.roles || []}
                onSave={handleSaveNodeConfig}
            />

            <RackTopologyModal
                isOpen={isRackTopologyOpen}
                onClose={() => setIsRackTopologyOpen(false)}
                topologyData={topologyData}
                nodes={Array.isArray(clusterState.nodes_details) ? clusterState.nodes_details : []}
                onSave={handleSaveRackTopology}
                onOpenPresets={handleOpenTopologyPresets}
            />

            <TopologyPresetsModal
                isOpen={isTopologyPresetsOpen}
                onClose={() => setIsTopologyPresetsOpen(false)}
                topologyData={topologyData}
                onSave={handleSaveRackTopology}
            />

        </div>
    );
};

export default ServiceView;
