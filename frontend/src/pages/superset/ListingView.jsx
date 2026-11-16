import React from 'react';
import { LayoutDashboard } from 'lucide-react';
import GenericListingView from '../../components/GenericListingView';
import PlatformListingSubtitle from '../../components/PlatformListingSubtitle';

const ListingView = ({ darkMode, selectedProject, projects = [], onSelectPlatform, superset }) => {
    const { platforms, loading, fetchPlatforms, getPlatformState } = superset;

    const renderSubtitle = (platform, state) => (
        <PlatformListingSubtitle platform={platform} state={state} projects={projects} />
    );

    const renderBadges = (platform, state) => {
        return state.message ? [{ text: state.message, variant: "dxc-badge-info" }] : [];
    };

    return (
        <GenericListingView
            title="Apache Superset"
            description="Modern data exploration and visualization platform"
            items={platforms}
            loading={loading}
            fetchItems={fetchPlatforms}
            getItemState={getPlatformState}
            onSelectItem={(platform) => onSelectPlatform(platform.id, 'connect')}
            onEditItem={(platform) => onSelectPlatform(platform.id, 'configure')}
            icon={LayoutDashboard}
            entityPath="/platform/superset"
            createConfig={{
                title: "Provision Superset Instance",
                buttonText: "NEW INSTANCE",
            }}
            searchPlaceholder="Search Superset instances..."
            emptyState={{
                title: "No instances found",
                description: selectedProject ? `No Superset instances in ${selectedProject.name}.` : 'Create your first Superset instance to get started.',
                icon: <LayoutDashboard size={48} className="text-slate-700" />
            }}
            renderSubtitle={renderSubtitle}
            renderBadges={renderBadges}
            darkMode={darkMode}
            selectedProject={selectedProject}
        />
    );
};

export default ListingView;
