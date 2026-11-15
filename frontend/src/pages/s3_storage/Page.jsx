import React from 'react';
import { useOutletContext, useParams, useNavigate } from 'react-router-dom';
import { useS3Storages } from '../../hooks/useResources';
import { ResourceLoading, ResourceNotFound } from '../../components/ResourceRouteState';
import ListingView from './ListingView';
import ServiceView from './ServiceView';

const S3StoragePage = () => {
    const { darkMode, selectedProject } = useOutletContext();
    const { id } = useParams();
    const navigate = useNavigate();
    const s3Storages = useS3Storages();

    const handleSelectStorage = (storage) => {
        navigate(`/s3-storages/${storage.id}`);
    };

    const handleBack = () => {
        navigate('/s3-storages');
    };

    if (id) {
        const browsingStorage = s3Storages.storages.find(s => String(s.id) === String(id));

        if (!browsingStorage) {
            if (s3Storages.loading) {
                return <ResourceLoading message="Loading S3 storage..." />;
            }
            return (
                <ResourceNotFound
                    title="S3 Storage Not Found"
                    description="The requested S3 storage connection could not be found or may have been deleted."
                    onBack={handleBack}
                />
            );
        }

        return (
            <ServiceView
                darkMode={darkMode}
                browsingStorage={browsingStorage}
                onBack={handleBack}
                s3Storages={s3Storages}
            />
        );
    }

    return (
        <ListingView
            darkMode={darkMode}
            selectedProject={selectedProject}
            s3Storages={s3Storages}
            onSelectStorage={handleSelectStorage}
        />
    );
};

export default S3StoragePage;
