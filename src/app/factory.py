"""Factory Ð´Ð»Ñ ÑÐ¾Ð·Ð´Ð°Ð½Ð¸Ñ FastAPI Ð¿Ñ€Ð¸Ð»Ð¾Ð¶ÐµÐ½Ð¸Ñ.

Ð¤ÑƒÐ½ÐºÑ†Ð¸Ñ create_app() ÑÐ¾Ð·Ð´Ð°Ñ‘Ñ‚ Ð¸ Ð½Ð°ÑÑ‚Ñ€Ð°Ð¸Ð²Ð°ÐµÑ‚ FastAPI app:
- ÐŸÐ¾Ð´ÐºÐ»ÑŽÑ‡Ð°ÐµÑ‚ Ð²ÑÐµ Ñ€Ð¾ÑƒÑ‚ÐµÑ€Ñ‹ (admin, webhooks, telegram, health)
- ÐÐ°ÑÑ‚Ñ€Ð°Ð¸Ð²Ð°ÐµÑ‚ Ð°Ð´Ð¼Ð¸Ð½ÐºÑƒ
- ÐŸÐ¾Ð´ÐºÐ»ÑŽÑ‡Ð°ÐµÑ‚ lifecycle manager
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from src.admin import setup_admin
from src.admin.auth import get_admin_secret_key
from src.api.admin import router as admin_router
from src.api.health import router as health_router
from src.api.root import router as root_router
from src.api.telegram import router as telegram_router
from src.api.webhooks import router as webhooks_router
from src.app.lifecycle import ApplicationLifecycle
from src.config.settings import settings
from src.config.yaml_config import yaml_config
from src.utils.logging import get_logger

logger = get_logger(__name__)


def create_app() -> FastAPI:
    """Ð¡Ð¾Ð·Ð´Ð°Ñ‚ÑŒ Ð¸ Ð½Ð°ÑÑ‚Ñ€Ð¾Ð¸Ñ‚ÑŒ FastAPI Ð¿Ñ€Ð¸Ð»Ð¾Ð¶ÐµÐ½Ð¸Ðµ.

    Ð¡Ð¾Ð·Ð´Ð°Ñ‘Ñ‚ FastAPI app Ñ:
    - Lifecycle management (startup/shutdown)
    - Ð’ÑÐµÐ¼Ð¸ API Ñ€Ð¾ÑƒÑ‚ÐµÑ€Ð°Ð¼Ð¸
    - ÐÐ´Ð¼Ð¸Ð½ÐºÐ¾Ð¹

    Returns:
        ÐÐ°ÑÑ‚Ñ€Ð¾ÐµÐ½Ð½Ð¾Ðµ FastAPI Ð¿Ñ€Ð¸Ð»Ð¾Ð¶ÐµÐ½Ð¸Ðµ Ð³Ð¾Ñ‚Ð¾Ð²Ð¾Ðµ Ðº Ð·Ð°Ð¿ÑƒÑÐºÑƒ
    """
    # Ð¡Ð¾Ð·Ð´Ð°Ñ‘Ð¼ lifecycle manager
    lifecycle = ApplicationLifecycle(settings, yaml_config)

    # ÐžÐ¿Ñ€ÐµÐ´ÐµÐ»ÑÐµÐ¼ lifespan context manager
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        """Ð£Ð¿Ñ€Ð°Ð²Ð»ÐµÐ½Ð¸Ðµ Ð¶Ð¸Ð·Ð½ÐµÐ½Ð½Ñ‹Ð¼ Ñ†Ð¸ÐºÐ»Ð¾Ð¼ Ð¿Ñ€Ð¸Ð»Ð¾Ð¶ÐµÐ½Ð¸Ñ.

        Args:
            app: FastAPI Ð¿Ñ€Ð¸Ð»Ð¾Ð¶ÐµÐ½Ð¸Ðµ

        Yields:
            None: ÐŸÑ€Ð¸Ð»Ð¾Ð¶ÐµÐ½Ð¸Ðµ Ñ€Ð°Ð±Ð¾Ñ‚Ð°ÐµÑ‚ Ð¼ÐµÐ¶Ð´Ñƒ startup Ð¸ shutdown
        """
        # Startup
        await lifecycle.startup(app)

        yield

        # Shutdown
        await lifecycle.shutdown()

    # Ð¡Ð¾Ð·Ð´Ð°Ñ‘Ð¼ FastAPI Ð¿Ñ€Ð¸Ð»Ð¾Ð¶ÐµÐ½Ð¸Ðµ
    app = FastAPI(
        title="Just Here",
        description="Telegram-Ð±Ð¾Ñ‚ Ð´Ð»Ñ AI-Ð³ÐµÐ½ÐµÑ€Ð°Ñ†Ð¸Ð¸",
        version="0.1.0",
        lifespan=lifespan,
    )

    # ÐŸÐ¾Ð´ÐºÐ»ÑŽÑ‡Ð°ÐµÐ¼ Ð°Ð´Ð¼Ð¸Ð½ÐºÑƒ (ÐµÑÐ»Ð¸ Ð½Ð°ÑÑ‚Ñ€Ð¾ÐµÐ½Ð°)
    # ÐÐ´Ð¼Ð¸Ð½ÐºÐ° Ð´Ð¾ÑÑ‚ÑƒÐ¿Ð½Ð° Ð¿Ð¾ Ð°Ð´Ñ€ÐµÑÑƒ /admin ÐµÑÐ»Ð¸ Ð·Ð°Ð´Ð°Ð½Ñ‹ ADMIN__USERNAME Ð¸ ADMIN__PASSWORD
    setup_admin(app)

    # Ð”Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ SessionMiddleware Ð´Ð»Ñ Ñ€Ð°Ð±Ð¾Ñ‚Ñ‹ ÑÐµÑÑÐ¸Ð¹ Ð²Ð¾ Ð²ÑÐµÑ… Ñ€Ð¾ÑƒÑ‚Ð°Ñ….
    # Ð­Ñ‚Ð¾ Ð½ÑƒÐ¶Ð½Ð¾ Ð´Ð»Ñ Ð°ÑƒÑ‚ÐµÐ½Ñ‚Ð¸Ñ„Ð¸ÐºÐ°Ñ†Ð¸Ð¸ admin API ÑÐ½Ð´Ð¿Ð¾Ð¸Ð½Ñ‚Ð¾Ð² Ñ‡ÐµÑ€ÐµÐ· Ñ‚Ðµ Ð¶Ðµ ÑÐµÑÑÐ¸Ð¸,
    # Ñ‡Ñ‚Ð¾ Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐµÑ‚ SQLAdmin (/admin).
    # secret_key Ð±ÐµÑ€Ñ‘Ð¼ Ð¸Ð· Ð½Ð°ÑÑ‚Ñ€Ð¾ÐµÐº Ð°Ð´Ð¼Ð¸Ð½ÐºÐ¸ â€” Ñ‚Ð¾Ñ‚ Ð¶Ðµ, Ñ‡Ñ‚Ð¾ Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐµÑ‚ÑÑ Ð´Ð»Ñ SQLAdmin.
    if settings.admin.is_enabled:
        app.add_middleware(
            SessionMiddleware,
            secret_key=get_admin_secret_key(),
        )

    # ÐŸÐ¾Ð´ÐºÐ»ÑŽÑ‡Ð°ÐµÐ¼ API Ñ€Ð¾ÑƒÑ‚ÐµÑ€Ñ‹
    # Admin API: /api/admin/payments/{id}/refund
    app.include_router(admin_router)

    # Webhooks API: /api/webhooks/yookassa, /api/webhooks/stripe
    app.include_router(webhooks_router)

    # Telegram webhook API: /api/telegram/webhook
    # Ð˜ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐµÑ‚ÑÑ Ñ‚Ð¾Ð»ÑŒÐºÐ¾ Ð² production mode (ÐºÐ¾Ð³Ð´Ð° ÑƒÐºÐ°Ð·Ð°Ð½ APP__DOMAIN)
    app.include_router(telegram_router)

    # Health check API: /health
    app.include_router(health_router)

    # Root paths: GET / (redirect), POST / (YooKassa webhook)
    app.include_router(root_router)

    return app




