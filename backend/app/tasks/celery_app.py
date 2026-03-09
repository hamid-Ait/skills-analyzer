from celery import Celery
from app.config import settings

celery_app = Celery(
    "people_intelligence",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

celery_app.conf.include = [
    "app.tasks.scrape_task",
    "app.tasks.analyze_task",
    "app.tasks.linkedin_task",
    "app.tasks.google_search_task",
    "app.tasks.resolve_linkedin_task",
]
