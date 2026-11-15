// SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
// SPDX-License-Identifier: AGPLv3+

import React from 'react';
import { useSearchParams } from 'react-router-dom';
import { cn } from '../../utils/cn';

/**
 * Reusable tabbed container for service views.
 * Synchronizes active tab state with the URL `?tab=` query parameter by default,
 * or supports controlled `activeTab` / `onTabChange` props.
 */
const ServiceViewTabs = ({
    darkMode = true,
    tabs = [],
    initialTab,
    defaultTab = 'connect',
    activeTab: controlledActiveTab,
    onTabChange,
    syncUrlParam = true,
    className,
}) => {
    const [searchParams, setSearchParams] = useSearchParams();
    const visibleTabs = tabs.filter((tab) => tab && !tab.hidden);
    const fallbackTab = defaultTab || visibleTabs[0]?.id;

    const urlTab = syncUrlParam ? searchParams.get('tab') : null;
    const rawActiveTab = controlledActiveTab ?? urlTab ?? initialTab ?? fallbackTab;
    const activeTabObj = visibleTabs.find((tab) => tab.id === rawActiveTab) || visibleTabs[0];
    const activeTab = activeTabObj?.id;

    /**
     * Updates the active tab via controlled callback or URL query parameter.
     */
    const setActiveTab = (tabId) => {
        if (onTabChange) {
            onTabChange(tabId);
        }
        if (syncUrlParam) {
            setSearchParams((prev) => {
                const next = new URLSearchParams(prev);
                if (!tabId || tabId === fallbackTab) {
                    next.delete('tab');
                } else {
                    next.set('tab', tabId);
                }
                return next;
            }, { replace: true });
        }
    };

    if (visibleTabs.length === 0) {
        return null;
    }

    return (
        <div className={cn('mw-service-tabs space-y-6', className)}>
            <div
                className={cn(
                    'mw-service-tab-bar flex items-center gap-4 border-b p-1 overflow-x-auto',
                    darkMode ? 'border-slate-800' : 'border-slate-200'
                )}
                role="tablist"
            >
                {visibleTabs.map((tab) => {
                    const isActive = activeTab === tab.id;
                    return (
                        <button
                            key={tab.id}
                            type="button"
                            role="tab"
                            aria-selected={isActive}
                            onClick={() => setActiveTab(tab.id)}
                            className={cn(
                                'mw-service-tab-btn px-4 py-2 text-sm font-bold uppercase tracking-widest transition-all border-b-2 whitespace-nowrap',
                                isActive
                                    ? 'border-blue-500 text-blue-500'
                                    : 'border-transparent text-slate-500 hover:text-slate-900 dark:hover:text-slate-100'
                            )}
                        >
                            {tab.label}
                        </button>
                    );
                })}
            </div>

            <div className="mw-service-tab-content" role="tabpanel">
                {activeTabObj?.render
                    ? activeTabObj.render({ activeTab, setActiveTab })
                    : activeTabObj?.content}
            </div>
        </div>
    );
};

export default ServiceViewTabs;
