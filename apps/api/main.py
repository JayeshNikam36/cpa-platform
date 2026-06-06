from dotenv import load_dotenv

load_dotenv()

from typing import Dict  # noqa: E402
import os  # noqa: E402

import sentry_sdk  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from supabase import Client, create_client  # noqa: E402
from routers.auth import router as auth_router  # noqa: E402


sentry_sdk.init(dsn=os.environ.get("SENTRY_DSN", ""), traces_sample_rate=0.1)

supabase: Client = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_SERVICE_KEY"),
)

app = FastAPI(title="CloseMind API", version="0.1.0")
app.include_router(auth_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


@app.get("/health")
async def health():
    try:
        result = supabase.table("firms").select("id").limit(1).execute()
        return {"status": "ok", "db": "connected"}
    except Exception as e:
        return {"status": "ok", "db": "unreachable", "error": str(e)}

