"""Celery tasks for Garmin synchronization."""
from __future__ import annotations

import logging

from ..worker import celery_app

logger = logging.getLogger("labx.tasks.garmin")


@celery_app.task(
    name="labx.garmin.sync_user",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
    soft_time_limit=300,  # 5 min soft limit
    time_limit=360,        # 6 min hard limit
)
def sync_garmin_user(self, user_id: str) -> dict:
    """Download and store Garmin activities for a user.

    Called after login or manual trigger. Uses its own DB session
    (not injected) so it's safe to run in a Celery worker process.
    """
    logger.info("Garmin sync start user_id=%s attempt=%d", user_id, self.request.retries)
    try:
        from ..garmin_pull_service import background_sync_user
        background_sync_user(user_id)
        logger.info("Garmin sync done user_id=%s", user_id)
        return {"status": "ok", "user_id": user_id}
    except Exception as exc:
        logger.warning("Garmin sync error user_id=%s: %s", user_id, exc)
        raise self.retry(exc=exc)
