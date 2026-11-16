// SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
// SPDX-License-Identifier: AGPLv3+

import React from 'react';
import { RefreshCcw } from 'lucide-react';
import GenericListingView from '../../components/GenericListingView';
import PlatformListingSubtitle from '../../components/PlatformListingSubtitle';

const ListingView = ({
    darkMode,
    selectedProject,
    projects = [],
    kafka,
    onSelectPlatform
}) => {
    const { platforms, loading, fetchPlatforms, getPlatformState } = kafka;

    const renderSubtitle = (platform, state) => (
        <PlatformListingSubtitle platform={platform} state={state} projects={projects} />
    );

    const renderBadges = (platform, state) => {
        const badges = [];
        if (platform.replica_count) {
            badges.push({ text: `${platform.replica_count} replica(s)`, variant: "dxc-badge-info" });
        }
        if (platform.enable_loadbalancer) {
            badges.push({ text: "LoadBalancer", variant: "dxc-badge-accent" });
        }
        if (state.message) {
            badges.push({ text: state.message, variant: "dxc-badge-info" });
        }
        return badges;
    };

    return (
        <GenericListingView
            title="Apache Kafka"
            description="Manage Apache Kafka event streaming clusters"
            items={platforms}
            loading={loading}
            fetchItems={fetchPlatforms}
            getItemState={getPlatformState}
            onSelectItem={(platform) => onSelectPlatform(platform.id, 'connect')}
            onEditItem={(platform) => onSelectPlatform(platform.id, 'configure')}
            icon={RefreshCcw}
            entityPath="/platform/kafka"
            createConfig={{
                title: "Provision Apache Kafka",
                buttonText: "NEW KAFKA",
            }}
            searchPlaceholder="Search Apache Kafka clusters..."
            emptyState={{
                title: "No Apache Kafka clusters found",
                description: selectedProject ? `No Apache Kafka clusters in ${selectedProject.name}.` : 'Create your first Apache Kafka cluster to get started.',
                icon: <RefreshCcw size={48} className="text-slate-700" />
            }}
            renderSubtitle={renderSubtitle}
            renderBadges={renderBadges}
            darkMode={darkMode}
            selectedProject={selectedProject}
        />
    );
};

export default ListingView;
