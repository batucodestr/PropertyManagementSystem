"""Celery uygulaması.

Çalıştırma (backend/ klasöründe):
    celery -A pms worker -l info        # Windows'ta: --pool=solo ekle
    celery -A pms beat -l info
Periyodik görevler settings.CELERY_BEAT_SCHEDULE içinde tanımlıdır.
"""
import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pms.settings')

app = Celery('pms')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
