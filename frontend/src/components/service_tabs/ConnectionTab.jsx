// SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
// SPDX-License-Identifier: AGPLv3+

import React from 'react';
import { Zap } from 'lucide-react';
import PageLayout from '../PageLayout';

/**
 * Common "Connection & Access" tab for service views.
 * Shows a deployment empty state when the service is not active, otherwise renders connection details.
 */
const ConnectionTab = ({
    isActive,
    onDeploy,
    notDeployedTitle = 'Cluster Not Deployed',
    notDeployedDescription = 'Deploy the cluster to see connection details and access endpoints.',
    deployButtonText = 'DEPLOY CLUSTER',
    renderContent,
    children,
}) => {
    return (
        <div className="dxc-connection-tab space-y-6 animate-in fade-in duration-500">
            {!isActive ? (
                <PageLayout.EmptyState
                    icon={<Zap size={40} />}
                    title={notDeployedTitle}
                    description={notDeployedDescription}
                    className="p-12 bg-slate-50/50 dark:bg-slate-950/20"
                >
                    <div className="flex justify-center w-full">
                        <button
                            type="button"
                            onClick={onDeploy}
                            className="dxc-deploy-btn dxc-btn-primary px-8 py-3 flex items-center justify-center gap-2 text-base mt-6"
                        >
                            <Zap size={18} /> {deployButtonText}
                        </button>
                    </div>
                </PageLayout.EmptyState>
            ) : (
                renderContent ? renderContent() : children
            )}
        </div>
    );
};

export default ConnectionTab;
