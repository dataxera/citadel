import React, { useMemo } from 'react';
import { Server, Cpu, SlidersHorizontal, Globe, MapPin, HardDrive } from 'lucide-react';

const NodeHierarchyCard = ({ node, onConfigureNode }) => {
    const isReady = node.status === 'Ready';
    return (
        <div
            id={`hierarchy-node-card-${node.hostname}`}
            className="p-3 rounded-xl bg-white dark:bg-slate-950/70 border border-slate-200/80 dark:border-slate-800 space-y-2 hover:border-indigo-500/40 transition-colors"
        >
            <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                    <div className="flex items-center gap-2">
                        <span
                            className={`w-2 h-2 rounded-full shrink-0 ${isReady ? 'bg-green-500' : 'bg-red-500'}`}
                            title={node.status || 'Unknown'}
                        />
                        <span className="font-semibold text-sm text-slate-900 dark:text-white truncate">
                            {node.hostname}
                        </span>
                    </div>
                    <div className="text-[11px] font-mono text-slate-400 pl-4">
                        {node.ip || '—'}
                    </div>
                </div>
                {onConfigureNode && (
                    <button
                        type="button"
                        onClick={() => onConfigureNode(node)}
                        className="p-1.5 rounded-lg text-slate-400 hover:text-indigo-500 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors shrink-0"
                        title="Configure Node Labels, Roles & GPU"
                    >
                        <SlidersHorizontal size={13} />
                    </button>
                )}
            </div>

            <div className="flex flex-wrap gap-1">
                {Array.isArray(node.roles) && node.roles.map((role) => (
                    <span
                        key={role}
                        className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-slate-200/70 dark:bg-slate-800 text-slate-700 dark:text-slate-300"
                    >
                        {role}
                    </span>
                ))}
                {node.gpu_vendor && (
                    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-500/10 border border-emerald-500/20 text-emerald-500 uppercase">
                        <Cpu size={10} />
                        {node.gpu_count > 0 ? `${node.gpu_count}x ` : ''}{node.gpu_vendor}
                    </span>
                )}
            </div>

            {(typeof node.cpu_total === 'number' || typeof node.ram_total === 'number') && (
                <div className="grid grid-cols-2 gap-2 pt-1 border-t border-slate-200/50 dark:border-slate-800/70 text-[11px] text-slate-500 tabular-nums">
                    <div>
                        CPU: <span className="font-semibold text-slate-700 dark:text-slate-300">
                            {(node.cpu_requested || 0).toFixed(1)}/{(node.cpu_total || 0).toFixed(0)}
                        </span>
                    </div>
                    <div>
                        RAM: <span className="font-semibold text-slate-700 dark:text-slate-300">
                            {(node.ram_requested || 0).toFixed(1)}/{(node.ram_total || 0).toFixed(0)}G
                        </span>
                    </div>
                </div>
            )}
        </div>
    );
};

const NodeHierarchyView = ({ nodes = [], assignments = {}, onConfigureNode }) => {
    const { regions, unassigned } = useMemo(() => {
        const regionMap = new Map();
        const unassignedNodes = [];

        nodes.forEach((node) => {
            const topo = assignments[node.hostname] || node.topology || {};
            const region = topo.region || '';
            const zone = topo.zone || '';
            const rack = topo.rack || '';

            if (!region && !zone && !rack) {
                unassignedNodes.push(node);
                return;
            }

            const rKey = region || 'Unassigned Region';
            const zKey = zone || 'Unassigned Zone';
            const kKey = rack || 'Unassigned Rack';

            if (!regionMap.has(rKey)) regionMap.set(rKey, new Map());
            const zoneMap = regionMap.get(rKey);
            if (!zoneMap.has(zKey)) zoneMap.set(zKey, new Map());
            const rackMap = zoneMap.get(zKey);
            if (!rackMap.has(kKey)) rackMap.set(kKey, []);
            rackMap.get(kKey).push(node);
        });

        const sortedRegions = Array.from(regionMap.entries())
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([regionName, zoneMap]) => ({
                name: regionName,
                zones: Array.from(zoneMap.entries())
                    .sort(([a], [b]) => a.localeCompare(b))
                    .map(([zoneName, rackMap]) => ({
                        name: zoneName,
                        racks: Array.from(rackMap.entries())
                            .sort(([a], [b]) => a.localeCompare(b))
                            .map(([rackName, rackNodes]) => ({
                                name: rackName,
                                nodes: rackNodes,
                            })),
                    })),
            }));

        return { regions: sortedRegions, unassigned: unassignedNodes };
    }, [nodes, assignments]);

    if (nodes.length === 0) {
        return <p className="text-sm text-slate-500">No nodes reported.</p>;
    }

    return (
        <div id="node-hierarchy-tree" className="space-y-4">
            {regions.map((region) => (
                <div
                    key={region.name}
                    className="p-4 rounded-xl bg-white/50 dark:bg-slate-950/30 border border-slate-200/70 dark:border-slate-800 space-y-3"
                >
                    <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-indigo-500">
                        <Globe size={14} />
                        <span>Region: {region.name}</span>
                    </div>

                    <div className="space-y-3 pl-4 border-l-2 border-indigo-500/20">
                        {region.zones.map((zone) => (
                            <div key={zone.name} className="space-y-2.5">
                                <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-blue-500">
                                    <MapPin size={13} />
                                    <span>Zone: {zone.name}</span>
                                </div>

                                <div className="space-y-2.5 pl-4 border-l-2 border-blue-500/20">
                                    {zone.racks.map((rack) => (
                                        <div key={rack.name} className="space-y-2">
                                            <div className="flex items-center gap-2 text-xs font-mono font-semibold text-emerald-600 dark:text-emerald-400">
                                                <HardDrive size={13} />
                                                <span>
                                                    Rack: {rack.name.includes('/')
                                                        ? rack.name.split('/').join(' › ')
                                                        : rack.name}
                                                </span>
                                                <span className="text-[11px] font-sans text-slate-400">
                                                    ({rack.nodes.length})
                                                </span>
                                            </div>

                                            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5 pl-4 border-l-2 border-emerald-500/20">
                                                {rack.nodes.map((node) => (
                                                    <NodeHierarchyCard
                                                        key={node.hostname}
                                                        node={node}
                                                        onConfigureNode={onConfigureNode}
                                                    />
                                                ))}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            ))}

            {unassigned.length > 0 && (
                <div className="p-4 rounded-xl bg-slate-100/60 dark:bg-slate-900/40 border border-dashed border-slate-300 dark:border-slate-700 space-y-3">
                    <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400">
                        <Server size={14} />
                        <span>Unassigned Nodes ({unassigned.length})</span>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
                        {unassigned.map((node) => (
                            <NodeHierarchyCard
                                key={node.hostname}
                                node={node}
                                onConfigureNode={onConfigureNode}
                            />
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
};

export default NodeHierarchyView;
