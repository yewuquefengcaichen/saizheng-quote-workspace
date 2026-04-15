from app.core.celery_app import celery_app


@celery_app.task(name='app.tasks.sync.ping')
def ping_sync_task() -> dict[str, str]:
    return {'status': 'ok', 'queue': 'sync'}
