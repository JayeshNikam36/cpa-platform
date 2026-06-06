import os
import ssl
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.environ.get("REDIS_URL", "")

celery_app = Celery(
    "cpa_platform",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["workers.ingestion"]
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
    broker_use_ssl={
        "ssl_cert_reqs": ssl.CERT_NONE
    },
    redis_backend_use_ssl={
        "ssl_cert_reqs": ssl.CERT_NONE
    },
    beat_schedule={
        "ingest-all-clients-monthly": {
            "task": "workers.ingestion.ingest_all_clients",
            "schedule": 3600.0,
        }
    }
)

if __name__ == "__main__":
    celery_app.start()
