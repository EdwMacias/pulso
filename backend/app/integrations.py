from fastapi import APIRouter, Depends

from .config import get_settings
from .dependencies import current_user
from .models import User


router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("/status")
def integrations_status(_: User = Depends(current_user)):
    settings = get_settings()
    return {
        "groq": {"configured": bool(settings.groq_api_key)},
        "whatsapp": {
            "configured": settings.whatsapp_configured,
            "available": settings.whatsapp_configured,
        },
        "tts": {"configured": bool(settings.tts_api_key), "available": False},
    }
