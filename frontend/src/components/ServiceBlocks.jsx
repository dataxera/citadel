// SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
// SPDX-License-Identifier: AGPLv3+

import React, { useState } from 'react';
import { Server, Lock, Eye, EyeOff, Copy, AlertCircle, ExternalLink, ChevronDown } from 'lucide-react';
import { cn } from '../utils/cn';

/**
 * Renders a string containing simple <strong>...</strong> tags safely as React elements without dangerouslySetInnerHTML.
 */
const renderSafeGuideText = (text) => {
    if (typeof text !== 'string') return text;
    const parts = text.split(/(<strong>.*?<\/strong>)/g);
    return parts.map((part, idx) => {
        if (part.startsWith('<strong>') && part.endsWith('</strong>')) {
            return <strong key={idx} className="font-semibold text-slate-700 dark:text-slate-200">{part.slice(8, -9)}</strong>;
        }
        return part;
    });
};

/**
 * Renders a titled section panel for service connection details.
 */
export const ServiceBlock = ({ darkMode, icon, iconColorClass = "text-emerald-500", iconBgClass = "bg-emerald-500/10", title, headerRight, children }) => {
    const IconComponent = icon;
    return (
        <div className="dxc-panel">
            <div className={cn("p-4 border-b flex items-center justify-between gap-4 flex-wrap", darkMode ? 'border-slate-800 bg-slate-950/30' : 'border-slate-200 bg-slate-50')}>
                <div className="flex items-center gap-3">
                    <div className={cn("p-2 rounded-lg", iconBgClass, iconColorClass)}><IconComponent size={18} /></div>
                    <h4 className="text-base font-bold tracking-wider leading-none text-slate-900 dark:text-white">{title}</h4>
                </div>
                {headerRight && (
                    <div className="flex items-center gap-2">
                        {headerRight}
                    </div>
                )}
            </div>
            <div className="p-6">
                {children}
            </div>
        </div>
    );
};

export const EndpointCard = ({ title, subtitle, code, description, copyValue, codeClassName = "text-emerald-600 dark:text-emerald-400" }) => (
    <div className="p-5 border rounded-2xl bg-slate-50 border-slate-200 dark:bg-slate-950/50 dark:border-slate-800 flex flex-col group/item relative h-full">
        <div className="flex items-center justify-between mb-2">
            <div>
                {subtitle && <p className="text-xs text-slate-500 font-bold uppercase tracking-widest leading-none mb-1">{subtitle}</p>}
                <h5 className="text-lg font-bold text-slate-900 dark:text-white leading-none">{title}</h5>
            </div>
        </div>
        <div className="mt-2 p-2 rounded bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 flex items-center justify-between">
            <code className={cn("text-xs font-mono truncate px-1", codeClassName)}>
                {code}
            </code>
            <button
                onClick={() => navigator.clipboard.writeText(copyValue || code)}
                className="p-1 text-slate-400 hover:text-emerald-500 transition-colors shrink-0"
                title="Copy endpoint"
            >
                <Copy size={14} />
            </button>
        </div>
        {description && (
            <p className="mt-4 text-xs text-slate-500 leading-relaxed">{description}</p>
        )}
    </div>
);

export const InternalNetworkAccessBlock = ({ darkMode, endpoints, icon = Server, iconColorClass = "text-emerald-500", iconBgClass = "bg-emerald-500/10" }) => (
    <ServiceBlock darkMode={darkMode} icon={icon} iconColorClass={iconColorClass} iconBgClass={iconBgClass} title="Internal Network Access">
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
            {endpoints.map((eps, i) => (
                <div key={i}>
                    <EndpointCard 
                        title={eps.title} 
                        subtitle={eps.subtitle}
                        code={eps.code} 
                        description={eps.description} 
                        copyValue={eps.copyValue} 
                        codeClassName={eps.codeClassName}
                    />
                </div>
            ))}
        </div>
    </ServiceBlock>
);

