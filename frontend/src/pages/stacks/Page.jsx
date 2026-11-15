// SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
// SPDX-License-Identifier: AGPLv3+

import React, { useMemo, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { Layers, Box, Info, Tag, RefreshCcw, Package, FileCode, Search } from 'lucide-react';
import { useStacks } from '../../hooks/useResources';
import { cn } from '../../utils/cn';

// Mapping backend component keys to user-friendly titles
const COMPONENT_TITLES = {
    pgsql: 'PostgreSQL',
    nifi: 'Apache NiFi',
    airflow: 'Apache Airflow',
    kafka: 'Apache Kafka',
    ranger: 'Apache Ranger',
    superset: 'Apache Superset',
    hive_metastore: 'Hive Metastore',
    trino: 'Trino',
    doris: 'Apache Doris',
    argocd: 'ArgoCD',
    'cert-manager': 'Cert Manager',
    cnpg: 'CloudNativePG Operator',
    'envoy-gateway': 'Envoy Gateway',
    'kafka-operator': 'Strimzi Kafka Operator',
    'nifikop-operator': 'NiFiKop Operator',
    'doris-operator': 'Apache Doris Operator',
};

const getPackageType = (comp) => {
    if (comp?.package_type === 'helm' || comp?.package_type === 'yml') {
        return comp.package_type;
    }
    if ((comp?.charts && Object.keys(comp.charts).length > 0) || comp?.chart_version) {
        return 'helm';
    }
    return 'yml';
};

const getCharts = (comp) => {
    if (comp?.charts && Object.keys(comp.charts).length > 0) {
        return Object.entries(comp.charts)
            .sort(([a], [b]) => (a === 'main' ? -1 : b === 'main' ? 1 : 0))
            .map(([key, chart]) => ({
                key,
                repo: chart?.repo || '',
                chart: chart?.chart || '',
                version: chart?.version || '',
            }));
    }
    if (comp?.chart_version) {
        return [{ key: 'main', repo: '', chart: '', version: comp.chart_version }];
    }
    return [];
};

const getImages = (comp) => {
    const images = comp?.images || {};
    return Object.entries(images)
        .sort(([a], [b]) => (a === 'main' ? -1 : b === 'main' ? 1 : 0))
        .map(([key, img]) => ({
            key,
            repository: img?.repository || '',
            tag: img?.tag || '',
        }));
};

const StacksPage = () => {
    const { darkMode } = useOutletContext();
    const { stacks, loading, error } = useStacks();
    const [selectedStackId, setSelectedStackId] = useState(null);
    const [componentFilter, setComponentFilter] = useState('');

    const cardBg = darkMode ? "bg-slate-900/60 border-slate-800" : "bg-white border-slate-200";
    const titleColor = darkMode ? "text-white" : "text-slate-900";
    const descColor = darkMode ? "text-slate-400" : "text-slate-600";
    const subBg = darkMode ? "bg-slate-950/60" : "bg-slate-50";
    const rowBorder = darkMode ? "border-slate-800/80" : "border-slate-200";
    const tableHeaderBg = darkMode ? "bg-slate-900/80 text-slate-400" : "bg-slate-100/80 text-slate-500";

    const selectedStack = stacks.find(s => s.id === selectedStackId) || stacks[0];

    const componentEntries = useMemo(() => {
        const all = Object.entries(selectedStack?.configuration?.components || {});
        const query = componentFilter.trim().toLowerCase();
        if (!query) return all;
        return all.filter(([key, comp]) => {
            const title = (COMPONENT_TITLES[key] || key).toLowerCase();
            const images = getImages(comp);
            const matchesImage = images.some(
                (img) =>
                    img.key.toLowerCase().includes(query) ||
                    img.repository.toLowerCase().includes(query) ||
                    img.tag.toLowerCase().includes(query)
            );
            return key.toLowerCase().includes(query) || title.includes(query) || matchesImage;
        });
    }, [selectedStack, componentFilter]);

    const totalStats = useMemo(() => {
        const comps = Object.values(selectedStack?.configuration?.components || {});
        const imageCount = comps.reduce((acc, comp) => acc + Object.keys(comp?.images || {}).length, 0);
        return { componentCount: comps.length, imageCount };
    }, [selectedStack]);

    if (loading && stacks.length === 0) {
        return (
            <div className="p-12 flex flex-col items-center justify-center space-y-4">
                <RefreshCcw className="animate-spin text-blue-500" size={32} />
                <p className="text-slate-500 text-base font-medium">Loading available stacks...</p>
            </div>
        );
    }

    return (
        <div className="p-6 md:p-8 space-y-8 w-full stacks-page">
            {/* Header */}
            <div className="flex flex-col gap-2">
                <div className="flex items-center gap-3">
                    <div className="w-12 h-12 bg-blue-600/10 rounded-2xl flex items-center justify-center border border-blue-500/20">
                        <Layers className="text-blue-500" size={24} />
                    </div>
                    <div>
                        <h1 className={cn("text-3xl font-bold tracking-tight", titleColor)}>Stack Registry</h1>
                        <p className={descColor}>Pre-configured, certified version combinations for platform components.</p>
                    </div>
                </div>
            </div>

            {error && (
                <div className="p-4 bg-rose-500/10 border border-rose-500/20 rounded-2xl flex items-center gap-3 text-rose-500">
                    <Info size={20} />
                    <span>Failed to load stacks: {error.message || 'Unknown error'}</span>
                </div>
            )}

            {stacks.length === 0 ? (
                <div className={cn("p-12 text-center rounded-3xl border border-dashed", cardBg)}>
                    <Layers size={48} className="mx-auto text-slate-500 mb-4" />
                    <h3 className={cn("text-lg font-bold mb-2", titleColor)}>No stacks found</h3>
                    <p className={descColor}>There are no certified stacks loaded. Run stack import command in CLI to initialize defaults.</p>
                </div>
            ) : (
                <div className="flex flex-col lg:flex-row gap-8 items-start">
                    {/* Stacks Sidebar */}
                    <div className="space-y-4 w-full lg:w-80 shrink-0 stack-sidebar">
                        <h2 className={cn("text-sm font-bold uppercase tracking-wider px-1", descColor)}>Available Stacks</h2>
                        <div className="space-y-3">
                            {stacks.map((stack) => {
                                const isSelected = selectedStack?.id === stack.id;
                                return (
                                    <div
                                        key={stack.id}
                                        onClick={() => setSelectedStackId(stack.id)}
                                        className={cn(
                                            "p-5 rounded-2xl border transition-all duration-200 cursor-pointer shadow-sm relative overflow-hidden group stack-selector-card",
                                            isSelected
                                                ? "bg-blue-600/10 border-blue-500/30 text-blue-500"
                                                : cn("hover:border-blue-500/20 hover:bg-slate-50/50 dark:hover:bg-slate-800/30", cardBg)
                                        )}
                                    >
                                        <div className="flex justify-between items-start mb-1">
                                            <h3 className={cn("font-bold text-lg", isSelected ? "text-blue-500" : titleColor)}>
                                                {stack.title || stack.name}
                                            </h3>
                                            <span className={cn(
                                                "text-xs px-2.5 py-1 rounded-full font-semibold border",
                                                isSelected
                                                    ? "bg-blue-500/20 border-blue-500/30 text-blue-400"
                                                    : "bg-slate-100 dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400"
                                            )}>
                                                {stack.version}
                                            </span>
                                        </div>
                                        <p className={cn("text-sm mb-2", descColor)}>Identifier: {stack.name}</p>
                                    </div>
                                );
                            })}
                        </div>
                    </div>

                    {/* Stack Details Pane */}
                    {selectedStack && (
                        <div className={cn("flex-1 w-full border rounded-3xl p-6 md:p-8 shadow-sm space-y-6 stack-details-pane", cardBg)}>
                            <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
                                <div>
                                    <div className="flex flex-wrap items-center gap-3 mb-2">
                                        <h2 className={cn("text-2xl font-bold", titleColor)}>
                                            {selectedStack.title || selectedStack.name} Details
                                        </h2>
                                        <span className={cn(
                                            "text-xs px-2.5 py-1 rounded-full font-semibold border",
                                            darkMode
                                                ? "bg-slate-800 border-slate-700 text-slate-300"
                                                : "bg-slate-100 border-slate-200 text-slate-700"
                                        )}>
                                            {totalStats.componentCount} components • {totalStats.imageCount} locked images
                                        </span>
                                    </div>
                                    <p className={descColor}>
                                        Below are the package types, Helm chart versions, and locked image repositories certified under stack version <strong className={titleColor}>{selectedStack.version}</strong>.
                                    </p>
                                </div>

                                <div className="relative w-full md:w-64 shrink-0">
                                    <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                                    <input
                                        type="text"
                                        value={componentFilter}
                                        onChange={(e) => setComponentFilter(e.target.value)}
                                        placeholder="Filter components or images..."
                                        aria-label="Filter components or images"
                                        className={cn(
                                            "w-full pl-9 pr-3 py-2 text-sm rounded-xl border outline-none transition-colors stack-component-filter",
                                            darkMode
                                                ? "bg-slate-950/70 border-slate-800 text-white placeholder-slate-500 focus:border-blue-500/50"
                                                : "bg-slate-50 border-slate-200 text-slate-900 placeholder-slate-400 focus:border-blue-500"
                                        )}
                                    />
                                </div>
                            </div>

                            {/* Components List */}
                            <div className="space-y-4">
                                {componentEntries.length === 0 ? (
                                    <div className={cn("p-8 text-center rounded-2xl border border-dashed", rowBorder)}>
                                        <p className={descColor}>No components match &ldquo;{componentFilter}&rdquo;.</p>
                                    </div>
                                ) : (
                                    componentEntries.map(([key, comp]) => {
                                        const packageType = getPackageType(comp);
                                        const charts = getCharts(comp);
                                        const images = getImages(comp);
                                        const isHelm = packageType === 'helm';

                                        return (
                                            <div
                                                key={key}
                                                className={cn(
                                                    "rounded-2xl border overflow-hidden transition-all hover:shadow-md stack-component-card",
                                                    subBg,
                                                    rowBorder
                                                )}
                                            >
                                                {/* Component Header: Title, Package Type & Helm Chart Metadata */}
                                                <div className={cn(
                                                    "p-4 md:p-5 flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b",
                                                    rowBorder
                                                )}>
                                                    <div className="flex items-center gap-3 min-w-0">
                                                        <div className="w-10 h-10 bg-blue-500/10 rounded-xl flex items-center justify-center shrink-0 border border-blue-500/20">
                                                            <Box className="text-blue-500" size={20} />
                                                        </div>
                                                        <div className="min-w-0">
                                                            <div className="flex flex-wrap items-center gap-2">
                                                                <h4 className={cn("font-bold text-base", titleColor)}>
                                                                    {COMPONENT_TITLES[key] || key}
                                                                </h4>
                                                                <span className={cn(
                                                                    "inline-flex items-center gap-1 text-[11px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md border package-type-badge",
                                                                    isHelm
                                                                        ? "bg-indigo-500/10 text-indigo-400 border-indigo-500/25"
                                                                        : "bg-amber-500/10 text-amber-500 border-amber-500/25"
                                                                )}>
                                                                    {isHelm ? <Package size={12} /> : <FileCode size={12} />}
                                                                    {packageType}
                                                                </span>
                                                            </div>
                                                            <p className={cn("text-xs font-mono mt-0.5", descColor)}>
                                                                {key}
                                                            </p>
                                                        </div>
                                                    </div>

                                                    {/* Helm Chart Info */}
                                                    {isHelm && charts.length > 0 && (
                                                        <div className="flex flex-wrap items-center gap-3 lg:justify-end">
                                                            {charts.map((c) => (
                                                                <div
                                                                    key={c.key}
                                                                    className={cn(
                                                                        "px-3 py-2 rounded-xl border flex flex-wrap items-center gap-x-4 gap-y-1 text-xs helm-chart-info",
                                                                        darkMode
                                                                            ? "bg-slate-900/80 border-slate-800"
                                                                            : "bg-white border-slate-200"
                                                                    )}
                                                                >
                                                                    {charts.length > 1 && (
                                                                        <span className={cn("font-semibold uppercase tracking-wider", descColor)}>
                                                                            {c.key}
                                                                        </span>
                                                                    )}
                                                                    {c.chart && (
                                                                        <div className="flex flex-col">
                                                                            <span className={cn("text-[10px] font-semibold uppercase tracking-wider", descColor)}>
                                                                                Helm Chart
                                                                            </span>
                                                                            <span className={cn("font-mono font-medium", titleColor)}>
                                                                                {c.chart}
                                                                            </span>
                                                                        </div>
                                                                    )}
                                                                    {c.version && (
                                                                        <div className="flex flex-col">
                                                                            <span className={cn("text-[10px] font-semibold uppercase tracking-wider", descColor)}>
                                                                                Helm Version
                                                                            </span>
                                                                            <span className="font-mono font-semibold text-blue-500">
                                                                                {c.version}
                                                                            </span>
                                                                        </div>
                                                                    )}
                                                                    {c.repo && (
                                                                        <div className="flex flex-col max-w-xs">
                                                                            <span className={cn("text-[10px] font-semibold uppercase tracking-wider", descColor)}>
                                                                                Chart Repo
                                                                            </span>
                                                                            <span className={cn("font-mono truncate", descColor)} title={c.repo}>
                                                                                {c.repo}
                                                                            </span>
                                                                        </div>
                                                                    )}
                                                                </div>
                                                            ))}
                                                        </div>
                                                    )}
                                                </div>

                                                {/* Locked Images Table */}
                                                {images.length > 0 && (
                                                    <div className="divide-y divide-slate-200/60 dark:divide-slate-800/60 stack-images-list">
                                                        <div className={cn(
                                                            "hidden sm:grid sm:grid-cols-12 gap-3 px-4 md:px-5 py-2 text-[11px] font-semibold uppercase tracking-wider",
                                                            tableHeaderBg
                                                        )}>
                                                            <div className="sm:col-span-3">Image Role</div>
                                                            <div className="sm:col-span-6">Locked Image Repository</div>
                                                            <div className="sm:col-span-3 sm:text-right">Locked Version</div>
                                                        </div>
                                                        {images.map((img) => (
                                                            <div
                                                                key={img.key}
                                                                className="grid grid-cols-1 sm:grid-cols-12 gap-2 sm:gap-3 px-4 md:px-5 py-3 items-center stack-image-row"
                                                            >
                                                                <div className="sm:col-span-3 flex items-center gap-2">
                                                                    <span className={cn(
                                                                        "text-xs font-mono font-semibold px-2 py-0.5 rounded-md border",
                                                                        img.key === 'main'
                                                                            ? "bg-blue-500/10 text-blue-500 border-blue-500/25"
                                                                            : darkMode
                                                                                ? "bg-slate-800/80 text-slate-300 border-slate-700"
                                                                                : "bg-slate-100 text-slate-700 border-slate-200"
                                                                    )}>
                                                                        {img.key}
                                                                    </span>
                                                                </div>
                                                                <div className="sm:col-span-6 min-w-0">
                                                                    <span className={cn("text-sm font-mono break-all", titleColor)} title={img.repository}>
                                                                        {img.repository || 'N/A'}
                                                                    </span>
                                                                </div>
                                                                <div className="sm:col-span-3 flex items-center gap-1.5 sm:justify-end">
                                                                    <Tag size={12} className="text-blue-500 shrink-0" />
                                                                    <span className={cn("text-sm font-semibold font-mono", titleColor)}>
                                                                        {img.tag || 'N/A'}
                                                                    </span>
                                                                </div>
                                                            </div>
                                                        ))}
                                                    </div>
                                                )}
                                            </div>
                                        );
                                    })
                                )}
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};

export default StacksPage;
