import React, { useState, useEffect, useMemo, useRef } from 'react';
import { Server, Layers } from 'lucide-react';
import Modal from '../../components/Modal';

const formatPresetLabel = (p) => {
    const parts = [];
    if (p.region) parts.push(`region: ${p.region}`);
    if (p.zone) parts.push(`zone: ${p.zone}`);
    if (p.rack) parts.push(`rack: ${p.rack}`);
    return parts.join('  /  ');
};

const serializePreset = (p) =>
    JSON.stringify({
        region: p?.region || '',
        zone: p?.zone || '',
        rack: p?.rack || '',
    });

const RackTopologyModal = ({
    isOpen,
    onClose,
    topologyData,
    nodes = [],
    onSave,
    onOpenPresets,
}) => {
    const [selectedByHost, setSelectedByHost] = useState({});
    const [saving, setSaving] = useState(false);
    const wasOpenRef = useRef(false);

    const presets = useMemo(
        () => (Array.isArray(topologyData?.presets) ? topologyData.presets : []),
        [topologyData]
    );

    const presetOptions = useMemo(
        () =>
            presets.map((p) => ({
                key: serializePreset(p),
                label: formatPresetLabel(p),
                value: p,
            })),
        [presets]
    );

    useEffect(() => {
        if (isOpen && !wasOpenRef.current) {
            const initial = {};
            nodes.forEach((n) => {
                const existing = topologyData?.assignments?.[n.hostname] || n.topology || {};
                const serialized = serializePreset(existing);
                const hasAny = Boolean(existing.region || existing.zone || existing.rack);
                initial[n.hostname] = hasAny ? serialized : '';
            });
            setSelectedByHost(initial);
        }
        wasOpenRef.current = isOpen;
    }, [isOpen, topologyData, nodes]);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setSaving(true);
        try {
            const assignments = {};
            Object.entries(selectedByHost).forEach(([host, serialized]) => {
                if (!serialized) {
                    assignments[host] = { region: null, zone: null, rack: null };
                } else {
                    const parsed = JSON.parse(serialized);
                    assignments[host] = {
                        region: parsed.region || null,
                        zone: parsed.zone || null,
                        rack: parsed.rack || null,
                    };
                }
            });
            await onSave({ assignments });
            onClose();
        } finally {
            setSaving(false);
        }
    };

    return (
        <Modal
            isOpen={isOpen}
            onClose={onClose}
            title="Node Hierarchy Assignment"
            size="lg"
        >
            <form id="rack-topology-form" onSubmit={handleSubmit} className="space-y-6">
                {presetOptions.length === 0 ? (
                    <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-600 dark:text-amber-400 text-xs flex items-center justify-between gap-4">
                        <span>
                            No topology hierarchy presets configured yet. Define Region / Zone / Rack combinations in Topology Presets first.
                        </span>
                        {onOpenPresets && (
                            <button
                                type="button"
                                onClick={() => {
                                    onClose();
                                    onOpenPresets();
                                }}
                                className="dxc-btn-secondary px-3 py-1.5 text-xs whitespace-nowrap flex items-center gap-1.5"
                            >
                                <Layers size={13} />
                                OPEN PRESETS
                            </button>
                        )}
                    </div>
                ) : null}

                <div className="space-y-3 p-4 rounded-xl bg-slate-50 dark:bg-slate-900/60 border border-slate-200/70 dark:border-slate-800">
                    <h4 className="text-sm font-bold uppercase tracking-wider text-slate-700 dark:text-slate-200">
                        Assign Nodes to Available Hierarchy
                    </h4>
                    {nodes.length === 0 ? (
                        <p className="text-xs text-slate-500">No nodes discovered in this cluster yet.</p>
                    ) : (
                        <div className="overflow-x-auto max-h-72">
                            <table className="w-full text-left border-collapse">
                                <thead>
                                    <tr className="border-b border-slate-200/70 dark:border-slate-800 text-[11px] font-bold uppercase tracking-wider text-slate-400">
                                        <th className="py-2 pr-3">Node</th>
                                        <th className="py-2 pl-2">Region / Zone / Rack</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-200/50 dark:divide-slate-800/60 text-xs">
                                    {nodes.map((node) => {
                                        const currentVal = selectedByHost[node.hostname] || '';
                                        const isLegacyOrCustom =
                                            currentVal &&
                                            !presetOptions.some((opt) => opt.key === currentVal);

                                        return (
                                            <tr key={node.hostname}>
                                                <td className="py-2.5 pr-3 font-semibold text-slate-800 dark:text-slate-200 whitespace-nowrap">
                                                    <div className="flex items-center gap-1.5">
                                                        <Server size={13} className="text-slate-400" />
                                                        {node.hostname}
                                                    </div>
                                                </td>
                                                <td className="py-2.5 pl-2">
                                                    <select
                                                        id={`assign-node-topology-${node.hostname}`}
                                                        value={currentVal}
                                                        onChange={(e) =>
                                                            setSelectedByHost((prev) => ({
                                                                ...prev,
                                                                [node.hostname]: e.target.value,
                                                            }))
                                                        }
                                                        className="dxc-input w-full text-xs font-mono"
                                                    >
                                                        <option value="">— Unassigned —</option>
                                                        {isLegacyOrCustom && (
                                                            <option value={currentVal} disabled>
                                                                {formatPresetLabel(JSON.parse(currentVal))} (not in presets)
                                                            </option>
                                                        )}
                                                        {presetOptions.map((opt) => (
                                                            <option key={opt.key} value={opt.key}>
                                                                {opt.label}
                                                            </option>
                                                        ))}
                                                    </select>
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>

                <div className="flex justify-end gap-3 pt-2">
                    <button
                        type="button"
                        onClick={onClose}
                        className="dxc-btn-secondary px-5 py-2 text-xs"
                    >
                        CANCEL
                    </button>
                    <button
                        id="save-rack-topology-btn"
                        type="submit"
                        disabled={saving}
                        className="dxc-btn-primary px-5 py-2 text-xs disabled:opacity-60"
                    >
                        {saving ? 'APPLYING...' : 'APPLY TOPOLOGY'}
                    </button>
                </div>
            </form>
        </Modal>
    );
};

export default RackTopologyModal;
