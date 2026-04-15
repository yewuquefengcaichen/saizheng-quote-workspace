from celery import Celery

from app.core.config import settings

broker_url = settings.celery_broker_url or settings.redis_url
result_backend = settings.celery_result_backend or settings.redis_url

celery_app = Celery(
    'saizheng_quote_v2',
    broker=broker_url,
    backend=result_backend,
)

celery_app.conf.update(
    task_default_queue='default',
    task_routes={
        'app.tasks.sync.*': {'queue': 'sync'},
        'app.tasks.image.*': {'queue': 'image'},
        'app.tasks.embedding.*': {'queue': 'embedding'},
        'app.tasks.export.*': {'queue': 'export'},
    },
)

celery_app.autodiscover_tasks(['app.tasks'])
