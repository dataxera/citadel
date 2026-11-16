/*
SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
SPDX-License-Identifier: AGPLv3+
*/

import React from 'react';
import { Database } from 'lucide-react';
import GenericListingView from '../../components/GenericListingView';
import PlatformListingSubtitle from '../../components/PlatformListingSubtitle';

const ListingView = ({ darkMode, selectedProject, projects = [], onSelectPlatform, doris }) => {
    const { platforms, loading, fetchPlatforms, getPlatformState } = doris;

    const renderSubtitle = (platform, state) => (
        <PlatformListingSubtitle platform={platform} state={state} projects={projects} />
    );

    const renderBadges = (platform, state) => {
        return state.message ? [{ text: state.message, variant: "dxc-badge-info" }] : [];
    };

    return (
        <GenericListingView
            title="Apache Doris"
            description="Real-time analytical database and MPP data warehouse"
            items={platforms}
            loading={loading}
            fetchItems={fetchPlatforms}
            getItemState={getPlatformState}
            onSelectItem={(platform) => onSelectPlatform(platform.id, 'connect')}
            onEditItem={(platform) => onSelectPlatform(platform.id, 'configure')}
            icon={Database}
            entityPath="/platform/doris"
            createConfig={{
                title: "Provision Doris Cluster",
                buttonText: "NEW CLUSTER",
            }}
            searchPlaceholder="Search Doris clusters..."
            emptyState={{
                title: "No clusters found",
                description: selectedProject ? `No Doris clusters in ${selectedProject.name}.` : 'Create your first Doris cluster to get started.',
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
