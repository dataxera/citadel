import React from 'react';
import { Server } from 'lucide-react';
import GenericListingView from '../../components/GenericListingView';
import PlatformListingSubtitle from '../../components/PlatformListingSubtitle';

const ListingView = ({ darkMode, selectedProject, projects = [], onSelectPlatform, trino }) => {
    const { platforms, loading, fetchPlatforms, getPlatformState } = trino;

    const renderSubtitle = (platform, state) => (
        <PlatformListingSubtitle platform={platform} state={state} projects={projects} />
    );

    const renderBadges = (platform, state) => {
        return state.message ? [{ text: state.message, variant: "mw-badge-info" }] : [];
    };

    return (
        <GenericListingView
            title="Trino Clusters"
            description="Distributed SQL query engine managed on Kubernetes"
            items={platforms}
            loading={loading}
            fetchItems={fetchPlatforms}
            getItemState={getPlatformState}
            onSelectItem={(platform) => onSelectPlatform(platform.id, 'connect')}
            onEditItem={(platform) => onSelectPlatform(platform.id, 'configure')}
            icon={Server}
            entityPath="/platform/trino"
            createConfig={{
                title: "Provision Trino Cluster",
                buttonText: "NEW CLUSTER",
            }}
            searchPlaceholder="Search Trino clusters..."
            emptyState={{
                title: "No clusters found",
                description: selectedProject ? `No Trino clusters in ${selectedProject.name}.` : 'Create your first Trino cluster to get started.',
                icon: <Server size={48} className="text-slate-700" />
            }}
            renderSubtitle={renderSubtitle}
            renderBadges={renderBadges}
            darkMode={darkMode}
            selectedProject={selectedProject}
        />
    );
};

export default ListingView;
