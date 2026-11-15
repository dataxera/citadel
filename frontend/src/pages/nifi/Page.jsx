// SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
// SPDX-License-Identifier: AGPLv3+

import React from 'react';
import { useNifi } from '../../hooks/useResources';
import PlatformResourcePage from '../../components/PlatformResourcePage';
import ListingView from './ListingView';
import ServiceView from './ServiceView';

/**
 * NiFiPage is the main container page component for Apache NiFi platform service in the frontend.
 * It delegates URL-based routing between the listing and service views to PlatformResourcePage.
 */
const NiFiPage = () => (
    <PlatformResourcePage
        useResourceHook={useNifi}
        resourcePropName="nifi"
        basePath="/platform/nifi"
        ListingView={ListingView}
        ServiceView={ServiceView}
        notFoundTitle="NiFi Cluster Not Found"
    />
);

export default NiFiPage;