/**
 * Renders a single external endpoint row with optional external link and copy-to-clipboard action.
 */
const ExternalEndpointRow = ({ epValue, scheme }) => (
    <div className="mt-2 p-2 rounded bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 flex items-center justify-between gap-2 external-endpoint-row">
        {scheme ? (
            <a
                href={epValue}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs font-mono text-emerald-600 dark:text-emerald-400 hover:text-emerald-700 dark:hover:text-emerald-300 truncate px-1 text-left hover:underline flex-1 min-w-0 external-endpoint-link"
                title="Open URL"
            >
                {epValue}
            </a>
        ) : (
            <code className="text-xs font-mono text-emerald-600 dark:text-emerald-400 truncate px-1 text-left flex-1 min-w-0 external-endpoint-code">
                {epValue}
            </code>
        )}
        <div className="flex items-center gap-1 shrink-0">
            {scheme && (
                <a
                    href={epValue}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="p-1 text-slate-400 hover:text-emerald-500 transition-colors shrink-0 external-endpoint-open-btn"
                    title="Open in new tab"
                >
                    <ExternalLink size={14} />
                </a>
            )}
            <button
                onClick={() => navigator.clipboard.writeText(epValue)}
                className="p-1 text-slate-400 hover:text-emerald-500 transition-colors shrink-0 external-endpoint-copy-btn"
                title="Copy endpoint"
            >
                <Copy size={14} />
            </button>
        </div>
    </div>
);

/**
 * Renders the External Network Access block with a cluster node hostname selector and compact endpoint cards.
 */
