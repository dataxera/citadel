import React from 'react';
import { usePgSql } from '../../hooks/useResources';
import PlatformResourcePage from '../../components/PlatformResourcePage';
import ListingView from './ListingView';
import ServiceView from './ServiceView';

const PgSqlPage = () => (
    <PlatformResourcePage
        useResourceHook={usePgSql}
        resourcePropName="pgsql"
        basePath="/platform/pgsql"
        ListingView={ListingView}
        ServiceView={ServiceView}
        notFoundTitle="PostgreSQL Cluster Not Found"
    />
);

export default PgSqlPage;
