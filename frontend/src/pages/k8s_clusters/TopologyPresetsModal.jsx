import React, { useState, useEffect, useRef } from 'react';
import { Plus, Trash2, Layers } from 'lucide-react';
import Modal from '../../components/Modal';

const DEFAULT_ROLES = [
    'ingest',
    'queue',
    'compute',
    'database',
    'warehouse',
    'application',
];

const TopologyPresetsModal = ({
    isOpen,
    onClose,
    topologyData,
    onSave,
}) => {
    const [presets, setPresets] = useState([]);
    const [regionInput, setRegionInput] = useState('');
    const [zoneInput, setZoneInput] = useState('');
    const [rackInput, setRackInput] = useState('');
    const [roles, setRoles] = useState([]);
    const [newRoleInput, setNewRoleInput] = useState('');
    const [saving, setSaving] = useState(false);
    const wasOpenRef = useRef(false);

    useEffect(() => {
        if (isOpen && !wasOpenRef.current) {
            setPresets(Array.isArray(topologyData?.presets) ? topologyData.presets : []);
            setRoles(
                Array.isArray(topologyData?.roles) && topologyData.roles.length > 0
                    ? topologyData.roles
                    : DEFAULT_ROLES
            );
            setRegionInput('');
            setZoneInput('');
            setRackInput('');
            setNewRoleInput('');
        }
        wasOpenRef.current = isOpen;
    }, [isOpen, topologyData]);

    const handleAddPreset = () => {
        const entry = {};
        if (regionInput.trim()) entry.region = regionInput.trim();
        if (zoneInput.trim()) entry.zone = zoneInput.trim();
        if (rackInput.trim()) entry.rack = rackInput.trim();
        if (Object.keys(entry).length === 0) return;

        const exists = presets.some(
            (p) =>
                (p.region || '') === (entry.region || '') &&
                (p.zone || '') === (entry.zone || '') &&
                (p.rack || '') === (entry.rack || '')
        );
        if (!exists) {
            setPresets((prev) => [...prev, entry]);
        }
        setRegionInput('');
        setZoneInput('');
        setRackInput('');
    };

    const handleRemovePreset = (idx) => {
        setPresets((prev) => prev.filter((_, i) => i !== idx));
    };

    const handleAddRolePreset = () => {
        const r = newRoleInput.trim();
        if (!r || roles.includes(r)) return;
        setRoles((prev) => [...prev, r]);
        setNewRoleInput('');
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setSaving(true);
        try {
            await onSave({ presets, roles });
            onClose();
        } finally {
            setSaving(false);
        }
    };

    return (
        <Modal
            isOpen={isOpen}
            onClose={onClose}
            title="Topology & Role Presets"
            size="lg"
        >
            <form id="topology-presets-form" onSubmit={handleSubmit} className="space-y-6">
                {/* Fixed Region / Zone / Rack Combinations */}
                <div className="space-y-3 p-4 rounded-xl bg-slate-50 dark:bg-slate-900/60 border border-slate-200/70 dark:border-slate-800">
                    <div className="flex items-center gap-2">
                        <Layers size={16} className="text-indigo-500" />
                        <h4 className="text-sm font-bold uppercase tracking-wider text-slate-700 dark:text-slate-200">
                            Hierarchy Combinations (Region / Zone / Rack)
                        </h4>
                    </div>
                    <p className="text-xs text-slate-500">
                        Define valid Region / Zone / Rack combinations. Rack supports slash-delimited hierarchy (e.g. <span className="font-mono">dc1/row-a/rack-01</span>).
                    </p>

                    <div className="space-y-2 max-h-52 overflow-y-auto">
                        {presets.length === 0 ? (
                            <p className="text-xs text-slate-400">No hierarchy presets defined yet.</p>
                        ) : (
                            presets.map((p, idx) => (
                                <div
                                    key={`${p.region || ''}-${p.zone || ''}-${p.rack || ''}-${idx}`}
                                    className="flex items-center justify-between gap-2 px-3 py-2 rounded-lg bg-white/70 dark:bg-slate-950/50 border border-slate-200/60 dark:border-slate-800 text-xs font-mono"
                                >
                                    <div className="flex flex-wrap items-center gap-2">
                                        {p.region && (
                                            <span className="px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
                                                region:{p.region}
                                            </span>
                                        )}
                                        {p.zone && (
                                            <span className="px-2 py-0.5 rounded bg-blue-500/10 text-blue-600 dark:text-blue-400">
                                                zone:{p.zone}
                                            </span>
                                        )}
                                        {p.rack && (
                                            <span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                                                rack:{p.rack}
                                            </span>
                                        )}
                                    </div>
                                    <button
                                        type="button"
                                        onClick={() => handleRemovePreset(idx)}
                                        className="p-1 text-slate-400 hover:text-red-500"
                                        title="Remove combination"
                                    >
                                        <Trash2 size={14} />
                                    </button>
                                </div>
                            ))
                        )}
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-4 gap-2 pt-2 border-t border-slate-200/60 dark:border-slate-800">
                        <input
                            id="preset-region-input"
                            type="text"
                            value={regionInput}
                            onChange={(e) => setRegionInput(e.target.value)}
                            placeholder="Region (e.g. regionA)"
                            className="dxc-input text-xs font-mono"
                        />
                        <input
                            id="preset-zone-input"
                            type="text"
                            value={zoneInput}
                            onChange={(e) => setZoneInput(e.target.value)}
                            placeholder="Zone (e.g. zoneA)"
                            className="dxc-input text-xs font-mono"
                        />
                        <input
                            id="preset-rack-input"
                            type="text"
                            value={rackInput}
                            onChange={(e) => setRackInput(e.target.value)}
                            placeholder="Rack (e.g. dc1/row-a/rack1)"
                            className="dxc-input text-xs font-mono"
                        />
                        <button
                            id="add-topology-preset-btn"
                            type="button"
                            onClick={handleAddPreset}
                            className="dxc-btn-secondary px-3 py-2 text-xs flex items-center justify-center gap-1"
                        >
                            <Plus size={14} /> ADD
                        </button>
                    </div>
                </div>

                {/* User-Defined Role Presets */}
                <div className="space-y-3 p-4 rounded-xl bg-slate-50 dark:bg-slate-900/60 border border-slate-200/70 dark:border-slate-800">
                    <h4 className="text-sm font-bold uppercase tracking-wider text-slate-700 dark:text-slate-200">
                        User-Defined Role Presets
                    </h4>
                    <div className="flex flex-wrap gap-2">
                        {roles.map((r) => (
                            <span
                                key={r}
                                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold bg-blue-500/10 border border-blue-500/20 text-blue-600 dark:text-blue-400"
                            >
                                {r}
                                <button
                                    type="button"
                                    onClick={() => setRoles((prev) => prev.filter((item) => item !== r))}
                                    className="hover:text-red-500"
                                >
                                    ×
                                </button>
                            </span>
                        ))}
                    </div>
                    <div className="flex gap-2">
                        <input
                            id="new-role-preset-input"
                            type="text"
                            value={newRoleInput}
                            onChange={(e) => setNewRoleInput(e.target.value)}
                            onKeyDown={(e) => {
                                if (e.key === 'Enter') {
                                    e.preventDefault();
                                    handleAddRolePreset();
                                }
                            }}
                            placeholder="Add role preset (e.g. storage, ai-worker)"
                            className="dxc-input flex-1 text-xs"
                        />
                        <button
                            type="button"
                            onClick={handleAddRolePreset}
                            className="dxc-btn-secondary px-3 py-2 text-xs flex items-center gap-1"
                        >
                            <Plus size={14} /> ADD PRESET
                        </button>
                    </div>
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
                        id="save-topology-presets-btn"
                        type="submit"
                        disabled={saving}
                        className="dxc-btn-primary px-5 py-2 text-xs disabled:opacity-60"
                    >
                        {saving ? 'SAVING...' : 'SAVE PRESETS'}
                    </button>
                </div>
            </form>
        </Modal>
    );
};

export default TopologyPresetsModal;
