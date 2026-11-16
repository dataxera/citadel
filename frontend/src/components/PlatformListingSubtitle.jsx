/*
SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
SPDX-License-Identifier: AGPLv3+
*/

import React from 'react';
import { Briefcase, Activity } from 'lucide-react';
import { cn } from '../utils/cn';

/**
 * Shared subtitle row for platform service listings, displaying the project pill,
 * deployment status badge, and active indicator.
 */
const PlatformListingSubtitle = ({ platform, state = {}, projects = [] }) => {
    const project = projects.find((p) => String(p.id) === String(platform.project_id));
    const projectLabel = project ? (project.title || project.name) : `Project #${platform.project_id}`;

    return (
        <div className="flex items-center gap-4 flex-wrap">
            <div
                className="mw-project-pill inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-slate-500/10 text-slate-600 dark:text-slate-300 border border-slate-500/20"
                title={`Project: ${projectLabel}`}
            >
                <Briefcase size={12} />
                <span>{projectLabel}</span>
            </div>
            <div className={cn(
                "flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[10px] font-bold uppercase border",
                state.status === 'online' ? "bg-emerald-500/10 text-emerald-500 border-emerald-500/20" :
                    state.status === 'error' ? "bg-rose-500/10 text-rose-500 border-rose-500/20" :
                        "bg-slate-500/10 text-slate-400 border-slate-500/20"
            )}>
                <div className={cn(
                    "w-1.5 h-1.5 rounded-full",
                    state.status === 'online' ? "bg-emerald-500" :
                        state.status === 'error' ? "bg-rose-500" :
                            "bg-slate-400"
                )} />
                {state.status || 'unknown'}
            </div>
            {state.active && (
                <div className="flex items-center gap-1 bg-blue-500/10 text-blue-500 border border-blue-500/20 px-2 py-0.5 rounded-md text-[10px] font-bold uppercase">
                    <Activity size={10} />
                    Active
                </div>
            )}
        </div>
    );
};

export default PlatformListingSubtitle;
