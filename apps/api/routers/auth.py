import os
import hmac
import hashlib
import base64
import httpx
from datetime import datetime, timedelta
from uuid import UUID
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from cryptography.fernet import Fernet
from dotenv import load_dotenv

from database import supabase

load_dotenv()

router = APIRouter(prefix="/auth", tags=["auth"])

# Initialize Fernet encryption using the key from environment
FERNET_KEY = os.environ.get("FERNET_KEY", "")
fernet = Fernet(FERNET_KEY.encode()) if FERNET_KEY else None

QBO_CLIENT_ID = os.environ.get("QBO_CLIENT_ID", "")
QBO_CLIENT_SECRET = os.environ.get("QBO_CLIENT_SECRET", "")
QBO_REDIRECT_URI = os.environ.get(
    "QBO_REDIRECT_URI", "http://localhost:8000/auth/qbo/callback"
)
QBO_SCOPE = "com.intuit.quickbooks.accounting"
QBO_AUTH_URL = "https://appcenter.intuit.com/connect/oauth2"
QBO_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"


def _basic_auth_header() -> str:
    credentials = base64.b64encode(
        f"{QBO_CLIENT_ID}:{QBO_CLIENT_SECRET}".encode()
    ).decode()
    return f"Basic {credentials}"


async def _exchange_tokens(data: dict[str, str]) -> dict[str, object]:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            QBO_TOKEN_URL,
            headers={
                "Authorization": _basic_auth_header(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data=data,
        )
        response.raise_for_status()
        return response.json()


@router.get("/qbo/connect")
async def qbo_connect(firm_id: str) -> RedirectResponse:
    if not QBO_CLIENT_ID:
        raise HTTPException(status_code=500, detail="QuickBooks OAuth is not configured")

    params = {
        "client_id": QBO_CLIENT_ID,
        "response_type": "code",
        "scope": QBO_SCOPE,
        "redirect_uri": QBO_REDIRECT_URI,
        "state": firm_id,
    }
    auth_url = f"{QBO_AUTH_URL}?{urlencode(params)}"
    return RedirectResponse(url=auth_url)


@router.get("/qbo/callback")
async def qbo_callback(code: str, state: str, realmId: str) -> RedirectResponse:
    if fernet is None:
        raise HTTPException(status_code=500, detail="Encryption is not configured")

    try:
        tokens = await _exchange_tokens(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": QBO_REDIRECT_URI,
            }
        )

        access_token = str(tokens["access_token"])
        refresh_token = str(tokens["refresh_token"])
        expires_in = int(tokens["expires_in"])

        encrypted_access = fernet.encrypt(access_token.encode()).decode()
        encrypted_refresh = fernet.encrypt(refresh_token.encode()).decode()
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

        supabase.table("firms").update(
            {
                "qbo_realm_id": realmId,
                "qbo_access_token": encrypted_access,
                "qbo_refresh_token": encrypted_refresh,
                "qbo_token_expires_at": expires_at.isoformat(),
            }
        ).eq("id", state).execute()

        return RedirectResponse(url="http://localhost:3000/dashboard?connected=true")
    except httpx.HTTPStatusError:
        raise HTTPException(
            status_code=400, detail="Failed to exchange authorization code"
        )
    except Exception:
        raise HTTPException(status_code=500, detail="QuickBooks connection failed")


@router.get("/qbo/refresh")
async def qbo_refresh(firm_id: str) -> dict[str, str]:
    if fernet is None:
        raise HTTPException(status_code=500, detail="Encryption is not configured")

    try:
        result = (
            supabase.table("firms")
            .select("qbo_refresh_token")
            .eq("id", firm_id)
            .single()
            .execute()
        )

        encrypted_refresh = result.data.get("qbo_refresh_token")
        if not encrypted_refresh:
            raise HTTPException(status_code=404, detail="Firm or refresh token not found")

        refresh_token = fernet.decrypt(str(encrypted_refresh).encode()).decode()

        tokens = await _exchange_tokens(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            }
        )

        access_token = str(tokens["access_token"])
        new_refresh_token = str(tokens.get("refresh_token", refresh_token))
        expires_in = int(tokens["expires_in"])

        encrypted_access = fernet.encrypt(access_token.encode()).decode()
        encrypted_refresh_new = fernet.encrypt(new_refresh_token.encode()).decode()
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

        supabase.table("firms").update(
            {
                "qbo_access_token": encrypted_access,
                "qbo_refresh_token": encrypted_refresh_new,
                "qbo_token_expires_at": expires_at.isoformat(),
            }
        ).eq("id", firm_id).execute()

        return {"status": "refreshed"}
    except HTTPException:
        raise
    except httpx.HTTPStatusError:
        raise HTTPException(status_code=400, detail="Failed to refresh QuickBooks token")
    except Exception:
        raise HTTPException(status_code=500, detail="Token refresh failed")
