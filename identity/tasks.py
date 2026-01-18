
from celery import shared_task
from django.core.management import call_command

@shared_task
def purge_data():
    """
    Celery task wraps the management command to purge expired data.
    This allows it to be scheduled via Celery Beat.
    """
    call_command('purge_expired_data')
