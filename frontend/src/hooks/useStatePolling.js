/*
SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
SPDX-License-Identifier: AGPLv3+
*/
import { useEffect, useRef } from 'react';

export const DEFAULT_POLL_INTERVAL_MS = 3000;

/**
 * Polls `callback` every `intervalMs` while `enabled` is true and the browser tab is visible.
 * Immediately invokes `callback` on mount/enable and when the tab becomes visible again.
 */
export const useVisibilityPolling = (callback, enabled, intervalMs = DEFAULT_POLL_INTERVAL_MS) => {
    const callbackRef = useRef(callback);

    useEffect(() => {
        callbackRef.current = callback;
    }, [callback]);

    useEffect(() => {
        if (!enabled) return;

        const runIfVisible = () => {
            if (typeof document === 'undefined' || !document.hidden) {
                callbackRef.current();
            }
        };

        runIfVisible();
        const timer = setInterval(runIfVisible, intervalMs);

        const handleVisibilityChange = () => {
            if (!document.hidden) {
                callbackRef.current();
            }
        };

        if (typeof document !== 'undefined') {
            document.addEventListener('visibilitychange', handleVisibilityChange);
        }

        return () => {
            clearInterval(timer);
            if (typeof document !== 'undefined') {
                document.removeEventListener('visibilitychange', handleVisibilityChange);
            }
        };
    }, [enabled, intervalMs]);
};
