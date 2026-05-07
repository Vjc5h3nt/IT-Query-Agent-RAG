"""Admin endpoints for operational tasks (credential refresh, etc.)."""
import hmac
import logging

from fastapi import APIRouter, Header, HTTPException

from app.config import settings
from services.bedrock_client import bedrock_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


def _verify_secret(provided: str | None) -> None:
    expected = settings.admin_refresh_secret
    if not expected:
        raise HTTPException(status_code=503, detail="Admin endpoint disabled: ADMIN_REFRESH_SECRET not configured")
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid admin secret")


@router.post("/refresh-credentials")
async def refresh_credentials(x_admin_secret: str | None = Header(default=None)):
    """Reload .env and rebuild the Bedrock client with current AWS credentials.

    Intended for rotating short-lived SSO tokens without restarting the server.
    Requires the X-Admin-Secret header to match ADMIN_REFRESH_SECRET.
    """
    _verify_secret(x_admin_secret)
    try:
        bedrock_client.refresh()
        return {"status": "refreshed", "region": settings.aws_region, "model": settings.aws_bedrock_model_id}
    except Exception as e:
        logger.exception("Credential refresh failed")
        raise HTTPException(status_code=500, detail=f"Refresh failed: {e}")
