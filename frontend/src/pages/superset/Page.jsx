import React from 'react';
import { useSuperset } from '../../hooks/useResources';
import PlatformResourcePage from '../../components/PlatformResourcePage';
import ListingView from './ListingView';
import ServiceView from './ServiceView';

const SupersetPage = () => (
    <PlatformResourcePage
        useResourceHook={useSuperset}
        resourcePropName="superset"
        basePath="/platform/superset"
        ListingView={ListingView}
        ServiceView={ServiceView}
        notFoundTitle="Superset Deployment Not Found"
    />
);

export default SupersetPage;
