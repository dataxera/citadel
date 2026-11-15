/*
SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
SPDX-License-Identifier: AGPLv3+
*/
import React from 'react';
import { useOutletContext, useParams, useNavigate } from 'react-router-dom';
import { useTrustedCerts } from '../../hooks/useResources';
import { ResourceLoading, ResourceNotFound } from '../../components/ResourceRouteState';
import ListingView from './ListingView';
import ServiceView from './ServiceView';

const TrustedCertsPage = () => {
    const { darkMode, selectedProject } = useOutletContext();
    const { id } = useParams();
    const navigate = useNavigate();
    const certsHook = useTrustedCerts();

    const handleSelectCert = (cert) => {
        navigate(`/trusted-certs/${cert.id}`);
    };

    const handleBack = () => {
        navigate('/trusted-certs');
    };

    if (id) {
        const browsingCert = certsHook.certs.find(c => String(c.id) === String(id));

        if (!browsingCert) {
            if (certsHook.loading) {
                return <ResourceLoading message="Loading trusted certificate..." />;
            }
            return (
                <ResourceNotFound
                    title="Trusted Certificate Not Found"
                    description="The requested trusted certificate could not be found or may have been deleted."
                    onBack={handleBack}
                />
            );
        }

        return (
            <ServiceView
                darkMode={darkMode}
                browsingCert={browsingCert}
                onBack={handleBack}
                certsHook={certsHook}
            />
        );
    }

    return (
        <ListingView
            darkMode={darkMode}
            selectedProject={selectedProject}
            certsHook={certsHook}
            onSelectCert={handleSelectCert}
        />
    );
};

export default TrustedCertsPage;
