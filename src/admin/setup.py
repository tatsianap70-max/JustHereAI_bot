"""ÐÐ°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ° Ð¸ Ð¼Ð¾Ð½Ñ‚Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ðµ Ð°Ð´Ð¼Ð¸Ð½ÐºÐ¸ Ðº FastAPI.

ÐÐ´Ð¼Ð¸Ð½ÐºÐ° Ð¼Ð¾Ð½Ñ‚Ð¸Ñ€ÑƒÐµÑ‚ÑÑ Ñ‚Ð¾Ð»ÑŒÐºÐ¾ ÐµÑÐ»Ð¸ Ð½Ð°ÑÑ‚Ñ€Ð¾ÐµÐ½Ñ‹ ADMIN__USERNAME Ð¸ ADMIN__PASSWORD.
Ð•ÑÐ»Ð¸ Ð¾Ð½Ð¸ Ð½Ðµ Ð·Ð°Ð´Ð°Ð½Ñ‹ â€” Ð°Ð´Ð¼Ð¸Ð½ÐºÐ° Ð½ÐµÐ´Ð¾ÑÑ‚ÑƒÐ¿Ð½Ð° (Ð²Ð¾Ð·Ð²Ñ€Ð°Ñ‰Ð°ÐµÑ‚ÑÑ 404).
"""

from pathlib import Path

from fastapi import FastAPI
from sqladmin import Admin

from src.admin.auth import get_admin_auth
from src.admin.views import (
    BroadcastAdmin,
    GenerationAdmin,
    PaymentAdmin,
    ReferralAdmin,
    SubscriptionAdmin,
    UserAdmin,
)
from src.config.settings import settings
from src.config.yaml_config import yaml_config
from src.db.base import get_sync_engine
from src.utils.logging import get_logger

logger = get_logger(__name__)


