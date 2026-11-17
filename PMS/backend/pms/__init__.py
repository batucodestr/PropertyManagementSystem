# Celery uygulamasını Django ile birlikte yükle; @shared_task'lar bu app'e bağlanır.
from .celery import app as celery_app

__all__ = ('celery_app',)
