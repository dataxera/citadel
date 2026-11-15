import React from 'react';
import { useOutletContext, useParams, useNavigate } from 'react-router-dom';
import { useK8sClusters } from '../../hooks/useResources';
import { ResourceLoading, ResourceNotFound } from '../../components/ResourceRouteState';
import ListingView from './ListingView';
import ServiceView from './ServiceView';

const K8sClustersPage = () => {
    const context = useOutletContext();
    const { id } = useParams();
    const navigate = useNavigate();
    const clustersHook = useK8sClusters();

    const handleSelectCluster = (clusterId) => {
        navigate(`/k8s_clusters/${clusterId}`);
    };

    const handleBack = () => {
        navigate('/k8s_clusters');
    };

    if (id) {
        const selectedCluster = clustersHook.clusters.find(p => String(p.id) === String(id));

        if (!selectedCluster) {
            if (clustersHook.loading) {
                return <ResourceLoading message="Loading Kubernetes cluster..." />;
            }
            return (
                <ResourceNotFound
                    title="Kubernetes Cluster Not Found"
                    description="The requested Kubernetes cluster could not be found or may have been deleted."
                    onBack={handleBack}
                />
            );
        }

        return (
            <ServiceView
                context={context}
                selectedClusterId={selectedCluster.id}
                selectedCluster={selectedCluster}
                onBack={handleBack}
                clustersHook={clustersHook}
            />
        );
    }

    return (
        <ListingView
            context={context}
            clustersHook={clustersHook}
            onSelectCluster={handleSelectCluster}
        />
    );
};

export default K8sClustersPage;