def setup_admin(app: FastAPI) -> Admin | None:
    """ÐÐ°ÑÑ‚Ñ€Ð¾Ð¸Ñ‚ÑŒ Ð¸ Ð¿Ð¾Ð´ÐºÐ»ÑŽÑ‡Ð¸Ñ‚ÑŒ Ð°Ð´Ð¼Ð¸Ð½ÐºÑƒ Ðº FastAPI.

    ÐÐ´Ð¼Ð¸Ð½ÐºÐ° Ð²ÐºÐ»ÑŽÑ‡Ð°ÐµÑ‚ÑÑ Ñ‚Ð¾Ð»ÑŒÐºÐ¾ ÐµÑÐ»Ð¸ Ð·Ð°Ð´Ð°Ð½Ñ‹ ADMIN__USERNAME Ð¸ ADMIN__PASSWORD.
    Ð­Ñ‚Ð¾ Ð¿Ð¾Ð·Ð²Ð¾Ð»ÑÐµÑ‚ Ð¾Ñ‚ÐºÐ»ÑŽÑ‡Ð¸Ñ‚ÑŒ Ð°Ð´Ð¼Ð¸Ð½ÐºÑƒ Ð½Ð° Ð¿Ñ€Ð¾Ð´Ð°ÐºÑˆÐµÐ½Ðµ ÐµÑÐ»Ð¸ Ð¾Ð½Ð° Ð½Ðµ Ð½ÑƒÐ¶Ð½Ð°.

    Args:
        app: FastAPI Ð¿Ñ€Ð¸Ð»Ð¾Ð¶ÐµÐ½Ð¸Ðµ.

    Returns:
        ÐžÐ±ÑŠÐµÐºÑ‚ Admin ÐµÑÐ»Ð¸ Ð°Ð´Ð¼Ð¸Ð½ÐºÐ° Ð²ÐºÐ»ÑŽÑ‡ÐµÐ½Ð°, None ÐµÑÐ»Ð¸ Ð¾Ñ‚ÐºÐ»ÑŽÑ‡ÐµÐ½Ð°.
    """
    if not settings.admin.is_enabled:
        logger.info("ÐÐ´Ð¼Ð¸Ð½ÐºÐ° Ð¾Ñ‚ÐºÐ»ÑŽÑ‡ÐµÐ½Ð° (Ð½Ðµ Ð·Ð°Ð´Ð°Ð½Ñ‹ ADMIN__USERNAME Ð¸ ADMIN__PASSWORD)")
        return None

    # Ð¡Ð¾Ð·Ð´Ð°Ñ‘Ð¼ ÑÐ¸Ð½Ñ…Ñ€Ð¾Ð½Ð½Ñ‹Ð¹ engine Ð´Ð»Ñ SQLAdmin
    sync_engine = get_sync_engine()

    # Ð¡Ð¾Ð·Ð´Ð°Ñ‘Ð¼ Ð°Ð´Ð¼Ð¸Ð½ÐºÑƒ Ñ Ð°ÑƒÑ‚ÐµÐ½Ñ‚Ð¸Ñ„Ð¸ÐºÐ°Ñ†Ð¸ÐµÐ¹ Ð¸ ÐºÐ°ÑÑ‚Ð¾Ð¼Ð½Ñ‹Ð¼Ð¸ ÑˆÐ°Ð±Ð»Ð¾Ð½Ð°Ð¼Ð¸
    # ÐŸÑƒÑ‚ÑŒ Ðº ÑˆÐ°Ð±Ð»Ð¾Ð½Ð°Ð¼ Ð¾Ñ‚Ð½Ð¾ÑÐ¸Ñ‚ÐµÐ»ÑŒÐ½Ð¾ Ð¼Ð¾Ð´ÑƒÐ»Ñ admin
    templates_path = Path(__file__).parent / "templates"

    admin = Admin(
        app=app,
        engine=sync_engine,
        authentication_backend=get_admin_auth(),
        title="Just Here Admin",
        templates_dir=str(templates_path),
    )

    # Ð ÐµÐ³Ð¸ÑÑ‚Ñ€Ð¸Ñ€ÑƒÐµÐ¼ Ð¿Ñ€ÐµÐ´ÑÑ‚Ð°Ð²Ð»ÐµÐ½Ð¸Ñ Ð¼Ð¾Ð´ÐµÐ»ÐµÐ¹
    admin.add_view(UserAdmin)
    admin.add_view(PaymentAdmin)
    admin.add_view(ReferralAdmin)
    admin.add_view(GenerationAdmin)

    # Ð ÐµÐ³Ð¸ÑÑ‚Ñ€Ð¸Ñ€ÑƒÐµÐ¼ Ð¿Ð¾Ð´Ð¿Ð¸ÑÐºÐ¸ ÐµÑÐ»Ð¸ ÐµÑÑ‚ÑŒ Ð¿Ð¾Ð´Ð¿Ð¸ÑÐ¾Ñ‡Ð½Ñ‹Ðµ Ñ‚Ð°Ñ€Ð¸Ñ„Ñ‹
    if yaml_config.has_subscription_tariffs():
        admin.add_view(SubscriptionAdmin)

    # Ð ÐµÐ³Ð¸ÑÑ‚Ñ€Ð¸Ñ€ÑƒÐµÐ¼ Ñ€Ð°ÑÑÑ‹Ð»ÐºÐ¸ ÐµÑÐ»Ð¸ Ð¾Ð½Ð¸ Ð²ÐºÐ»ÑŽÑ‡ÐµÐ½Ñ‹ Ð² ÐºÐ¾Ð½Ñ„Ð¸Ð³Ðµ
    if yaml_config.broadcast.enabled:
        admin.add_view(BroadcastAdmin)

    # Ð¤Ð¾Ñ€Ð¼Ð¸Ñ€ÑƒÐµÐ¼ URL Ð°Ð´Ð¼Ð¸Ð½ÐºÐ¸ â€” Ð¿Ð¾Ð»Ð½Ñ‹Ð¹ ÐµÑÐ»Ð¸ ÐµÑÑ‚ÑŒ Ð´Ð¾Ð¼ÐµÐ½, Ð¸Ð½Ð°Ñ‡Ðµ Ð¾Ñ‚Ð½Ð¾ÑÐ¸Ñ‚ÐµÐ»ÑŒÐ½Ñ‹Ð¹ Ð¿ÑƒÑ‚ÑŒ
    if settings.app.domain:
        # Ð£Ð±Ð¸Ñ€Ð°ÐµÐ¼ trailing slash Ð¸ Ð´Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ /admin
        domain = settings.app.domain.rstrip("/")
        if not domain.startswith("http"):
            domain = f"https://{domain}"
        admin_url = f"{domain}/admin"
    else:
        admin_url = "/admin"

    logger.info("ÐÐ´Ð¼Ð¸Ð½ÐºÐ° Ð´Ð¾ÑÑ‚ÑƒÐ¿Ð½Ð°: %s", admin_url)
    return admin




