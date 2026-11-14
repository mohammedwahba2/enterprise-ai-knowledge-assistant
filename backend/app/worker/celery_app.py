from celery import Celery

from app.core.config import broker_url, get_settings

settings = get_settings()

celery_app = Celery("knowledge", broker=broker_url(settings), include=["app.worker.tasks"])
celery_app.conf.update(
    task_default_queue="ingest",
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    task_acks_late=False,  # a crashed worker must not redeliver a poison document forever;
    worker_prefetch_multiplier=1,  # the sweeper re-queues lost work with a bounded attempt count
    task_time_limit=900,
    task_soft_time_limit=840,
    worker_max_tasks_per_child=50,  # native parsers: recycle children regularly
    broker_connection_retry_on_startup=True,
    timezone="UTC",
    beat_schedule={
        "requeue-stuck-documents": {"task": "knowledge.requeue_stuck", "schedule": 60.0},
        "requeue-transient-failures": {"task": "knowledge.requeue_transient", "schedule": 120.0},
        "purge-deleted-objects": {"task": "knowledge.purge_deleted", "schedule": 300.0},
        "purge-orphan-prefixes": {"task": "knowledge.purge_orphans", "schedule": 3600.0},
    },
)
