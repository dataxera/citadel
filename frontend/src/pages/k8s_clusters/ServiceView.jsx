import React, { useState, useEffect, useCallback } from 'react';
import {
    Activity, Monitor, RefreshCw, CheckCircle2, AlertCircle, Loader2, Clock, Copy, Check
} from 'lucide-react';
import { useNotification } from '../../providers/NotificationProvider';
import Modal from '../../components/Modal';
import { cn } from '../../utils/cn';
import { useVisibilityPolling } from '../../hooks/useStatePolling';

const CORE_INTEGRATIONS_CONFIG = [
    { key: 'argocd', name: 'ArgoCD', installedField: 'argocd_installed', versionField: 'argocd_version' },
    { key: 'cert_manager', name: 'Cert Manager', installedField: 'cert_manager_installed', versionField: 'cert_manager_version' },
    { key: 'cnpg', name: 'CNPG Operator', installedField: 'cnpg_installed', versionField: 'cnpg_version' },
    { key: 'envoy_gateway', name: 'Envoy Gateway', installedField: 'envoy_gateway_installed', versionField: 'envoy_gateway_version' },
    { key: 'kafka_operator', name: 'Kafka Operator', installedField: 'kafka_operator_installed', versionField: 'kafka_operator_version' },
    { key: 'nifikop', name: 'NiFi Operator', installedField: 'nifikop_installed', versionField: 'nifikop_version' },
    { key: 'doris_operator', name: 'Doris Operator', installedField: 'doris_operator_installed', versionField: 'doris_operator_version' },
];

const IntegrationStatusBadge = ({ status }) => {
    const styles = {
        online: 'mw-badge-success',
        pending: 'mw-badge-warning',
        offline: 'mw-badge-neutral',
        error: 'mw-badge-danger',
    };
    return (
        <span className={cn(styles[status] || 'mw-badge-neutral')}>
            {(status || 'unknown').toUpperCase()}
        </span>
    );
};

const ServiceView = ({
    selectedClusterId,
    selectedCluster,
    onBack,
    clustersHook
}) => {
    const { getClusterState, refreshClusterState } = clustersHook;
    const [clusterState, setClusterState] = useState(null);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const [installingActions, setInstallingActions] = useState({});
    const [selectedSyncTask, setSelectedSyncTask] = useState(null);
    const [copiedLogs, setCopiedLogs] = useState(false);
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
            setClusterState(newState);
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

    if (!clusterState) {
        return (
            <div className="space-y-8 animate-in fade-in duration-500">
                <div className="mw-page-header">
                    <div className="flex gap-4 items-center">
                        <div className="mw-icon-box w-16 h-16 text-slate-400">
                            <Monitor size={32} />
                        </div>
                        <div>
                            <h2 className="text-4xl font-bold tracking-tight text-slate-900 dark:text-white">Loading Cluster State...</h2>
                        </div>
                    </div>
                    <div className="flex gap-3">
                        <button
                            onClick={onBack}
                            className="mw-btn-secondary px-6 py-2.5"
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
            <div className="mw-page-header">
                <div className="flex gap-4 items-center">
                    <div className="mw-icon-box w-16 h-16 text-indigo-400">
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
                        className="mw-btn-secondary px-6 py-2.5 flex items-center gap-2"
                    >
                        <RefreshCw size={16} className={isRefreshing ? "animate-spin" : ""} />
                        {isRefreshing ? 'REFRESHING...' : 'REFRESH'}
                    </button>
                    <button
                        id="sync-core-integrations-btn"
                        onClick={() => handleInstallAction('sync_core_integrations')}
                        disabled={isSyncInProgress}
                        className="mw-btn-secondary px-6 py-2.5 flex items-center gap-2 disabled:opacity-60"
                    >
                        <RefreshCw size={16} className={isSyncInProgress ? "animate-spin" : ""} />
                        {isSyncInProgress ? 'SYNCING...' : 'SYNC INTEGRATIONS'}
                    </button>
                    <button
                        onClick={onBack}
                        className="mw-btn-secondary px-6 py-2.5"
                    >
                        BACK TO LIST
                    </button>
                </div>
            </div>

            <div className="mw-card p-8 space-y-8 animate-in slide-in-from-bottom duration-700">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <div className="mw-icon-box text-blue-500">
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

                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                    {/* Resource Utilization */}
                    <div className="space-y-6 bg-slate-50/50 dark:bg-slate-900/50 p-6 rounded-2xl border border-slate-200/50 dark:border-slate-800/50">
                        <div className="space-y-4">
                            <div className="flex justify-between items-end">
                                <p className="text-xs font-bold uppercase tracking-widest text-slate-400">Total CPU Allocation</p>
                                <p className="text-sm font-bold text-slate-900 dark:text-white">{(clusterState.cpu_total || 0).toFixed(1)} Cores</p>
                            </div>
                            <div className="h-2 w-full bg-slate-200 dark:bg-slate-800 rounded-full overflow-hidden">
                                <div
                                    className="h-full bg-blue-500 transition-all duration-1000"
                                    style={{ width: '100%' }}
                                />
                            </div>
                        </div>
                        <div className="space-y-4">
                            <div className="flex justify-between items-end">
                                <p className="text-xs font-bold uppercase tracking-widest text-slate-400">Total RAM Capacity</p>
                                <p className="text-sm font-bold text-slate-900 dark:text-white">{(clusterState.ram_total || 0).toFixed(1)} GiB</p>
                            </div>
                            <div className="h-2 w-full bg-slate-200 dark:bg-slate-800 rounded-full overflow-hidden">
                                <div
                                    className="h-full bg-purple-500 transition-all duration-1000"
                                    style={{ width: '100%' }}
                                />
                            </div>
                        </div>
                    </div>

                    {/* Node Cluster Map */}
                    <div className="space-y-4 bg-slate-50/50 dark:bg-slate-900/50 p-6 rounded-2xl border border-slate-200/50 dark:border-slate-800/50">
                        <p className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-4">Node Topology ({clusterState.node_count || 0})</p>
                        <div className="flex flex-wrap gap-2">
                            {Object.entries(clusterState.nodes_status || {}).map(([name, status]) => (
                                <div
                                    key={name}
                                    className={`px-3 py-1.5 rounded-lg text-xs font-bold border flex items-center gap-2 ${status === 'Ready'
                                        ? 'bg-green-500/10 border-green-500/20 text-green-500'
                                        : 'bg-red-500/10 border-red-500/20 text-red-500'
                                        }`}
                                    title={`${name}: ${status}`}
                                >
                                    <div className={`w-1.5 h-1.5 rounded-full ${status === 'Ready' ? 'bg-green-500' : 'bg-red-500'}`} />
                                    {name.split('-').pop()}
                                </div>
                            ))}
                        </div>
                    </div>
                </div>

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
                                        className="mw-btn-primary py-2 px-4 text-xs flex items-center gap-2 disabled:opacity-60"
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
                                        <span className="text-xs font-mono font-bold text-slate-500 dark:text-slate-400">
                                            {completedCount}/{totalCount} ({progressPercent}%)
                                        </span>
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

                                    return (
                                        <div
                                            key={item.key}
                                            id={`core-integration-${item.key}`}
                                            className="flex flex-col justify-between gap-3 p-4 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700"
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
                                    className="mw-btn-secondary px-3 py-1.5 text-xs flex items-center gap-1.5"
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

        </div>
    );
};

export default ServiceView;
