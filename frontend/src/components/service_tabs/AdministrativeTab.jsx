// SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
// SPDX-License-Identifier: AGPLv3+

import React, { useState } from 'react';
import { AlertCircle } from 'lucide-react';
import { cn } from '../../utils/cn';
import ResourceConfirmModal from '../ResourceConfirmModal';

/**
 * Common "Administrative" tab for service views.
 * Provides Danger Zone actions (decommission and delete) with confirmation modals.
 */
const AdministrativeTab = ({
    darkMode = true,
    resourceName,
    isActive = false,
    icon,
    onDecommission,
    decommissionTitle = 'Decommission Cluster',
    decommissionButtonText = 'DECOMMISSION CLUSTER',
    decommissionModalTitle = 'Confirm Decommissioning',
    decommissionWarningText = 'Decommissioning this cluster will permanently delete all associated Kubernetes resources and data. This action cannot be undone.',
    onDelete,
    deleteTitle = 'Delete Cluster',
    deleteButtonText = 'DELETE CLUSTER',
    deleteModalTitle = 'Confirm Deletion',
    deleteWarningText = 'Permanently delete this cluster and all associated configurations. The cluster must be decommissioned before it can be deleted. This action cannot be undone.',
}) => {
    const [isDecommissionModalOpen, setIsDecommissionModalOpen] = useState(false);
    const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);

    return (
        <div className="mw-administrative-tab space-y-6 animate-in fade-in slide-in-from-top-4 duration-500">
            <div className="mw-panel overflow-hidden border-rose-500/20">
                <div className="p-4 border-b bg-rose-500/5 border-rose-500/10 flex items-center gap-3">
                    <AlertCircle className="text-rose-500" size={20} />
                    <h4 className="text-base font-bold tracking-wider text-rose-500 uppercase">Danger Zone</h4>
                </div>
                <div className="p-8 space-y-6">
                    {onDecommission && (
                        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
                            <div className="space-y-1">
                                <h5 className="text-lg font-bold text-slate-900 dark:text-white">{decommissionTitle}</h5>
                                <p className="text-sm text-slate-500 dark:text-slate-400 max-w-xl">
                                    {decommissionWarningText}
                                </p>
                            </div>
                            <button
                                type="button"
                                onClick={() => setIsDecommissionModalOpen(true)}
                                disabled={!isActive}
                                className={cn(
                                    'mw-decommission-btn px-8 py-3 rounded-xl font-bold text-sm transition-all border shrink-0',
                                    isActive
                                        ? 'bg-rose-500 text-white hover:bg-rose-600 border-rose-600 shadow-lg shadow-rose-500/20'
                                        : 'bg-slate-100 text-slate-400 border-slate-200 cursor-not-allowed'
                                )}
                            >
                                {decommissionButtonText}
                            </button>
                        </div>
                    )}

                    {onDelete && (
                        <div
                            className={cn(
                                'flex flex-col md:flex-row md:items-center justify-between gap-6',
                                onDecommission && 'pt-6 border-t border-rose-500/10'
                            )}
                        >
                            <div className="space-y-1">
                                <h5 className="text-lg font-bold text-slate-900 dark:text-white">{deleteTitle}</h5>
                                <p className="text-sm text-slate-500 dark:text-slate-400 max-w-xl">
                                    {deleteWarningText}
                                </p>
                            </div>
                            <button
                                type="button"
                                onClick={() => setIsDeleteModalOpen(true)}
                                disabled={isActive}
                                className={cn(
                                    'mw-delete-btn px-8 py-3 rounded-xl font-bold text-sm transition-all border shrink-0',
                                    !isActive
                                        ? 'bg-rose-500 text-white hover:bg-rose-600 border-rose-600 shadow-lg shadow-rose-500/20'
                                        : 'bg-slate-100 text-slate-400 border-slate-200 cursor-not-allowed'
                                )}
                            >
                                {deleteButtonText}
                            </button>
                        </div>
                    )}
                </div>
            </div>

            {isDecommissionModalOpen && onDecommission && (
                <ResourceConfirmModal
                    isOpen={isDecommissionModalOpen}
                    onClose={() => setIsDecommissionModalOpen(false)}
                    onConfirm={(name, options) => onDecommission(name || resourceName, options)}
                    resourceName={resourceName}
                    darkMode={darkMode}
                    title={decommissionModalTitle}
                    message={decommissionWarningText}
                    confirmText="DECOMMISSION"
                    icon={icon}
                    variant="danger"
                    showForceOption={true}
                />
            )}

            {isDeleteModalOpen && onDelete && (
                <ResourceConfirmModal
                    isOpen={isDeleteModalOpen}
                    onClose={() => setIsDeleteModalOpen(false)}
                    onConfirm={(name) => onDelete(name || resourceName)}
                    resourceName={resourceName}
                    darkMode={darkMode}
                    title={deleteModalTitle}
                    message={deleteWarningText}
                    confirmText="DELETE"
                    icon={icon}
                    variant="danger"
                />
            )}
        </div>
    );
};

export default AdministrativeTab;
