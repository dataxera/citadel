import React, { useState, useEffect } from 'react';
import { Plus, Trash2, Lock, Cpu, Tag, Shield } from 'lucide-react';
import Modal from '../../components/Modal';

const PROTECTED_LABELS = new Set([
    'kubernetes.io/hostname',
    'kubernetes.io/os',
    'kubernetes.io/arch',
    'beta.kubernetes.io/os',
    'beta.kubernetes.io/arch',
]);
const isProtectedLabel = (key) => {
    if (PROTECTED_LABELS.has(key)) return true;
    if (key.startsWith('k3s.io/') || key.startsWith('k3s.cattle.io/')) return true;
    const slashIdx = key.indexOf('/');
    if (slashIdx > 0) {
        const prefix = key.slice(0, slashIdx + 1);
        if (prefix.endsWith('.k3s.io/') || prefix.endsWith('.k3s.cattle.io/')) return true;
    }
    return false;
};
const PROTECTED_ROLES = new Set(['control-plane', 'master', 'etcd']);
const GPU_PROVISIONING_LABELS = new Set([
    'nvidia.com/gpu.present',
    'feature.node.kubernetes.io/pci-10de.present',
    'amd.com/gpu.present',
    'feature.node.kubernetes.io/pci-1002.present',
]);
const DEFAULT_NODE_ROLES = [
    'ingest',
    'queue',
    'compute',
    'database',
    'warehouse',
    'application',
];

