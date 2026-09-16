from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import auth, chat, integrations, notifications, preferences, reminders, tasks, whatsapp
from .config import get_settings
from .database import Base, get_engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=get_engine())
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    if settings.cors_origin_list:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "X-CSRF-Token"],
        )
    api_prefix = "/api/v1"
    application.include_router(auth.router, prefix=api_prefix)
    application.include_router(preferences.router, prefix=api_prefix)
    application.include_router(tasks.router, prefix=api_prefix)
    application.include_router(reminders.router, prefix=api_prefix)
    application.include_router(chat.router, prefix=api_prefix)
    application.include_router(integrations.router, prefix=api_prefix)
    application.include_router(notifications.router, prefix=api_prefix)
    application.include_router(whatsapp.router, prefix=api_prefix)

    @application.get("/health", tags=["health"])
    def health():
        return {"status": "ok"}

    return application


app = create_app()
