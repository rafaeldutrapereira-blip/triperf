"""
LabX Celery worker — async task execution.

Usage:
  celery -A api.worker.celery_app worker --loglevel=info -Q default

In tests (APP_ENV=test): tasks run synchronously (task_always_eager=True).
When REDIS_URL is not set: tasks fall back to FastAPI BackgroundTasks.
"""
from __future__ import annotations

import os

from celery import Celery

_BROKER = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_IS_TEST = os.getenv("APP_ENV") == "test"

celery_app = Celery(
    "labx",
    broker=_BROKER,
    backend=_BROKER,
    include=["api.tasks.garmin_tasks"],
)

celery_app.conf.update(
    task_serializer            = "json",
    result_serializer          = "json",
    accept_content             = ["json"],
    task_always_eager          = _IS_TEST,
    task_eager_propagates      = True,
    broker_connection_retry_on_startup = True,
    result_expires             = 3600,
    worker_prefetch_multiplier = 1,    # fair dispatch for long tasks
    task_acks_late             = True,  # ack after task completes, not before
    task_reject_on_worker_lost = True,
    timezone                   = "UTC",
)
