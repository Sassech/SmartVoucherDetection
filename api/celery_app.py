"""Celery application instance.

Broker and result backend both use Redis (same instance, different key prefix).
For tests: set CELERY_TASK_ALWAYS_EAGER=True in environment or conftest.

The `celery:` key prefix is implicit from the default Celery task result backend
naming — no explicit key_prefix parameter needed. Task results are stored as
`celery-task-meta-{task_id}` by default.

Decisiones de diseno:
- `task_always_eager=True` en tests via monkeypatch — no broker en CI.
- `result_expires=3600` — 1 hora por defecto (suficiente para polling manual).
- `task_track_started=True` — permite ver STARTED state en el poller.
"""

from celery import Celery
from config import settings

celery_app = Celery(
    "smartvoucher",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=3600,  # 1 hour
    task_track_started=True,
)
