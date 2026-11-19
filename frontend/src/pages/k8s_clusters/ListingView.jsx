import React, { useState } from 'react';
import { Server, AlertTriangle } from 'lucide-react';
import Modal from '../../components/Modal';
import DynamicForm from '../../components/DynamicForm';
import GenericListingView from '../../components/GenericListingView';
import { clusterNeedsIntegrationSync } from './coreIntegrations';

const ListingView = ({ context, clustersHook, onSelectCluster }) => {
    const { darkMode } = context;
    const { clusters, loading, deleteCluster, fetchClusters, getClusterState } = clustersHook;
    const [isEditModalOpen, setIsEditModalOpen] = useState(false);
    const [selectedClusterForEdit, setSelectedClusterForEdit] = useState(null);

    const renderSubtitle = (cluster, state) => {
        const statusColor = state.status === 'online' ? 'bg-green-500' :
            state.status === 'error' ? 'bg-red-500' :
                state.status === 'offline' ? 'bg-slate-400' :
                    'bg-yellow-500';

        return (
            <div className="flex items-center gap-2">
                <div
                    className={`w-2.5 h-2.5 rounded-full ${statusColor}`}
                    title={`Status: ${state.status || 'unknown'}`}
                />
                <span>{cluster.type}</span>
            </div>
        );
    };

    const renderBadges = (cluster, state) => (
        state.k8s_version ? [{ text: state.k8s_version, variant: "dxc-badge-neutral" }] : []
    );

    const renderActions = (cluster, state, { onDelete, canUpdate, canDelete }) => (
        <React.Fragment>
            <div className="flex items-center gap-12">
                {clusterNeedsIntegrationSync(state) && (
                    <div
                        className="cluster-integration-alert flex items-center justify-center p-2 rounded-lg bg-amber-500/10 text-amber-500 border border-amber-500/20"
                        title="Core integrations need to be installed or updated. Open cluster to sync integrations."
                        aria-label="Core integrations need to be installed or updated"
                    >
                        <AlertTriangle size={18} />
                    </div>
                )}

                <div className="text-center">
                    <p className="text-base text-slate-500 uppercase font-bold mb-1">Nodes</p>
                    <p className="text-lg font-bold text-slate-900 dark:text-white">{state.node_count || 0}</p>
                </div>

                <div className="flex items-center gap-2">
                    {canUpdate && (
                        <button
                            onClick={(e) => {
                                e.stopPropagation();
                                setSelectedClusterForEdit(cluster);
                                setIsEditModalOpen(true);
                            }}
                            className="p-2 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors text-slate-400 hover:text-blue-500"
                            title="Edit Cluster"
                        >
                            {/* Using manual SVG to match existing style if lucide import is removed/changed */}
                            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="lucide lucide-edit-2"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"></path></svg>
                        </button>
                    )}
                    {canDelete && onDelete && (
                        <button
                            onClick={(e) => onDelete(e, cluster)}
                            className="p-2 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors text-slate-400 hover:text-red-500"
                            title="Delete Cluster"
                        >
                            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="lucide lucide-trash-2"><path d="M3 6h18"></path><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>
                        </button>
                    )}
                    <div className="w-px h-8 bg-slate-200 dark:bg-slate-800 mx-2" />
                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="lucide lucide-chevron-right text-slate-300 dark:text-slate-600"><path d="m9 18 6-6-6-6"></path></svg>
                </div>
            </div>
        </React.Fragment>
    );

    return (
        <React.Fragment>
            <GenericListingView
                title="Kubernetes Clusters"
                description="Manage underlying infrastructure compute clusters."
                items={clusters}
                loading={loading}
                fetchItems={fetchClusters}
                deleteItem={deleteCluster}
                getItemState={getClusterState}
                onSelectItem={(cluster) => onSelectCluster(cluster.id)}
                icon={Server}
                entityPath="/k8s_clusters"
                createConfig={{
                    title: "Register New Cluster",
                    buttonText: "REGISTER CLUSTER",
                }}
                searchPlaceholder="Search clusters by title or description..."
                emptyState={{
                    title: "No clusters registered",
                    description: "Register a Kubernetes cluster to start deploying infrastructure.",
                    icon: <Server size={48} className="text-slate-700" />
                }}
                renderSubtitle={renderSubtitle}
                renderBadges={renderBadges}
                renderActions={renderActions}
                deleteModalConfig={{
                    title: "Delete Cluster",
                    message: "Are you sure you want to remove this cluster? Wait, ensure that no projects are actively referencing it!"
                }}
                darkMode={darkMode}
                searchFields={["title", "description"]}
            />

            <Modal
                isOpen={isEditModalOpen}
                onClose={() => {
                    setIsEditModalOpen(false);
                    setSelectedClusterForEdit(null);
                }}
                title="Edit Cluster"
                darkMode={darkMode}
            >
                {selectedClusterForEdit && (
                    <DynamicForm
                        entityPath="/k8s_clusters"
                        mode="edit"
                        initialData={selectedClusterForEdit}
                        darkMode={darkMode}
                        onSuccess={() => {
                            setIsEditModalOpen(false);
                            setSelectedClusterForEdit(null);
                            fetchClusters();
                        }}
                        onCancel={() => {
                            setIsEditModalOpen(false);
                            setSelectedClusterForEdit(null);
                        }}
                    />
                )}
            </Modal>
        </React.Fragment>
    );
};

export default ListingView;
