import React from 'react';
import { Database } from 'lucide-react';
import GenericListingView from '../../components/GenericListingView';
import PlatformListingSubtitle from '../../components/PlatformListingSubtitle';

const ListingView = ({
    darkMode,
    selectedProject,
    projects = [],
    pgsql,
    onSelectPlatform
}) => {
    const { platforms, loading, fetchPlatforms, getPlatformState } = pgsql;

    const renderSubtitle = (platform, state) => (
        <PlatformListingSubtitle platform={platform} state={state} projects={projects} />
    );

    const renderBadges = (platform, state) => {
        return state.message ? [{ text: state.message, variant: "dxc-badge-info" }] : [];
    };

    return (
        <GenericListingView
            title="PostgreSQL Clusters"
            description="High-availability PostgreSQL managed on Kubernetes"
            items={platforms}
            loading={loading}
            fetchItems={fetchPlatforms}
            getItemState={getPlatformState}
            onSelectItem={(platform) => onSelectPlatform(platform.id, 'connect')}
            onEditItem={(platform) => onSelectPlatform(platform.id, 'configure')}
            icon={Database}
            entityPath="/platform/pgsql"
            createConfig={{
                title: "Provision PGSQL Cluster",
                buttonText: "NEW CLUSTER",
            }}
            searchPlaceholder="Search PostgreSQL clusters..."
            emptyState={{
                title: "No clusters found",
                description: selectedProject ? `No PostgreSQL clusters in ${selectedProject.name}.` : 'Create your first PostgreSQL cluster to get started.',
                icon: <Database size={48} className="text-slate-700" />
            }}
            renderSubtitle={renderSubtitle}
            renderBadges={renderBadges}
            darkMode={darkMode}
            selectedProject={selectedProject}
        />
    );
};

export default ListingView;