const NodeConfigModal = ({
    isOpen,
    onClose,
    node,
    availableRoles = [],
    onSave,
}) => {
    const [gpuVendor, setGpuVendor] = useState('none');
    const [userRoles, setUserRoles] = useState([]);
    const [newRole, setNewRole] = useState('');
    const [customLabels, setCustomLabels] = useState([]);
    const [removedKeys, setRemovedKeys] = useState([]);
    const [newKey, setNewKey] = useState('');
    const [newValue, setNewValue] = useState('');
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        if (!node) return;
        const labels = node.labels || {};
        setGpuVendor(node.gpu_vendor === 'nvidia' || node.gpu_vendor === 'amd' ? node.gpu_vendor : 'none');

        const roles = Array.isArray(node.roles) ? node.roles : [];
        setUserRoles(roles.filter((r) => !PROTECTED_ROLES.has(r)));
        setNewRole('');

        const editable = Object.entries(labels)
            .filter(([k]) => (
                !isProtectedLabel(k) &&
                !k.startsWith('node-role.kubernetes.io/') &&
                !GPU_PROVISIONING_LABELS.has(k)
            ))
            .map(([key, value]) => ({ key, value: value ?? '' }));
        setCustomLabels(editable);
        setRemovedKeys([]);
        setNewKey('');
        setNewValue('');
    }, [node]);

    if (!node) return null;

    const systemRoles = (node.roles || []).filter((r) => PROTECTED_ROLES.has(r));
    const systemLabels = Object.entries(node.labels || {}).filter(([k]) => isProtectedLabel(k));

    const handleAddRole = (roleName) => {
        const clean = roleName.trim();
        if (!clean || PROTECTED_ROLES.has(clean) || userRoles.includes(clean)) return;
        setUserRoles((prev) => [...prev, clean]);
        setNewRole('');
    };

    const handleRemoveRole = (roleName) => {
        setUserRoles((prev) => prev.filter((r) => r !== roleName));
    };

    const handleAddLabel = () => {
        const k = newKey.trim();
        const v = newValue.trim();
        if (!k || isProtectedLabel(k) || k.startsWith('node-role.kubernetes.io/')) return;
        setCustomLabels((prev) => {
            const idx = prev.findIndex((item) => item.key === k);
            if (idx >= 0) {
                const copy = [...prev];
                copy[idx] = { key: k, value: v };
                return copy;
            }
            return [...prev, { key: k, value: v }];
        });
        setRemovedKeys((prev) => prev.filter((item) => item !== k));
        setNewKey('');
        setNewValue('');
    };

    const handleRemoveLabel = (key) => {
        setCustomLabels((prev) => prev.filter((item) => item.key !== key));
        if (node.labels && Object.prototype.hasOwnProperty.call(node.labels, key)) {
            setRemovedKeys((prev) => (prev.includes(key) ? prev : [...prev, key]));
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setSaving(true);
        try {
            const setLabels = {};
            customLabels.forEach(({ key, value }) => {
                if (key.trim()) {
                    setLabels[key.trim()] = value;
                }
            });
            await onSave(node.hostname, {
                set_labels: setLabels,
                remove_labels: removedKeys,
                roles: userRoles,
                gpu_vendor: gpuVendor,
            });
            onClose();
        } finally {
            setSaving(false);
        }
    };

    const mergedAvailableRoles = Array.from(new Set([...DEFAULT_NODE_ROLES, ...availableRoles]));
    const suggestedRoles = mergedAvailableRoles.filter(
        (r) => !PROTECTED_ROLES.has(r) && !userRoles.includes(r)
    );

    return (
        <Modal
            isOpen={isOpen}
            onClose={onClose}
            title={`Configure Node: ${node.hostname}`}
            size="lg"
        >
            <form id="node-config-form" onSubmit={handleSubmit} className="space-y-6">
                {/* GPU Provisioning Section */}
                <div className="space-y-3 p-4 rounded-xl bg-slate-50 dark:bg-slate-900/60 border border-slate-200/70 dark:border-slate-800">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <Cpu size={16} className="text-emerald-500" />
                            <h4 className="text-sm font-bold uppercase tracking-wider text-slate-700 dark:text-slate-200">
                                GPU Provisioning
                            </h4>
                        </div>
                        {node.gpu_count > 0 && (
                            <span className="text-xs font-mono font-semibold text-emerald-500">
                                Detected: {node.gpu_count}x {node.gpu_product || node.gpu_vendor?.toUpperCase()}
                            </span>
                        )}
                    </div>
                    <p className="text-xs text-slate-500">
                        Applies standard NVIDIA or AMD GPU operator provisioning labels to this node.
                    </p>
                    <div className="grid grid-cols-3 gap-2">
                        {[
                            { value: 'none', label: 'None', desc: 'No GPU label' },
                            { value: 'nvidia', label: 'NVIDIA GPU', desc: 'nvidia.com/gpu.present' },
                            { value: 'amd', label: 'AMD GPU', desc: 'amd.com/gpu.present + pci-1002' },
                        ].map((opt) => (
                            <button
                                key={opt.value}
                                id={`gpu-vendor-${opt.value}`}
                                type="button"
                                onClick={() => setGpuVendor(opt.value)}
                                className={`p-3 rounded-xl border text-left transition-all ${
                                    gpuVendor === opt.value
                                        ? 'border-indigo-500 bg-indigo-500/10 text-indigo-600 dark:text-indigo-400'
                                        : 'border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700'
                                }`}
                            >
                                <div className="text-xs font-bold">{opt.label}</div>
                                <div className="text-[11px] font-mono text-slate-400 truncate">{opt.desc}</div>
                            </button>
                        ))}
                    </div>
                </div>

                {/* Node Roles Section */}
                <div className="space-y-3 p-4 rounded-xl bg-slate-50 dark:bg-slate-900/60 border border-slate-200/70 dark:border-slate-800">
                    <div className="flex items-center gap-2">
                        <Shield size={16} className="text-blue-500" />
                        <h4 className="text-sm font-bold uppercase tracking-wider text-slate-700 dark:text-slate-200">
                            Node Roles
                        </h4>
                    </div>
                    <div className="flex flex-wrap gap-2">
                        {systemRoles.map((r) => (
                            <span
                                key={r}
                                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold bg-slate-200 dark:bg-slate-800 text-slate-600 dark:text-slate-300"
                                title="System-managed role"
                            >
                                <Lock size={11} />
                                {r}
                            </span>
                        ))}
                        {userRoles.map((r) => (
                            <span
                                key={r}
                                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold bg-blue-500/10 border border-blue-500/20 text-blue-600 dark:text-blue-400"
                            >
                                {r}
                                <button
                                    type="button"
                                    onClick={() => handleRemoveRole(r)}
                                    className="hover:text-red-500"
                                    title={`Remove role ${r}`}
                                >
                                    ×
                                </button>
                            </span>
                        ))}
                        {systemRoles.length === 0 && userRoles.length === 0 && (
                            <span className="text-xs text-slate-400">No roles assigned.</span>
                        )}
                    </div>

                    <div className="flex gap-2">
                        <input
                            id="new-node-role-input"
                            type="text"
                            value={newRole}
                            onChange={(e) => setNewRole(e.target.value)}
                            onKeyDown={(e) => {
                                if (e.key === 'Enter') {
                                    e.preventDefault();
                                    handleAddRole(newRole);
                                }
                            }}
                            placeholder="Add role (e.g. compute, storage, ingress)"
                            className="mw-input flex-1 text-sm"
                        />
                        <button
                            id="add-node-role-btn"
                            type="button"
                            onClick={() => handleAddRole(newRole)}
                            className="mw-btn-secondary px-3 py-2 text-xs flex items-center gap-1"
                        >
                            <Plus size={14} /> ADD ROLE
                        </button>
                    </div>

                    {suggestedRoles.length > 0 && (
                        <div className="flex flex-wrap items-center gap-1.5 pt-1">
                            <span className="text-[11px] text-slate-400">Quick add:</span>
                            {suggestedRoles.map((r) => (
                                <button
                                    key={r}
                                    type="button"
                                    onClick={() => handleAddRole(r)}
                                    className="px-2 py-0.5 rounded-md text-[11px] font-semibold bg-slate-200/70 dark:bg-slate-800 hover:bg-blue-500/10 text-slate-600 dark:text-slate-300"
                                >
                                    + {r}
                                </button>
                            ))}
                        </div>
                    )}
                </div>

                {/* Custom Labels Section */}
                <div className="space-y-3 p-4 rounded-xl bg-slate-50 dark:bg-slate-900/60 border border-slate-200/70 dark:border-slate-800">
                    <div className="flex items-center gap-2">
                        <Tag size={16} className="text-purple-500" />
                        <h4 className="text-sm font-bold uppercase tracking-wider text-slate-700 dark:text-slate-200">
                            Node Labels
                        </h4>
                    </div>

                    <div className="max-h-48 overflow-y-auto space-y-2">
                        {customLabels.map((item, idx) => (
                            <div key={item.key} className="flex items-center gap-2">
                                <input
                                    type="text"
                                    value={item.key}
                                    disabled
                                    className="mw-input flex-1 text-xs font-mono opacity-80"
                                />
                                <input
                                    type="text"
                                    value={item.value}
                                    onChange={(e) => {
                                        const val = e.target.value;
                                        setCustomLabels((prev) =>
                                            prev.map((row, i) => (i === idx ? { ...row, value: val } : row))
                                        );
                                    }}
                                    placeholder="value"
                                    className="mw-input flex-1 text-xs font-mono"
                                />
                                <button
                                    type="button"
                                    onClick={() => handleRemoveLabel(item.key)}
                                    className="p-2 text-slate-400 hover:text-red-500 rounded-lg"
                                    title={`Remove ${item.key}`}
                                >
                                    <Trash2 size={14} />
                                </button>
                            </div>
                        ))}
                    </div>

                    <div className="flex items-center gap-2 pt-2 border-t border-slate-200/60 dark:border-slate-800">
                        <input
                            id="new-label-key-input"
                            type="text"
                            value={newKey}
                            onChange={(e) => setNewKey(e.target.value)}
                            placeholder="label key (e.g. disk-type)"
                            className="mw-input flex-1 text-xs font-mono"
                        />
                        <input
                            id="new-label-value-input"
                            type="text"
                            value={newValue}
                            onChange={(e) => setNewValue(e.target.value)}
                            placeholder="label value (e.g. nvme)"
                            className="mw-input flex-1 text-xs font-mono"
                        />
                        <button
                            id="add-node-label-btn"
                            type="button"
                            onClick={handleAddLabel}
                            className="mw-btn-secondary px-3 py-2 text-xs flex items-center gap-1"
                        >
                            <Plus size={14} /> ADD
                        </button>
                    </div>

                    {systemLabels.length > 0 && (
                        <div className="pt-2 text-[11px] text-slate-400 space-y-1">
                            <div className="flex items-center gap-1 font-semibold">
                                <Lock size={11} /> Protected System Labels
                            </div>
                            <div className="flex flex-wrap gap-1.5">
                                {systemLabels.map(([k, v]) => (
                                    <span
                                        key={k}
                                        className="px-2 py-0.5 rounded bg-slate-200/60 dark:bg-slate-800/80 font-mono"
                                    >
                                        {k}={v}
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}
                </div>

                <div className="flex justify-end gap-3 pt-2">
                    <button
                        type="button"
                        onClick={onClose}
                        className="mw-btn-secondary px-5 py-2 text-xs"
                    >
                        CANCEL
                    </button>
                    <button
                        id="save-node-config-btn"
                        type="submit"
                        disabled={saving}
                        className="mw-btn-primary px-5 py-2 text-xs disabled:opacity-60"
                    >
                        {saving ? 'SAVING...' : 'APPLY TO NODE'}
                    </button>
                </div>
            </form>
        </Modal>
    );
};

export default NodeConfigModal;
