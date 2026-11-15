import React from 'react';
import { useHiveMetastore } from '../../hooks/useResources';
import PlatformResourcePage from '../../components/PlatformResourcePage';
import ListingView from './ListingView';
import ServiceView from './ServiceView';

const HiveMetastorePage = () => (
    <PlatformResourcePage
        useResourceHook={useHiveMetastore}
        resourcePropName="hms"
        basePath="/platform/hive-metastore"
        ListingView={ListingView}
        ServiceView={ServiceView}
        notFoundTitle="Hive Metastore Deployment Not Found"
    />
);

export default HiveMetastorePage;
