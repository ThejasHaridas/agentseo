"""Celery worker for long-running audits.

Run on Windows with the solo pool:  uv run celery -A app.worker worker --pool=solo --loglevel=info
"""

from celery import Celery

from app.config import settings
from app.pipeline import run_audit

celery_app = Celery("agentrank", broker=settings.redis_url, backend=settings.redis_url)


@celery_app.task(name="agentrank.run_audit")
def run_audit_task(audit_id: str) -> None:
    run_audit(audit_id)
