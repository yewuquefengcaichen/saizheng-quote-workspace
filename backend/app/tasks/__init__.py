from app.tasks.catalog import scrape_mall_sync_task
from app.tasks.embedding import generate_image_embeddings_task
from app.tasks.sync import ping_sync_task

__all__ = ['generate_image_embeddings_task', 'ping_sync_task', 'scrape_mall_sync_task']
