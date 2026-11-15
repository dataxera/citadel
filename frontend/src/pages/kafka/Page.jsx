// SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
// SPDX-License-Identifier: AGPLv3+

import React from 'react';
import { useKafka } from '../../hooks/useResources';
import PlatformResourcePage from '../../components/PlatformResourcePage';
import ListingView from './ListingView';
import ServiceView from './ServiceView';

const KafkaPage = () => (
    <PlatformResourcePage
        useResourceHook={useKafka}
        resourcePropName="kafka"
        basePath="/platform/kafka"
        ListingView={ListingView}
        ServiceView={ServiceView}
        notFoundTitle="Kafka Cluster Not Found"
    />
);

export default KafkaPage;
