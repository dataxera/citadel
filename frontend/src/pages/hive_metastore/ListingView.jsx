import React from 'react';
import { Boxes } from 'lucide-react';
import GenericListingView from '../../components/GenericListingView';
import PlatformListingSubtitle from '../../components/PlatformListingSubtitle';

const ListingView = ({
    darkMode,
    selectedProject,
    projects = [],
    hms,
    onSelectPlatform
}) => {
    const { platforms, loading, fetchPlatforms, getPlatformState } = hms;

    const renderSubtitle = (platform, state) => (
        <PlatformListingSubtitle platform={platform} state={state} projects={projects} />
    );

    const renderBadges = (platform, state) => {
        return state.message ? [{ text: state.message, variant: "mw-badge-info" }] : [];
    };

    return (
        <GenericListingView
            title="Hive Metastore"
            description="Manage Apache Hive Metastore clusters for your data lake"
            items={platforms}
            loading={loading}
            fetchItems={fetchPlatforms}
            getItemState={getPlatformState}
            onSelectItem={(platform) => onSelectPlatform(platform.id, 'connect')}
            onEditItem={(platform) => onSelectPlatform(platform.id, 'configure')}
            icon={Boxes}
            entityPath="/platform/hive-metastore"
            createConfig={{
                title: "Provision Hive Metastore",
                buttonText: "NEW METASTORE",
            }}
            searchPlaceholder="Search metastore clusters..."
            emptyState={{
                title: "No metastores found",
                description: selectedProject ? `No Hive Metastore clusters in ${selectedProject.name}.` : 'Create your first Hive Metastore cluster to get started.',
                icon: <Boxes size={48} className="text-slate-700" />
            }}
            renderSubtitle={renderSubtitle}
            renderBadges={renderBadges}
            darkMode={darkMode}
            selectedProject={selectedProject}
        />
    );
};

export default ListingView;
