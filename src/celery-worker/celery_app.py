"""
Celery application configuration for video stream processing
"""

from celery import Celery
from config.settings import settings

# Create Celery app
celery_app = Celery(
    'camera_stream_worker',
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=['tasks.camera_tasks']
)

# Celery configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=None,  # No time limit - tasks control their own lifecycle
    task_soft_time_limit=None,  # No soft time limit
    worker_prefetch_multiplier=1,  # Process one task at a time per worker
    worker_max_tasks_per_child=50,  # Restart worker after 50 tasks to prevent memory leaks
    task_acks_late=True,  # Acknowledge task after completion, not before
    task_reject_on_worker_lost=True,  # Reject task if worker dies
    worker_disable_rate_limits=True,
    task_routes={
        'tasks.start_process_camera_stream': {'queue': 'camera_streams'},
        'tasks.stop_process_camera_stream': {'queue': 'camera_streams'},
    },
)

