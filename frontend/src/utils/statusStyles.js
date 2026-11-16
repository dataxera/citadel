/*
SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
SPDX-License-Identifier: AGPLv3+
*/

const VARIANT_DOTS = {
    'dxc-badge-success': 'bg-emerald-500',
    'dxc-badge-warning': 'bg-amber-500',
    'dxc-badge-danger': 'bg-rose-500',
    'dxc-badge-info': 'bg-blue-500',
    'dxc-badge-neutral': 'bg-slate-400',
};

const STATUS_BADGE_MAP = {
    running: 'dxc-badge-success',
    online: 'dxc-badge-success',
    connected: 'dxc-badge-success',
    warning: 'dxc-badge-warning',
    pending: 'dxc-badge-warning',
    stopped: 'dxc-badge-neutral',
    offline: 'dxc-badge-neutral',
    error: 'dxc-badge-danger',
    active: 'dxc-badge-info',
};

/**
 * Returns the shared badge class and status dot class for a given service status.
 *
 * @param {string} [status] - Service status string (e.g. 'online', 'pending', 'error').
 * @returns {{ badge: string, dot: string }}
 */
export function getStatusStyle(status) {
    const normalized = typeof status === 'string' ? status.toLowerCase() : '';
    const badge = STATUS_BADGE_MAP[normalized] || 'dxc-badge-neutral';
    return {
        badge,
        dot: VARIANT_DOTS[badge] || 'bg-slate-400',
    };
}
