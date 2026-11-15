// SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
// SPDX-License-Identifier: AGPLv3+

import React from 'react';
import { Zap } from 'lucide-react';
import { cn } from '../../utils/cn';
import DynamicForm from '../DynamicForm';

/**
 * Common "Configuration" tab for service views.
 * Wraps DynamicForm in edit mode inside a standard panel layout.
 */
const ConfigurationTab = ({
    darkMode = true,
    entityPath,
    initialData,
    title = 'Configuration',
    icon = Zap,
    onCancel,
    onSuccess,
}) => {
    const IconComponent = icon;
    return (
        <div className="mw-configuration-tab mw-panel animate-in fade-in slide-in-from-top-4 duration-500">
            <div
                className={cn(
                    'p-4 border-b flex items-center justify-between',
                    darkMode ? 'border-slate-800 bg-slate-950/30' : 'border-slate-200 bg-slate-50'
                )}
            >
                <div className="flex items-center gap-3">
                    <div className="p-2 bg-indigo-500/10 text-indigo-400 rounded-lg">
                        <IconComponent size={18} />
                    </div>
                    <h4 className="text-base font-bold tracking-wider leading-none text-slate-900 dark:text-white">
                        {title}
                    </h4>
                </div>
            </div>
            <div className="p-8">
                <DynamicForm
                    entityPath={entityPath}
                    mode="edit"
                    initialData={initialData}
                    darkMode={darkMode}
                    onCancel={onCancel}
                    onSuccess={onSuccess}
                />
            </div>
        </div>
    );
};

export default ConfigurationTab;
