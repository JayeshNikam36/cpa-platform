import os
import time
import logging
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from typing import Any

from celery import shared_task
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

from workers.celery_app import celery_app
from services.qbo_auth import qbo_auth_service
from database import supabase


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=300,
    name="workers.ingestion.ingest_client_transactions",
)
def ingest_client_transactions(
    self: Any, firm_id: str, client_id: str, period_month: str
) -> dict[str, str | int]:
    """
    Pulls all transactions for a single client from QBO for the given month.
    period_month format: YYYY-MM-01 (first day of the month)
    """
    logger.info(f"Starting ingestion for client {client_id}")

    access_token = qbo_auth_service.get_valid_access_token(firm_id)

    result = (
        supabase.table("clients")
        .select("qbo_realm_id")
        .eq("id", client_id)
        .execute()
    )
    realm_id = result.data[0]["qbo_realm_id"]

    start_date = period_month
    from datetime import timedelta

    start = datetime.strptime(period_month, "%Y-%m-%d")
    if start.month == 12:
        end_date = start.replace(year=start.year + 1, month=1, day=1) - timedelta(
            days=1
        )
    else:
        end_date = start.replace(month=start.month + 1, day=1) - timedelta(days=1)
    end_date_str = end_date.strftime("%Y-%m-%d")

    import httpx

    transaction_types_queries = [
        "Purchase", "SalesReceipt", "Invoice",
        "Payment", "Transfer", "Bill",
        "BillPayment", "Deposit", "JournalEntry"
    ]

    all_transactions = []

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }

    for txn_type in transaction_types_queries:
        query = f"SELECT * FROM {txn_type} WHERE TxnDate >= '{start_date}' AND TxnDate <= '{end_date_str}'"

        url = f"https://sandbox-quickbooks.api.intuit.com/v3/company/{realm_id}/query"

        response = httpx.get(
            url,
            headers=headers,
            params={"query": query, "minorversion": "65"}
        )

        if response.status_code == 200:
            data = response.json()
            query_response = data.get("QueryResponse", {})
            txns = query_response.get(txn_type, [])
            for txn in txns:
                txn["_type"] = txn_type
            all_transactions.extend(txns)
            logger.info(f"Got {len(txns)} {txn_type} transactions")
        elif response.status_code == 400:
            logger.info(f"Skipping {txn_type} - not supported")
            continue
        else:
            logger.error(f"QBO error for {txn_type}: {response.status_code}")

        time.sleep(0.2)

    for txn in all_transactions:
        amount = Decimal(str(txn.get("TotalAmt", txn.get("Amount", "0"))))

        description = txn.get("PrivateNote", txn.get("Memo", ""))

        vendor_name = ""
        if "EntityRef" in txn:
            vendor_name = txn["EntityRef"].get("name", "")
        elif "VendorRef" in txn:
            vendor_name = txn["VendorRef"].get("name", "")
        elif "CustomerRef" in txn:
            vendor_name = txn["CustomerRef"].get("name", "")

        row = {
            "firm_id": firm_id,
            "client_id": client_id,
            "qbo_txn_id": f"{txn['_type']}_{txn['Id']}",
            "txn_date": txn.get("TxnDate", start_date),
            "amount": str(amount),
            "description": description,
            "vendor_name": vendor_name,
            "raw_category": txn.get("_type", ""),
            "reconciliation_status": "pending",
            "period_month": period_month,
        }

        supabase.table("transactions").upsert(
            row,
            on_conflict="qbo_txn_id,client_id",
        ).execute()

        time.sleep(0.05)

    pkg = (
        supabase.table("close_packages")
        .select("id")
        .eq("client_id", client_id)
        .eq("period_month", period_month)
        .execute()
    )

    if pkg.data:
        supabase.table("close_packages").update({"status": "ingested"}).eq(
            "id", pkg.data[0]["id"]
        ).execute()

    logger.info(
        f"Ingested {len(all_transactions)} transactions for client {client_id}"
    )
    return {"status": "success", "count": len(all_transactions)}


@celery_app.task(name="workers.ingestion.ingest_all_clients")
def ingest_all_clients() -> dict[str, int]:
    """
    Triggered by cron schedule.
    Loops all active clients and dispatches ingest_client_transactions for each.
    Uses current month as the period.
    """
    today = date.today()
    period_month = today.replace(day=1).strftime("%Y-%m-%d")

    result = (
        supabase.table("clients")
        .select("id, firm_id")
        .eq("is_active", True)
        .execute()
    )

    for client in result.data:
        ingest_client_transactions.delay(
            client["firm_id"],
            client["id"],
            period_month,
        )

    logger.info(f"Dispatched ingestion for {len(result.data)} clients")
    return {"dispatched": len(result.data)}
