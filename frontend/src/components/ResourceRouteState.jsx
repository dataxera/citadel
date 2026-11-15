/*
SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
SPDX-License-Identifier: AGPLv3+
*/

import React from 'react';
import { RefreshCcw, AlertCircle } from 'lucide-react';

/**
 * Displays a centered loading indicator while a routed resource is being fetched.
 */
export const ResourceLoading = ({ message = 'Loading resource...' }) => (
    <div className="p-12 flex flex-col items-center justify-center space-y-4">
        <RefreshCcw className="animate-spin text-blue-500" size={32} />
        <p className="text-slate-500 text-base font-medium">{message}</p>
    </div>
);

/**
 * Displays a not-found state when a resource ID in the URL does not match any record.
 */
export const ResourceNotFound = ({
    title = 'Resource Not Found',
    description = 'The requested resource could not be found or may have been deleted.',
    onBack,
    backLabel = 'BACK TO LIST',
}) => (
    <div className="p-12 flex flex-col items-center justify-center text-center space-y-4">
        <div className="w-14 h-14 rounded-2xl bg-rose-500/10 text-rose-500 flex items-center justify-center border border-rose-500/20">
            <AlertCircle size={28} />
        </div>
        <div className="space-y-1">
            <h2 className="text-2xl font-bold text-slate-900 dark:text-white">{title}</h2>
            <p className="text-slate-500 dark:text-slate-400 text-sm max-w-md">{description}</p>
        </div>
        {onBack && (
            <button
                type="button"
                onClick={onBack}
                className="mw-btn-secondary px-6 py-2.5 mt-2"
            >
                {backLabel}
            </button>
        )}
    </div>
);
