import os
from celery import Celery

# Get Redis URL from environment or default to local (for safety)
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://redis:6379/0")

app = Celery(
    "worker",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    # CRITICAL FIX: This tells Celery to look in 'tasks.py' for @task decorators
    include=["tasks"]
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Optional: Ensure tasks are not lost if the worker crashes
    task_acks_late=True,
)