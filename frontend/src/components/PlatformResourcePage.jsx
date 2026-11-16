/*
SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
SPDX-License-Identifier: AGPLv3+
*/

import React from 'react';
import { useOutletContext, useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { ResourceLoading, ResourceNotFound } from './ResourceRouteState';

/**
 * Shared route controller for platform service pages that separates the listing view
 * (`basePath`) from the individual deployment view (`basePath/:id`).
 */
const PlatformResourcePage = (props) => {
    const {
        useResourceHook,
        resourcePropName,
        basePath,
        ListingView,
        ServiceView,
        notFoundTitle = 'Deployment Not Found',
        notFoundDescription = 'The requested deployment could not be found or may have been deleted.',
    } = props;
    const { darkMode, selectedProject, projects = [] } = useOutletContext();
    const { id } = useParams();
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const resource = useResourceHook();

    const handleSelectPlatform = (platformId, tab = 'connect') => {
        const suffix = tab && tab !== 'connect' ? `?tab=${encodeURIComponent(tab)}` : '';
        navigate(`${basePath}/${platformId}${suffix}`);
    };

    const handleBack = () => {
        navigate(basePath);
    };

    if (id) {
        const selectedPlatform = resource.platforms.find(p => String(p.id) === String(id));

        if (!selectedPlatform) {
            if (resource.loading) {
                return <ResourceLoading message="Loading deployment..." />;
            }
            return (
                <ResourceNotFound
                    title={notFoundTitle}
                    description={notFoundDescription}
                    onBack={handleBack}
                />
            );
        }

        const serviceProps = {
            darkMode,
            selectedPlatformId: selectedPlatform.id,
            selectedPlatform,
            onBack: handleBack,
            initialTab: searchParams.get('tab') || 'connect',
            [resourcePropName]: resource,
        };

        return <ServiceView {...serviceProps} />;
    }

    const listingProps = {
        darkMode,
        selectedProject,
        projects,
        onSelectPlatform: handleSelectPlatform,
        [resourcePropName]: resource,
    };

    return <ListingView {...listingProps} />;
};

export default PlatformResourcePage;
