# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

import time
import logging
import redis.asyncio as aioredis
from citadel.config import settings

logger = logging.getLogger(__name__)

# In-memory fallback when Redis is unavailable (e.g. unit tests)
_memory_cooldowns: dict[str, float] = {}
_memory_locks: dict[str, float] = {}


def _get_redis_client() -> aioredis.Redis:
    """Create an async Redis client using the configured Celery broker URL."""
    return aioredis.from_url(
        settings.celery_broker_url,
        socket_connect_timeout=1.0,
        socket_timeout=1.0,
        decode_responses=True,
    )


async def _try_acquire_cooldown_and_check_lock(
    resource_key: str, cooldown_seconds: int
) -> bool:
    """
    Atomically check if an in-flight lock exists and acquire a cooldown key.
    Returns True if a new poll should be scheduled, False if deduplicated.
    """
    cooldown_key = f"mw:poll:cooldown:{resource_key}"
    lock_key = f"mw:poll:lock:{resource_key}"

    client = None
    try:
        client = _get_redis_client()
        if await client.exists(lock_key):
            return False
        acquired = await client.set(cooldown_key, "1", nx=True, ex=cooldown_seconds)
        return bool(acquired)
    except Exception as e:
        logger.debug(f"Redis unavailable for poll coordination, using in-memory fallback: {e}")
        now = time.monotonic()
        lock_exp = _memory_locks.get(lock_key)
        if lock_exp and lock_exp > now:
            return False
        cd_exp = _memory_cooldowns.get(cooldown_key)
        if cd_exp and cd_exp > now:
            return False
        _memory_cooldowns[cooldown_key] = now + cooldown_seconds
        return True
    finally:
        if client is not None:
            try:
                await client.aclose()
            except Exception:
                pass


async def acquire_poll_lock(resource_key: str) -> bool:
    """Acquire an in-flight poll lock for the given resource key."""
    lock_key = f"mw:poll:lock:{resource_key}"
    ttl = settings.status_polling_expiry
    client = None
    try:
        client = _get_redis_client()
        return bool(await client.set(lock_key, "1", nx=True, ex=ttl))
    except Exception:
        now = time.monotonic()
        lock_exp = _memory_locks.get(lock_key)
        if lock_exp and lock_exp > now:
            return False
        _memory_locks[lock_key] = now + ttl
        return True
    finally:
        if client is not None:
            try:
                await client.aclose()
            except Exception:
                pass


async def release_poll_lock(resource_key: str) -> None:
    """Release an in-flight poll lock for the given resource key."""
    lock_key = f"mw:poll:lock:{resource_key}"
    client = None
    try:
        client = _get_redis_client()
        await client.delete(lock_key)
    except Exception:
        _memory_locks.pop(lock_key, None)
    finally:
        if client is not None:
            try:
                await client.aclose()
            except Exception:
                pass


async def schedule_platform_poll(service_class_name: str, platform_id: int) -> bool:
    """
    Schedule a background platform status poll if not recently polled or in-flight.
    Returns True if a task was enqueued, False if deduplicated or failed.
    """
    resource_key = f"platform:{service_class_name}:{platform_id}"
    should_poll = await _try_acquire_cooldown_and_check_lock(
        resource_key, settings.status_polling_interval
    )
    if not should_poll:
        return False

    try:
        from citadel.tasks.platform_status import poll_platform_status

        poll_platform_status.apply_async(
            args=[service_class_name, platform_id],
            expires=settings.status_polling_expiry,
        )
        return True
    except Exception as e:
        logger.debug(f"Failed to enqueue poll_platform_status for {resource_key}: {e}")
        return False


async def schedule_k8s_cluster_poll(k8s_cluster_id: int) -> bool:
    """
    Schedule a background K8s cluster status poll if not recently polled or in-flight.
    Returns True if a task was enqueued, False if deduplicated or failed.
    """
    resource_key = f"k8s_cluster:{k8s_cluster_id}"
    should_poll = await _try_acquire_cooldown_and_check_lock(
        resource_key, settings.status_polling_interval
    )
    if not should_poll:
        return False

    try:
        from citadel.tasks.k8s_cluster_status import poll_k8s_cluster_status

        poll_k8s_cluster_status.apply_async(
            args=[k8s_cluster_id],
            expires=settings.status_polling_expiry,
        )
        return True
    except Exception as e:
        logger.debug(f"Failed to enqueue poll_k8s_cluster_status for {resource_key}: {e}")
        return False
