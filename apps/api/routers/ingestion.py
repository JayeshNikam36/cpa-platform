from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from workers.ingestion import ingest_client_transactions

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


class IngestRequest(BaseModel):
    firm_id: str
    client_id: str
    period_month: str


@router.post("/trigger")
async def trigger_ingestion(request: IngestRequest) -> dict[str, str]:
    try:
        datetime.strptime(request.period_month, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="period_month must be in YYYY-MM-DD format",
        )

    result = ingest_client_transactions.delay(
        request.firm_id,
        request.client_id,
        request.period_month,
    )

    return {"status": "queued", "task_id": result.id}
