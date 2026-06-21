from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "selection_board",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.document_pipeline"],
)
celery_app.conf.task_default_queue = "selection-board"
celery_app.conf.result_expires = 3600
