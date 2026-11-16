# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

from citadel.celery_app import app


def test_celery_beat_schedule_no_always_on_polling():
    """Verify that always-on status polling tasks are not in beat_schedule."""
    schedule = app.conf.beat_schedule

    assert "poll-all-platforms-15s" not in schedule
    assert "poll-all-k8s-clusters-15s" not in schedule
    assert "scan-and-clean-names-daily" in schedule
