/*
SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
SPDX-License-Identifier: AGPLv3+
*/

import { useState, useEffect, useCallback } from 'react';
import apiClient from '../services/api';
import { useAuth } from '../providers/AuthProvider';

const DEFAULT_PERMISSIONS = Object.freeze({
    list: false,
    view: false,
    create: false,
    update: false,
    delete: false,
    execute: false,
});

const permissionCache = new Map();
const inFlightRequests = new Map();

/**
 * Fetch and cache collection-level or model-level permissions for a resource service.
 * Fails closed (all false) while loading or if the request fails/returns 403.
 */
export const useResourcePermissions = (entityPath, options = {}) => {
    const { resourceId = null, headers = null, enabled = true } = options;
    const { user } = useAuth() || {};

    const headersKey = headers ? JSON.stringify(headers) : '';
    const userKey = user?.id ?? 'anon';
    const permUrl = entityPath
        ? (resourceId != null ? `${entityPath}/${resourceId}/_permissions` : `${entityPath}/_permissions`)
        : null;
    const cacheKey = permUrl ? `${userKey}:${permUrl}:${headersKey}` : null;

    const [permissions, setPermissions] = useState(() => {
        if (cacheKey && permissionCache.has(cacheKey)) {
            return permissionCache.get(cacheKey);
        }
        return DEFAULT_PERMISSIONS;
    });
    const [loading, setLoading] = useState(() => Boolean(enabled && permUrl && !(cacheKey && permissionCache.has(cacheKey))));

    const fetchPermissions = useCallback(async (force = false) => {
        if (!enabled || !permUrl || !cacheKey) {
            setPermissions(DEFAULT_PERMISSIONS);
            setLoading(false);
            return DEFAULT_PERMISSIONS;
        }

        if (!force && permissionCache.has(cacheKey)) {
            const cached = permissionCache.get(cacheKey);
            setPermissions(cached);
            setLoading(false);
            return cached;
        }

        setLoading(true);
        try {
            let requestPromise = !force ? inFlightRequests.get(cacheKey) : null;
            if (!requestPromise) {
                const config = headers ? { headers } : undefined;
                requestPromise = apiClient
                    .get(permUrl, config)
                    .then((res) => ({ ...DEFAULT_PERMISSIONS, ...(res.data?.data || {}) }))
                    .catch(() => DEFAULT_PERMISSIONS)
                    .finally(() => {
                        inFlightRequests.delete(cacheKey);
                    });
                inFlightRequests.set(cacheKey, requestPromise);
            }
            const resolved = await requestPromise;
            permissionCache.set(cacheKey, resolved);
            setPermissions(resolved);
            return resolved;
        } finally {
            setLoading(false);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [enabled, permUrl, cacheKey, headersKey]);

    useEffect(() => {
        fetchPermissions(false);
    }, [fetchPermissions]);

    const refetch = useCallback(() => fetchPermissions(true), [fetchPermissions]);

    return {
        permissions,
        loading,
        canList: Boolean(permissions.list),
        canView: Boolean(permissions.view),
        canCreate: Boolean(permissions.create),
        canUpdate: Boolean(permissions.update),
        canDelete: Boolean(permissions.delete),
        canExecute: Boolean(permissions.execute),
        refetch,
    };
};

export default useResourcePermissions;
