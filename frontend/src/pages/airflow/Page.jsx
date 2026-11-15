import React from 'react';
import { useAirflow } from '../../hooks/useResources';
import PlatformResourcePage from '../../components/PlatformResourcePage';
import ListingView from './ListingView';
import ServiceView from './ServiceView';

const AirflowPage = () => (
    <PlatformResourcePage
        useResourceHook={useAirflow}
        resourcePropName="airflow"
        basePath="/platform/airflow"
        ListingView={ListingView}
        ServiceView={ServiceView}
        notFoundTitle="Airflow Deployment Not Found"
    />
);

export default AirflowPage;
