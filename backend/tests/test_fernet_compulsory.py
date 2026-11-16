# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

import pytest
from unittest.mock import patch
from citadel.config import settings
from citadel.crypto import EncryptionError


@pytest.mark.asyncio
async def test_lifespan_fails_missing_key():
    """Verify that lifespan fails if the Fernet key is missing."""
    from citadel.app import lifespan
    
    with patch.object(settings, "fernet_key", None):
        with pytest.raises(EncryptionError, match="No encryption key configured"):
            async with lifespan(None):
                pass


@pytest.mark.asyncio
async def test_lifespan_fails_invalid_key():
    """Verify that lifespan fails if the Fernet key is invalid."""
    from citadel.app import lifespan
    
    with patch.object(settings, "fernet_key", "invalid-key-not-base64-or-short"):
        with pytest.raises(EncryptionError, match="Invalid encryption key"):
            async with lifespan(None):
                pass


def test_celery_worker_init_fails_missing_key():
    """Verify that Celery worker init fails if the Fernet key is missing."""
    from citadel.celery_app import check_fernet_on_worker_init
    
    with patch.object(settings, "fernet_key", None):
        with pytest.raises(EncryptionError, match="No encryption key configured"):
            check_fernet_on_worker_init()


def test_celery_beat_init_fails_invalid_key():
    """Verify that Celery beat init fails if the Fernet key is invalid."""
    from citadel.celery_app import check_fernet_on_beat_init
    
    with patch.object(settings, "fernet_key", "invalid-key-not-base64-or-short"):
        with pytest.raises(EncryptionError, match="Invalid encryption key"):
            check_fernet_on_beat_init()
