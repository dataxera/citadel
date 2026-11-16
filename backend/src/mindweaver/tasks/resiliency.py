# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

import asyncio
import contextlib
import logging
import time
from typing import Awaitable, Callable, TypeVar

import redis.asyncio as aioredis

from mindweaver.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

_LOCK_PREFIX = "mw:task:lock:"
_memory_locks: dict[str, float] = {}


def _get_redis_client() -> aioredis.Redis:
    """Create an async Redis client using the configured Celery broker URL."""
    return aioredis.from_url(
        settings.celery_broker_url,
        socket_connect_timeout=1.0,
        socket_timeout=1.0,
        decode_responses=True,
    )


def clear_memory_locks() -> None:
    """Clear in-memory fallback task locks (primarily for unit tests)."""
    _memory_locks.clear()


async def acquire_task_lock(resource_key: str, ttl: int = 120) -> bool:
    """Acquire an exclusive distributed lock for a background task resource key."""
    lock_key = f"{_LOCK_PREFIX}{resource_key}"
    client = None
    try:
        client = _get_redis_client()
        return bool(await client.set(lock_key, "1", nx=True, ex=ttl))
    except Exception as e:
        logger.debug(
            f"Redis unavailable for task lock {resource_key}, using in-memory fallback: {e}"
        )
        now = time.monotonic()
        exp = _memory_locks.get(lock_key)
        if exp and exp > now:
            return False
        _memory_locks[lock_key] = now + ttl
        return True
    finally:
        if client is not None:
            with contextlib.suppress(Exception):
                await client.aclose()


async def refresh_task_lock(resource_key: str, ttl: int = 120) -> None:
    """Extend the TTL of an existing distributed task lock."""
    lock_key = f"{_LOCK_PREFIX}{resource_key}"
    client = None
    try:
        client = _get_redis_client()
        await client.expire(lock_key, ttl)
    except Exception:
        if lock_key in _memory_locks:
            _memory_locks[lock_key] = time.monotonic() + ttl
    finally:
        if client is not None:
            with contextlib.suppress(Exception):
                await client.aclose()


async def release_task_lock(resource_key: str) -> None:
    """Release a distributed lock for a background task resource key."""
    lock_key = f"{_LOCK_PREFIX}{resource_key}"
    client = None
    try:
        client = _get_redis_client()
        await client.delete(lock_key)
    except Exception:
        _memory_locks.pop(lock_key, None)
    finally:
        if client is not None:
            with contextlib.suppress(Exception):
                await client.aclose()


async def is_task_locked(resource_key: str) -> bool:
    """Return True if a distributed lock is currently active for the resource key."""
    lock_key = f"{_LOCK_PREFIX}{resource_key}"
    client = None
    try:
        client = _get_redis_client()
        return bool(await client.exists(lock_key))
    except Exception:
        now = time.monotonic()
        exp = _memory_locks.get(lock_key)
        if exp and exp > now:
            return True
        _memory_locks.pop(lock_key, None)
        return False
    finally:
        if client is not None:
            with contextlib.suppress(Exception):
                await client.aclose()


async def run_with_lock_heartbeat(
    resource_key: str,
    coro_fn: Callable[[], Awaitable[T]],
    ttl: int = 120,
    heartbeat_interval: int = 30,
) -> T:
    """Execute an async callable while periodically refreshing its distributed lock."""
    stop_event = asyncio.Event()

    async def _heartbeat():
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=heartbeat_interval)
            except asyncio.TimeoutError:
                await refresh_task_lock(resource_key, ttl=ttl)

    hb_task = asyncio.create_task(_heartbeat())
    try:
        return await coro_fn()
    finally:
        stop_event.set()
        hb_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await hb_task
