import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
    Activity, Monitor, RefreshCw, CheckCircle2, AlertCircle, AlertTriangle, Loader2, Clock, Copy, Check,
    Network, SlidersHorizontal, Cpu, Layers, Table2, GitBranch, ExternalLink, Eye, EyeOff, HardDrive, ChevronDown
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
import { CORE_INTEGRATIONS_CONFIG, clusterNeedsIntegrationSync } from './coreIntegrations';

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

const PvStatusBadge = ({ status }) => {
    const normalized = (status || 'unknown').toLowerCase();
    const styles = {
        bound: 'dxc-badge-success',
        available: 'dxc-badge-neutral',
        released: 'dxc-badge-warning',
        failed: 'dxc-badge-danger',
    };
    return (
        <span className={cn(styles[normalized] || 'dxc-badge-neutral')}>
            {(status || 'Unknown').toUpperCase()}
        </span>
    );
};

const PvUtilizationCell = ({ pv }) => {
    const cap = typeof pv.capacity_gib === 'number' ? pv.capacity_gib : 0;
    const hasTelemetry = typeof pv.used_gib === 'number';
    if (!hasTelemetry) {
        return (
            <div className="min-w-[160px] space-y-0.5">
                <span className="text-xs font-semibold text-slate-700 dark:text-slate-200 tabular-nums">
                    {cap > 0 ? `${cap.toFixed(1)} GiB` : '—'}
                </span>
                <p className="text-[11px] text-slate-400">No usage telemetry</p>
            </div>
        );
    }
    const pct = typeof pv.utilization_pct === 'number'
        ? Math.min(100, Math.round(pv.utilization_pct))
        : (cap > 0 ? Math.min(100, Math.round((pv.used_gib / cap) * 100)) : 0);
    const barClass = pct >= 90 ? 'bg-red-500' : pct >= 80 ? 'bg-amber-500' : 'bg-emerald-500';
    return (
        <div className="min-w-[160px] space-y-1">
            <div className="flex items-center justify-between gap-2 text-xs">
                <span className="font-semibold text-slate-700 dark:text-slate-200 tabular-nums">
                    {pv.used_gib.toFixed(2)} / {cap.toFixed(1)} GiB
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
    const [selectedSyncTaskRef, setSelectedSyncTaskRef] = useState(null);
    const [copiedLogs, setCopiedLogs] = useState(false);
    const [syncAccordionExpanded, setSyncAccordionExpanded] = useState(null);
    const logContainerRef = useRef(null);
    const shouldAutoScrollRef = useRef(true);
    const [showArgoPassword, setShowArgoPassword] = useState(false);
    const [copiedArgoField, setCopiedArgoField] = useState(null);
    const [selectedNodeForConfig, setSelectedNodeForConfig] = useState(null);
    const [isRackTopologyOpen, setIsRackTopologyOpen] = useState(false);
    const [isTopologyPresetsOpen, setIsTopologyPresetsOpen] = useState(false);
    const [topologyData, setTopologyData] = useState(null);
    const [nodeTopologyTab, setNodeTopologyTab] = useState('table');
    const { showSuccess, showError } = useNotification();


    const syncState = clusterState?.sync_state;
    const syncTasksMap = syncState?.tasks || {};
    const selectedSyncTask = selectedSyncTaskRef
        ? {
              key: selectedSyncTaskRef.key,
              name: selectedSyncTaskRef.name,
              ...(syncTasksMap[selectedSyncTaskRef.key] || {}),
          }
        : null;

    useEffect(() => {
        if (selectedSyncTask?.logs && shouldAutoScrollRef.current && logContainerRef.current) {
            logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
        }
    }, [selectedSyncTask?.logs]);

    const pollClusterState = useCallback(() => {
        if (!selectedClusterId || !getClusterState) return;
        getClusterState(selectedClusterId)
            .then((state) => {
                setClusterState(state);
                if (state?.sync_state?.status === 'in_progress' || state?.sync_state?.status === 'error') {
                    setSyncAccordionExpanded((prev) => (prev === null ? true : prev));
                }
            })
            .catch(console.error);
    }, [selectedClusterId, getClusterState]);

    useEffect(() => {
        if (!selectedClusterId) {
            Promise.resolve().then(() => {
                setClusterState(null);
                setSyncAccordionExpanded(null);
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
        if (actionId === 'sync_core_integrations' || actionId === 'resume_sync_core_integrations') {
            setSyncAccordionExpanded(true);
        }
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

    const isSyncInProgress = Boolean(
        installingActions['sync_core_integrations'] ||
        syncState?.status === 'in_progress'
    );
    const needsIntegrationSync = !isSyncInProgress && clusterNeedsIntegrationSync(clusterState);

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
                        className={cn(
                            "px-6 py-2.5 flex items-center gap-2 disabled:opacity-60",
                            needsIntegrationSync
                                ? "bg-amber-500 hover:bg-amber-600 text-white font-bold rounded-xl shadow-lg shadow-amber-500/25 transition-all"
                                : "dxc-btn-secondary"
                        )}
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

            {needsIntegrationSync && (
                <div
                    id="cluster-integration-sync-alert"
                    className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-5 rounded-2xl bg-amber-500/10 border border-amber-500/30 text-amber-900 dark:text-amber-200 animate-in fade-in duration-300"
                >
                    <div className="flex items-start sm:items-center gap-4">
                        <div className="p-2.5 rounded-xl bg-amber-500/20 text-amber-600 dark:text-amber-400 shrink-0">
                            <AlertTriangle size={22} />
                        </div>
                        <div>
                            <h4 className="text-sm font-bold uppercase tracking-wide text-amber-800 dark:text-amber-300">
                                Core Integrations Require Sync
                            </h4>
                            <p className="text-sm text-amber-700 dark:text-amber-200/80 mt-0.5">
                                One or more core integrations need to be installed or updated on this cluster.
                            </p>
                        </div>
                    </div>
                    <button
                        id="alert-sync-core-integrations-btn"
                        onClick={() => handleInstallAction('sync_core_integrations')}
                        disabled={isSyncInProgress}
                        className="bg-amber-500 hover:bg-amber-600 text-white font-bold px-5 py-2.5 rounded-xl text-xs flex items-center gap-2 shrink-0 shadow-md shadow-amber-500/20 transition-all disabled:opacity-60"
                    >
                        <RefreshCw size={14} className={isSyncInProgress ? "animate-spin" : ""} />
                        {isSyncInProgress ? 'SYNCING...' : 'SYNC INTEGRATIONS'}
                    </button>
                </div>
            )}

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

                {/* Core Integrations (Top Full-Width Widget) */}
                {(() => {
                    const hasSyncState = Boolean(
                        syncState &&
                        syncState.total > 0
                    );
                    const syncStatus = syncState?.status;
                    const isSyncProgressExpanded =
                        syncAccordionExpanded !== null
                            ? syncAccordionExpanded
                            : syncStatus !== 'completed';
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
                            </div>

                            {/* Persistent Sync Progress Bar (Collapsible Accordion) */}
                            {hasSyncState && (
                                <div
                                    id="core-integrations-sync-progress"
                                    className="p-4 bg-white dark:bg-slate-800/90 rounded-xl border border-slate-200 dark:border-slate-700 space-y-3"
                                >
                                    <div
                                        role="button"
                                        tabIndex={0}
                                        id="core-integrations-sync-accordion-toggle"
                                        onClick={() => setSyncAccordionExpanded(!isSyncProgressExpanded)}
                                        onKeyDown={(e) => {
                                            if (e.key === 'Enter' || e.key === ' ') {
                                                e.preventDefault();
                                                setSyncAccordionExpanded(!isSyncProgressExpanded);
                                            }
                                        }}
                                        aria-expanded={isSyncProgressExpanded}
                                        className="flex flex-wrap items-center justify-between gap-2 cursor-pointer select-none"
                                    >
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
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        handleInstallAction('resume_sync_core_integrations');
                                                    }}
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
                                            <ChevronDown
                                                size={16}
                                                className={cn(
                                                    "text-slate-400 transition-transform duration-200",
                                                    isSyncProgressExpanded ? "rotate-180" : ""
                                                )}
                                            />
                                        </div>
                                    </div>

                                    {isSyncProgressExpanded && (
                                        <>
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
                                                    return (
                                                        <button
                                                            type="button"
                                                            key={key}
                                                            id={`sync-task-chip-${key}`}
                                                            onClick={() => {
                                                                shouldAutoScrollRef.current = true;
                                                                setSelectedSyncTaskRef({ key, name });
                                                            }}
                                                            title="Click to view task details & live logs"
                                                            className={cn(
                                                                "px-2.5 py-1 rounded-lg text-[11px] font-semibold border flex items-center gap-1.5 transition-all cursor-pointer hover:brightness-95 dark:hover:brightness-110",
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
                                        </>
                                    )}
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

                {/* Persistent Volumes & Disk Utilization */}
                {(() => {
                    const pvRows = Array.isArray(clusterState.pvs_details) ? clusterState.pvs_details : [];
                    const totalCapacityGib = pvRows.reduce(
                        (sum, pv) => sum + (typeof pv.capacity_gib === 'number' ? pv.capacity_gib : 0),
                        0
                    );
                    const pvsWithUsage = pvRows.filter((pv) => typeof pv.used_gib === 'number');
                    const totalUsedGib = pvsWithUsage.reduce((sum, pv) => sum + pv.used_gib, 0);

                    return (
                        <div
                            id="pvs-utilization-widget"
                            className="space-y-4 bg-slate-50/50 dark:bg-slate-900/50 p-6 rounded-2xl border border-slate-200/50 dark:border-slate-800/50"
                        >
                            <div className="flex flex-wrap items-center justify-between gap-4">
                                <div className="flex items-center gap-3">
                                    <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-500">
                                        <HardDrive size={18} />
                                    </div>
                                    <div>
                                        <p className="text-xs font-bold uppercase tracking-widest text-slate-400">
                                            Persistent Volumes ({pvRows.length})
                                        </p>
                                        <p className="text-xs text-slate-500 mt-0.5 tabular-nums">
                                            Total Allocated: {totalCapacityGib.toFixed(1)} GiB
                                            {pvsWithUsage.length > 0 && ` • Used: ${totalUsedGib.toFixed(2)} GiB`}
                                        </p>
                                    </div>
                                </div>
                            </div>

                            {pvRows.length === 0 ? (
                                <p className="text-sm text-slate-500 dark:text-slate-400">
                                    No persistent volumes found in this cluster.
                                </p>
                            ) : (
                                <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/80">
                                    <table id="pvs-table" className="w-full text-left border-collapse">
                                        <thead>
                                            <tr className="border-b border-slate-200 dark:border-slate-800 text-[11px] font-bold uppercase tracking-wider text-slate-400">
                                                <th className="py-3 px-4">Volume</th>
                                                <th className="py-3 px-4">Status</th>
                                                <th className="py-3 px-4">StorageClass</th>
                                                <th className="py-3 px-4">Node</th>
                                                <th className="py-3 px-4">Claim</th>
                                                <th className="py-3 px-4">Disk Utilization</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-slate-100 dark:divide-slate-800/70 text-sm">
                                            {pvRows.map((pv) => {
                                                const claimLabel = pv.claim_namespace && pv.claim_name
                                                    ? `${pv.claim_namespace}/${pv.claim_name}`
                                                    : 'Unbound';
                                                return (
                                                    <tr
                                                        key={pv.name}
                                                        data-pv-name={pv.name}
                                                        className="hover:bg-slate-50/80 dark:hover:bg-slate-800/40 transition-colors"
                                                    >
                                                        <td className="py-3 px-4">
                                                            <div className="font-mono text-xs font-semibold text-slate-800 dark:text-slate-100">
                                                                {pv.name}
                                                            </div>
                                                            <div className="text-[11px] text-slate-400 mt-0.5">
                                                                {pv.reclaim_policy || '—'}
                                                                {Array.isArray(pv.access_modes) && pv.access_modes.length > 0
                                                                    ? ` • ${pv.access_modes.join(', ')}`
                                                                    : ''}
                                                            </div>
                                                        </td>
                                                        <td className="py-3 px-4">
                                                            <PvStatusBadge status={pv.status} />
                                                        </td>
                                                        <td className="py-3 px-4">
                                                            <span className="px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-xs font-mono text-slate-600 dark:text-slate-300">
                                                                {pv.storage_class || '—'}
                                                            </span>
                                                        </td>
                                                        <td className="py-3 px-4 text-xs font-mono text-slate-600 dark:text-slate-300">
                                                            {pv.node_name || '—'}
                                                        </td>
                                                        <td className="py-3 px-4 text-xs font-mono text-slate-600 dark:text-slate-300">
                                                            {claimLabel}
                                                        </td>
                                                        <td className="py-3 px-4">
                                                            <PvUtilizationCell pv={pv} />
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

            </div>

            <Modal
                isOpen={Boolean(selectedSyncTask)}
                onClose={() => {
                    setSelectedSyncTaskRef(null);
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
                                    "px-2.5 py-0.5 rounded-full text-xs font-bold uppercase inline-flex items-center gap-1.5",
                                    selectedSyncTask.status === 'failed' && "bg-red-500/10 text-red-500",
                                    selectedSyncTask.status === 'completed' && "bg-green-500/10 text-green-500",
                                    selectedSyncTask.status === 'running' && "bg-indigo-500/10 text-indigo-500",
                                    selectedSyncTask.status === 'pending' && "bg-slate-200 dark:bg-slate-700 text-slate-500"
                                )}>
                                    {selectedSyncTask.status === 'running' && <Loader2 size={11} className="animate-spin" />}
                                    {selectedSyncTask.status}
                                </span>
                                {selectedSyncTask.status === 'running' && (
                                    <span className="text-[11px] font-medium text-indigo-500 flex items-center gap-1">
                                        <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse" />
                                        Streaming output
                                    </span>
                                )}
                            </div>
                            {(selectedSyncTask.logs || selectedSyncTask.message) && (
                                <button
                                    type="button"
                                    onClick={() => {
                                        const text = [selectedSyncTask.message, selectedSyncTask.logs].filter(Boolean).join('\n\n');
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
                                <p className="text-xs font-bold uppercase tracking-widest text-slate-400">Task Output (stdout / stderr)</p>
                                <pre
                                    ref={logContainerRef}
                                    onScroll={(e) => {
                                        const el = e.currentTarget;
                                        const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
                                        shouldAutoScrollRef.current = nearBottom;
                                    }}
                                    className="p-4 bg-slate-950 text-slate-200 rounded-xl border border-slate-800 text-xs font-mono overflow-x-auto max-h-96 whitespace-pre-wrap break-words"
                                >
                                    {selectedSyncTask.logs}
                                </pre>
                            </div>
                        )}

                        {!selectedSyncTask.message && !selectedSyncTask.logs && (
                            <p className="text-sm text-slate-500">
                                {selectedSyncTask.status === 'running'
                                    ? 'Task is running, waiting for output...'
                                    : selectedSyncTask.status === 'pending'
                                        ? 'Task is queued and waiting to start...'
                                        : 'No additional logs recorded for this task.'}
                            </p>
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
