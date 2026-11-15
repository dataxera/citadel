/*
SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
SPDX-License-Identifier: AGPLv3+
*/

import React from 'react';
import { useDoris } from '../../hooks/useResources';
import PlatformResourcePage from '../../components/PlatformResourcePage';
import ListingView from './ListingView';
import ServiceView from './ServiceView';

const DorisPage = () => (
    <PlatformResourcePage
        useResourceHook={useDoris}
        resourcePropName="doris"
        basePath="/platform/doris"
        ListingView={ListingView}
        ServiceView={ServiceView}
        notFoundTitle="Apache Doris Cluster Not Found"
    />
);

export default DorisPage;