export const ExternalNetworkAccessBlock = ({ 
    darkMode, 
    ports, 
    clusterNodes, 
    cliInfo, 
    guideTitle = "External Connection Guide", 
    guideText,
    isIngressUsed = false,
    cliLanguage = "bash",
    cliTitle = "CLI Example",
    icon = Server,
    iconColorClass = "text-indigo-500",
    iconBgClass = "bg-indigo-500/10"
}) => {
    const [selectedNodeIdx, setSelectedNodeIdx] = useState(0);
    const nodes = (clusterNodes || []).filter(n => n && n.hostname);
    const safeNodeIdx = selectedNodeIdx < nodes.length ? selectedNodeIdx : 0;
    const selectedNode = nodes[safeNodeIdx] || null;

    const hasNodePort = (ports || []).some(np => np.load_balancer_ips === undefined && !np.url);
    const effectiveGuideText = guideText !== undefined
        ? guideText
        : (hasNodePort && !isIngressUsed
            ? "Use any of the <strong>Node Hostname:Port</strong> combinations listed above to connect from outside the cluster."
            : null);

    const nodeSelector = hasNodePort && nodes.length > 0 ? (
        <div className="flex items-center gap-2 external-access-node-selector" id="external-access-node-selector">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                Node ({nodes.length})
            </span>
            <div className="relative flex items-center">
                <Server size={13} className="absolute left-2.5 text-indigo-500 pointer-events-none" />
                <select
                    id="external-access-node-select"
                    aria-label="Select cluster node hostname"
                    value={safeNodeIdx}
                    onChange={(e) => setSelectedNodeIdx(Number(e.target.value))}
                    className={cn(
                        "pl-8 pr-7 py-1.5 rounded-lg text-xs font-mono font-semibold border appearance-none cursor-pointer transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500/40",
                        darkMode
                            ? "bg-slate-900 border-slate-700 text-slate-200 hover:border-slate-600"
                            : "bg-white border-slate-200 text-slate-700 hover:border-slate-300"
                    )}
                >
                    {nodes.map((node, idx) => (
                        <option key={node.hostname || idx} value={idx}>
                            {node.hostname}
                        </option>
                    ))}
                </select>
                <ChevronDown size={13} className="absolute right-2 text-slate-400 pointer-events-none" />
            </div>
        </div>
    ) : null;

    const resolvedCliCommand = cliInfo
        ? (typeof cliInfo.command === 'function' ? cliInfo.command(selectedNode) : cliInfo.command)
        : '';

    return (
        <ServiceBlock
            darkMode={darkMode}
            icon={icon}
            iconColorClass={iconColorClass}
            iconBgClass={iconBgClass}
            title="External Network Access"
            headerRight={nodeSelector}
        >
            <div className="space-y-8">
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
                    {ports.map((np, i) => {
                        const isLoadBalancer = np.load_balancer_ips !== undefined || Boolean(np.url);
                        const lbTargets = np.load_balancer_ips !== undefined
                            ? np.load_balancer_ips
                            : (np.url ? [np.url] : []);

                        return (
                            <div key={i} className="p-5 border rounded-2xl bg-slate-50 border-slate-200 dark:bg-slate-950/50 dark:border-slate-800 flex flex-col justify-between h-full external-port-card">
                                <div className="flex items-center justify-between gap-2 mb-2">
                                    <div className="min-w-0">
                                        <p className="text-xs text-slate-500 font-bold uppercase tracking-widest leading-none mb-1">Service Type</p>
                                        <h5 className="text-lg font-bold text-slate-900 dark:text-white leading-none truncate">{np.label}</h5>
                                    </div>
                                    <div className="px-2 py-1 rounded text-[10px] font-bold bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border border-indigo-500/20 uppercase tracking-tighter shrink-0">
                                        {isLoadBalancer ? `LoadBalancer: ${np.port}` : `NodePort: ${np.node_port}`}
                                    </div>
                                </div>

                                <div>
                                    {isLoadBalancer ? (
                                        lbTargets.length === 0 ? (
                                            <div className="mt-2 p-2.5 rounded bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-xs text-slate-500 italic">
                                                Pending LoadBalancer Hostname...
                                            </div>
                                        ) : (
                                            lbTargets.map((target, j) => {
                                                const isFullUrl = target.startsWith('http://') || target.startsWith('https://');
                                                const epValue = isFullUrl
                                                    ? target
                                                    : (np.scheme ? `${np.scheme}://${target}:${np.port}` : `${target}:${np.port}`);
                                                return (
                                                    <ExternalEndpointRow key={j} epValue={epValue} scheme={np.scheme} />
                                                );
                                            })
                                        )
                                    ) : (
                                        !selectedNode ? (
                                            <div className="mt-2 p-2.5 rounded bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-xs text-slate-500 italic">
                                                Pending cluster node...
                                            </div>
                                        ) : (
                                            <ExternalEndpointRow
                                                epValue={np.scheme ? `${np.scheme}://${selectedNode.hostname}:${np.node_port}` : `${selectedNode.hostname}:${np.node_port}`}
                                                scheme={np.scheme}
                                            />
                                        )
                                    )}
                                </div>
                            </div>
                        );
                    })}
                </div>

                {(effectiveGuideText || cliInfo) && (
                    <div className="space-y-4">
                        {effectiveGuideText && (
                            <div className="flex items-start gap-4 p-4 rounded-xl bg-blue-500/5 border border-blue-500/10">
                                <AlertCircle className="text-blue-500 shrink-0 mt-0.5" size={20} />
                                <div>
                                    <p className="text-sm font-bold text-slate-900 dark:text-white tracking-tight">{guideTitle}</p>
                                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1 leading-relaxed">
                                        {renderSafeGuideText(effectiveGuideText)}
                                    </p>
                                </div>
                            </div>
                        )}

                        {cliInfo && (
                            <div className={cn(
                                "flex flex-col rounded-2xl border overflow-hidden",
                                darkMode ? 'bg-slate-950/80 border-slate-800' : 'bg-slate-900 border-slate-700'
                            )}>
                                <div className={cn("flex border-b p-1 items-center justify-between", darkMode ? 'border-slate-800' : 'border-slate-700')}>
                                    <div className="flex p-1 gap-1">
                                        <button className="px-4 py-1.5 text-xs font-bold uppercase rounded-lg bg-slate-700 text-white shadow-inner">{cliLanguage}</button>
                                        {cliInfo.languageButtons && cliInfo.languageButtons.map((btn, i) => (
                                            <button key={i} className="px-4 py-1.5 text-xs font-bold uppercase rounded-lg text-slate-500 hover:text-slate-300">{btn}</button>
                                        ))}
                                    </div>
                                    <div className="px-4 text-[10px] font-bold text-slate-500 uppercase tracking-widest">{cliTitle}</div>
                                </div>
                                <div className="p-6 relative group">
                                    <pre className="text-sm font-mono text-blue-400 leading-relaxed overflow-x-auto whitespace-pre-wrap">
                                        {resolvedCliCommand}
                                    </pre>
                                    <button
                                        onClick={() => navigator.clipboard.writeText(cliInfo.copyValue || resolvedCliCommand)}
                                        className="absolute top-4 right-4 p-2 text-slate-500 hover:text-white opacity-0 group-hover:opacity-100 transition-all"
                                    >
                                        <Copy size={16} />
                                    </button>
                                </div>
                            </div>
                        )}
                    </div>
                )}
            </div>
        </ServiceBlock>
    );
};



