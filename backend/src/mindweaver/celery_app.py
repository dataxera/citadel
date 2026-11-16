# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

from celery import Celery
from mindweaver.config import settings

app = Celery(
    "mindweaver",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "mindweaver.tasks.platform_status",
        "mindweaver.tasks.k8s_cluster_status",
        "mindweaver.tasks.project_tasks",
        "mindweaver.tasks.name_tracker",
    ],
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=settings.timezone,
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "scan-and-clean-names-daily": {
            "task": "mindweaver.tasks.name_tracker.scan_and_clean_names_task",
            "schedule": 86400.0,
        },
        "recover-stuck-k8s-sync-tasks": {
            "task": "mindweaver.tasks.k8s_cluster_status.recover_stuck_sync_tasks",
            "schedule": 60.0,
        },
    },
)

from celery.signals import celeryd_init, beat_init, worker_process_init, worker_ready
from mindweaver.crypto import _get_fernet_instance
from mindweaver.fw.model import clear_engine


@celeryd_init.connect
def check_fernet_on_worker_init(**kwargs):
    """Verify Fernet encryption key on worker initialization."""
    _get_fernet_instance()


@beat_init.connect
def check_fernet_on_beat_init(**kwargs):
    """Verify Fernet encryption key on beat scheduler initialization."""
    _get_fernet_instance()


@worker_process_init.connect
def clear_engine_on_worker_process_init(**kwargs):
    """Clear database async engine upon worker process fork to prevent shared connection pool corruption."""
    clear_engine()


@worker_ready.connect
def recover_stuck_tasks_on_worker_ready(**kwargs):
    """Trigger immediate recovery of interrupted background sync tasks when a worker boots."""
    try:
        app.send_task(
            "mindweaver.tasks.k8s_cluster_status.recover_stuck_sync_tasks",
            kwargs={"stale_seconds": 0},
        )
    except Exception:
        pass


if __name__ == "__main__":
    app.start()
