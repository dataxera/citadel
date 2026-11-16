// SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
// SPDX-License-Identifier: AGPLv3+

import React from 'react';
import { Network } from 'lucide-react';
import GenericListingView from '../../components/GenericListingView';
import PlatformListingSubtitle from '../../components/PlatformListingSubtitle';

/**
 * ListingView displays a list of provisioned Apache NiFi platforms with their statuses and active states.
 */
const ListingView = ({
    darkMode,
    selectedProject,
    projects = [],
    nifi,
    onSelectPlatform
}) => {
    const { platforms, loading, fetchPlatforms, getPlatformState } = nifi;

    const renderSubtitle = (platform, state) => (
        <PlatformListingSubtitle platform={platform} state={state} projects={projects} />
    );

    const renderBadges = (platform, state) => {
        const badges = [];
        if (platform.replica_count) {
            badges.push({ text: `${platform.replica_count} replica(s)`, variant: "dxc-badge-info" });
        }
        if (state.message) {
            badges.push({ text: state.message, variant: "dxc-badge-info" });
        }
        return badges;
    };

    return (
        <GenericListingView
            title="Apache NiFi"
            description="Manage Apache NiFi data flow processing clusters"
            items={platforms}
            loading={loading}
            fetchItems={fetchPlatforms}
            getItemState={getPlatformState}
            onSelectItem={(platform) => onSelectPlatform(platform.id, 'connect')}
            onEditItem={(platform) => onSelectPlatform(platform.id, 'configure')}
            icon={Network}
            entityPath="/platform/nifi"
            createConfig={{
                title: "Provision Apache NiFi",
                buttonText: "NEW NIFI",
            }}
            searchPlaceholder="Search Apache NiFi clusters..."
            emptyState={{
                title: "No Apache NiFi clusters found",
                description: selectedProject ? `No Apache NiFi clusters in ${selectedProject.name}.` : 'Create your first Apache NiFi cluster to get started.',
                icon: <Network size={48} className="text-slate-700" />
            }}
            renderSubtitle={renderSubtitle}
            renderBadges={renderBadges}
            darkMode={darkMode}
            selectedProject={selectedProject}
        />
    );
};

export default ListingView;
