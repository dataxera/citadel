import React from 'react';
import { useTrino } from '../../hooks/useResources';
import PlatformResourcePage from '../../components/PlatformResourcePage';
import ListingView from './ListingView';
import ServiceView from './ServiceView';

const TrinoPage = () => (
    <PlatformResourcePage
        useResourceHook={useTrino}
        resourcePropName="trino"
        basePath="/platform/trino"
        ListingView={ListingView}
        ServiceView={ServiceView}
        notFoundTitle="Trino Cluster Not Found"
    />
);

export default TrinoPage;