export const CredentialField = ({ label, value, isMasked }) => {
    const [showPassword, setShowPassword] = useState(false);
    
    return (
        <div className="p-3 border rounded-xl group relative bg-slate-50 border-slate-200 dark:bg-slate-950/50 dark:border-slate-800 h-full">
            <p className="text-[10px] text-slate-500 font-bold uppercase tracking-widest mb-1">{label}</p>
            <div className="flex items-center justify-between">
                <span className={cn("text-sm font-mono truncate pr-4", isMasked && !showPassword ? "text-slate-500" : "text-slate-700 dark:text-slate-200")}>
                    {isMasked ? (showPassword ? (value || "pending") : "••••••••••••••••") : (value || 'pending')}
                </span>
                <div className="flex items-center gap-2">
                    {isMasked && (
                        <button onClick={() => setShowPassword(!showPassword)} className="text-slate-400 hover:text-slate-600 transition-colors">
                            {showPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                        </button>
                    )}
                    <button onClick={() => navigator.clipboard.writeText(value || "")} className={cn("text-slate-400 hover:text-blue-500 transition-colors", isMasked ? "" : "opacity-0 group-hover:opacity-100")}><Copy size={14} /></button>
                </div>
            </div>
        </div>
    );
};

export const CredentialBlock = ({ darkMode, credentials, caCert }) => (
    <ServiceBlock darkMode={darkMode} icon={Lock} iconColorClass="text-blue-400" iconBgClass="bg-blue-500/10" title="Cluster Credentials">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {credentials.map((cred, i) => (
                <div key={i}>
                    <CredentialField label={cred.label} value={cred.value} isMasked={cred.isMasked} />
                </div>
            ))}
        </div>

        {caCert && (
            <div className="mt-6 animate-in slide-in-from-top-2 duration-300">
                <div className="p-4 border rounded-xl bg-slate-50 border-slate-200 dark:bg-slate-950/50 dark:border-slate-800">
                    <div className="flex items-center justify-between mb-2">
                        <p className="text-[10px] text-slate-500 font-bold uppercase tracking-widest">CA Certificate</p>
                        <button
                            onClick={() => navigator.clipboard.writeText(caCert)}
                            className="text-xs font-bold text-blue-500 hover:text-blue-400 flex items-center gap-1.5 transition-colors"
                        >
                            <Copy size={12} /> COPY CERTIFICATE
                        </button>
                    </div>
                    <div className="bg-slate-900 rounded-lg p-3 relative group text-emerald-400/90">
                        <pre className="text-[10px] font-mono leading-tight overflow-x-auto max-h-[120px] scrollbar-thin scrollbar-thumb-slate-700 whitespace-pre-wrap">
                            {caCert}
                        </pre>
                    </div>
                </div>
            </div>
        )}
    </ServiceBlock>
);
