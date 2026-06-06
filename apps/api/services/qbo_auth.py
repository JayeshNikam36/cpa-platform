import os
import base64
import httpx
from datetime import datetime, timedelta, timezone
from uuid import UUID

from cryptography.fernet import Fernet
from dotenv import load_dotenv

from database import supabase

load_dotenv()

FERNET_KEY = os.environ.get("FERNET_KEY", "")
fernet = Fernet(FERNET_KEY.encode()) if FERNET_KEY else None

QBO_CLIENT_ID = os.environ.get("QBO_CLIENT_ID", "")
QBO_CLIENT_SECRET = os.environ.get("QBO_CLIENT_SECRET", "")
QBO_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"


class QBOAuthService:
    def __init__(self) -> None:
        self.supabase = supabase

    def _load_firm_tokens(self, firm_id: str) -> dict[str, object]:
        result = (
            self.supabase.table("firms")
            .select("qbo_access_token, qbo_refresh_token, qbo_token_expires_at")
            .eq("id", firm_id)
            .single()
            .execute()
        )
        return result.data

    def _parse_expires_at(self, expires_at: str | None) -> datetime:
        if not expires_at:
            return datetime.min.replace(tzinfo=timezone.utc)

        parsed = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed

    def _basic_auth_header(self) -> str:
        credentials = base64.b64encode(
            f"{QBO_CLIENT_ID}:{QBO_CLIENT_SECRET}".encode()
        ).decode()
        return f"Basic {credentials}"

    def get_valid_access_token(self, firm_id: str) -> str:
        try:
            row = self._load_firm_tokens(firm_id)

            expires_at = self._parse_expires_at(row.get("qbo_token_expires_at"))
            now = datetime.now(timezone.utc)

            if (expires_at - now).total_seconds() < 600:
                self.refresh_tokens(firm_id)
                row = self._load_firm_tokens(firm_id)

            encrypted_access = row.get("qbo_access_token")
            if not encrypted_access:
                raise ValueError("Missing access token")

            return self.decrypt_token(str(encrypted_access))
        except Exception:
            raise Exception("QBO token unavailable")

    def refresh_tokens(self, firm_id: str) -> None:
        row = self._load_firm_tokens(firm_id)

        encrypted_refresh = row.get("qbo_refresh_token")
        if not encrypted_refresh:
            raise Exception("Token refresh failed")

        refresh_token = self.decrypt_token(str(encrypted_refresh))

        with httpx.Client() as client:
            response = client.post(
                QBO_TOKEN_URL,
                headers={
                    "Authorization": self._basic_auth_header(),
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )

        if response.status_code != 200:
            raise Exception("Token refresh failed")

        tokens = response.json()
        access_token = str(tokens["access_token"])
        new_refresh_token = str(tokens.get("refresh_token", refresh_token))
        expires_in = int(tokens["expires_in"])

        encrypted_access = self.encrypt_token(access_token)
        encrypted_refresh_new = self.encrypt_token(new_refresh_token)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        self.supabase.table("firms").update(
            {
                "qbo_access_token": encrypted_access,
                "qbo_refresh_token": encrypted_refresh_new,
                "qbo_token_expires_at": expires_at.isoformat(),
            }
        ).eq("id", firm_id).execute()

    def decrypt_token(self, encrypted_token: str) -> str:
        if fernet is None:
            raise ValueError("Fernet encryption is not configured")
        return fernet.decrypt(encrypted_token.encode()).decode()

    def encrypt_token(self, plain_token: str) -> str:
        if fernet is None:
            raise ValueError("Fernet encryption is not configured")
        return fernet.encrypt(plain_token.encode()).decode()


qbo_auth_service = QBOAuthService()
