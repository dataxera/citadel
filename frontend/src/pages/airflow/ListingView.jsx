import React from 'react';
import { Activity } from 'lucide-react';
import GenericListingView from '../../components/GenericListingView';
import PlatformListingSubtitle from '../../components/PlatformListingSubtitle';

const ListingView = ({ darkMode, selectedProject, projects = [], onSelectPlatform, airflow }) => {
    const { platforms, loading, fetchPlatforms, getPlatformState } = airflow;

    const renderSubtitle = (platform, state) => (
        <PlatformListingSubtitle platform={platform} state={state} projects={projects} />
    );

    const renderBadges = (platform, state) => {
        return state.message ? [{ text: state.message, variant: "dxc-badge-info" }] : [];
    };

    return (
        <GenericListingView
            title="Apache Airflow"
            description="Workflow orchestration and scheduling platform"
            items={platforms}
            loading={loading}
            fetchItems={fetchPlatforms}
            getItemState={getPlatformState}
            onSelectItem={(platform) => onSelectPlatform(platform.id, 'connect')}
            onEditItem={(platform) => onSelectPlatform(platform.id, 'configure')}
            icon={Activity}
            entityPath="/platform/airflow"
            createConfig={{
                title: "Provision Airflow Instance",
                buttonText: "NEW INSTANCE",
            }}
            searchPlaceholder="Search Airflow instances..."
            emptyState={{
                title: "No instances found",
                description: selectedProject ? `No Airflow instances in ${selectedProject.name}.` : 'Create your first Airflow instance to get started.',
                icon: <Activity size={48} className="text-slate-700" />
            }}
            renderSubtitle={renderSubtitle}
            renderBadges={renderBadges}
            darkMode={darkMode}
            selectedProject={selectedProject}
        />
    );
};

export default ListingView;
