"""Задачи планировщика.

Этот модуль содержит функции, которые периодически выполняются
планировщиком APScheduler:

1. process_renewals — проверка и продление истекающих подписок
2. process_past_due — повторные попытки для неудачных продлений
3. expire_stale_subscriptions — пометка подписок как истёкших
4. process_broadcasts — отправка сообщений активных рассылок

Как работает процесс автопродления:
1. Ежедневно в 06:00 UTC (09:00 МСК) запускается проверка подписок
2. Находим подписки с period_end в ближайшие сутки
3. Для каждой подписки пытаемся списать оплату:
   - YooKassa: рекуррентный платёж через сохранённую карту
   - Stripe: аналогично через payment_method_id
   - Telegram Stars: Telegram сам управляет (мы только обрабатываем webhook)
4. При успехе — продлеваем период и начисляем токены
5. При неудаче — помечаем PAST_DUE, повторяем попытку на следующий день
6. После billing.renewal_retry_days неудачных попыток — подписка истекает

Как работают рассылки:
1. Каждые 30 секунд проверяем активные рассылки (PENDING/RUNNING)
2. Для каждой рассылки отправляем батч сообщений
3. Обновляем прогресс и продолжаем в следующем цикле
4. При завершении всех отправок — статус COMPLETED

Важно: Все задачи должны быть идемпотентными (безопасно запускать повторно).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from src.config.settings import settings
from src.db.base import DatabaseSession
from src.db.models.subscription import Subscription, SubscriptionStatus
from src.db.repositories.subscription_repo import SubscriptionRepository
from src.db.repositories.user_repo import UserRepository
from src.services.renewal_service import (
    RenewalAttemptResult,
    RenewalResult,
    create_renewal_service,
)
from src.services.subscription_service import create_subscription_service
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from aiogram import Bot

    from src.config.yaml_config import BroadcastConfig, YamlConfig
    from src.db.models.broadcast import Broadcast
    from src.db.repositories.broadcast_repo import BroadcastRepository
    from src.providers.payments.base import BasePaymentProvider

logger = get_logger(__name__)


def _create_payment_providers() -> dict[str, BasePaymentProvider]:
    """Создать словарь настроенных платёжных провайдеров.

    Проверяет конфигурацию и создаёт только настроенные провайдеры.

    Returns:
        Словарь {имя_провайдера: экземпляр}.
    """
    from src.providers.payments import (
        create_stripe_provider,
        create_yookassa_provider,
    )

    providers: dict[str, BasePaymentProvider] = {}

    # YooKassa
    if settings.payments.has_yookassa:
        yookassa_config = settings.payments.yookassa
        if yookassa_config.shop_id and yookassa_config.secret_key:
            providers["yookassa"] = create_yookassa_provider(
                shop_id=yookassa_config.shop_id,
                secret_key=yookassa_config.secret_key.get_secret_value(),
            )
            logger.debug("YooKassa провайдер инициализирован для scheduler")

    # Stripe
    if settings.payments.has_stripe:
        stripe_config = settings.payments.stripe
        if stripe_config.secret_key:
            webhook_secret = None
            if stripe_config.webhook_secret:
                webhook_secret = stripe_config.webhook_secret.get_secret_value()
            providers["stripe"] = create_stripe_provider(
                secret_key=stripe_config.secret_key.get_secret_value(),
                webhook_secret=webhook_secret,
            )
            logger.debug("Stripe провайдер инициализирован для scheduler")

    return providers


async def _get_tariff_name(yaml_config: YamlConfig, tariff_slug: str) -> str:
    """Получить название тарифа из конфига."""
    tariff = yaml_config.get_tariff(tariff_slug)
    return tariff.name.ru if tariff else tariff_slug


async def _handle_renewal_result(
    result: RenewalAttemptResult,
    subscription: Subscription,
    stats: dict[str, int],
    yaml_config: YamlConfig,
    user_repo: UserRepository,
    bot: Bot | None,
) -> None:
    """Обработать результат продления и отправить уведомление."""
    if result.result == RenewalResult.SUCCESS:
        stats["success"] += 1
    elif result.result == RenewalResult.SKIPPED:
        stats["skipped"] += 1
    elif result.result == RenewalResult.NO_PAYMENT_METHOD:
        stats["no_payment_method"] += 1
        if bot:
            user = await user_repo.get_by_id(subscription.user_id)
            if user:
                tariff_name = await _get_tariff_name(
                    yaml_config, subscription.tariff_slug
                )
                await _send_renewal_required_notification(
                    bot, user.telegram_id, tariff_name
                )
    else:
        stats["failed"] += 1
        if bot:
            user = await user_repo.get_by_id(subscription.user_id)
            if user:
                tariff_name = await _get_tariff_name(
                    yaml_config, subscription.tariff_slug
                )
                await _send_renewal_failed_notification(
                    bot, user.telegram_id, tariff_name
                )


async def process_renewals(
    yaml_config: YamlConfig,
    bot: Bot | None = None,
) -> None:
    """Обработать автопродление подписок.

    Находит подписки с истекающим периодом и инициирует продление.
    Для YooKassa/Stripe создаёт рекуррентный платёж.
    Для Telegram Stars — пропускаем (Telegram сам управляет).

    Args:
        yaml_config: YAML-конфигурация.
        bot: Telegram Bot для отправки уведомлений (опционально).
    """
    if not yaml_config.has_subscription_tariffs():
        logger.debug("Подписочные тарифы не найдены, пропускаем проверку продлений")
        return

    logger.info("Запуск проверки автопродления подписок...")

    providers = _create_payment_providers()
    if not providers:
        logger.warning(
            "Нет настроенных провайдеров для автопродления. "
            "Проверьте конфигурацию YooKassa/Stripe."
        )

    stats: dict[str, int] = {
        "total": 0,
        "success": 0,
        "failed": 0,
        "skipped": 0,
        "no_payment_method": 0,
    }

    async with DatabaseSession() as session:
        subscription_repo = SubscriptionRepository(session)
        user_repo = UserRepository(session)
        expiring_before = datetime.now(UTC) + timedelta(hours=24)

        expiring_subscriptions = await subscription_repo.get_expiring_subscriptions(
            before=expiring_before, limit=100
        )
        stats["total"] = len(expiring_subscriptions)
        logger.info("Найдено %d подписок для продления", stats["total"])

        renewal_service = create_renewal_service(
            session=session, providers=providers, yaml_config=yaml_config
        )

        for subscription in expiring_subscriptions:
            try:
                result = await renewal_service.process_subscription_renewal(
                    subscription
                )
                await _handle_renewal_result(
                    result, subscription, stats, yaml_config, user_repo, bot
                )
            except Exception:
                stats["failed"] += 1
                logger.exception(
                    "Ошибка при обработке продления подписки id=%d", subscription.id
                )

        await session.commit()
        logger.info(
            "Проверка автопродления завершена: "
            "всего=%d, успешно=%d, неудачно=%d, пропущено=%d, без метода оплаты=%d",
            stats["total"],
            stats["success"],
            stats["failed"],
            stats["skipped"],
            stats["no_payment_method"],
        )


async def process_past_due(
    yaml_config: YamlConfig,
    bot: Bot | None = None,
) -> None:
    """Обработать подписки с неудачными попытками продления.

    Повторяет попытку продления для PAST_DUE подписок раз в день.
    После billing.renewal_retry_days неудачных попыток — подписка истекает.

    Args:
        yaml_config: YAML-конфигурация.
        bot: Telegram Bot для отправки уведомлений (опционально).
    """
    if not yaml_config.has_subscription_tariffs():
        return

    max_attempts = yaml_config.billing.renewal_retry_days

    logger.info("Обработка PAST_DUE подписок (max_attempts=%d)...", max_attempts)

    # Создаём провайдеры
    providers = _create_payment_providers()

    stats = {"total": 0, "success": 0, "failed": 0, "expired": 0}

    async with DatabaseSession() as session:
        subscription_repo = SubscriptionRepository(session)
        subscription_service = create_subscription_service(session, yaml_config)
        user_repo = UserRepository(session)

        past_due = await subscription_repo.get_past_due_subscriptions(
            max_attempts=max_attempts,
            limit=50,
        )

        stats["total"] = len(past_due)
        logger.info("Найдено %d PAST_DUE подписок", stats["total"])

        # Создаём сервис для продлений
        renewal_service = create_renewal_service(
            session=session,
            providers=providers,
            yaml_config=yaml_config,
        )

        for subscription in past_due:
            try:
                # Проверяем лимит попыток
                if subscription.renewal_attempts >= max_attempts:
                    logger.info(
                        "Подписка id=%d: достигнут лимит попыток (%d дней), истекает",
                        subscription.id,
                        max_attempts,
                    )
                    await subscription_service.expire_subscription(subscription)
                    stats["expired"] += 1

                    # Уведомляем пользователя
                    if bot:
                        user = await user_repo.get_by_id(subscription.user_id)
                        if user:
                            tariff = yaml_config.get_tariff(subscription.tariff_slug)
                            tariff_name = (
                                tariff.name.ru if tariff else subscription.tariff_slug
                            )
                            await _send_subscription_expired_notification(
                                bot, user.telegram_id, tariff_name
                            )
                    continue

                # Повторная попытка продления
                result = await renewal_service.process_subscription_renewal(
                    subscription
                )

                if result.result == RenewalResult.SUCCESS:
                    stats["success"] += 1
                    # Уведомляем о успешном продлении после retry
                    if bot:
                        user = await user_repo.get_by_id(subscription.user_id)
                        if user:
                            tariff = yaml_config.get_tariff(subscription.tariff_slug)
                            tariff_name = (
                                tariff.name.ru if tariff else subscription.tariff_slug
                            )
                            await _send_renewal_success_notification(
                                bot, user.telegram_id, tariff_name
                            )
                else:
                    stats["failed"] += 1
                    logger.warning(
                        "Retry продления не удался: subscription_id=%d, "
                        "попытка %d/%d, причина=%s",
                        subscription.id,
                        subscription.renewal_attempts,
                        max_attempts,
                        result.error_message,
                    )

            except Exception:
                stats["failed"] += 1
                logger.exception(
                    "Ошибка при обработке PAST_DUE подписки id=%d",
                    subscription.id,
                )

        await session.commit()

        logger.info(
            "Обработка PAST_DUE завершена: "
            "всего=%d, успешно=%d, неудачно=%d, истекло=%d",
            stats["total"],
            stats["success"],
            stats["failed"],
            stats["expired"],
        )


async def expire_stale_subscriptions(yaml_config: YamlConfig) -> None:
    """Пометить устаревшие подписки как истёкшие.

    Находит подписки, которые давно истекли (более 7 дней)
    и помечает их как EXPIRED с переносом токенов.

    Args:
        yaml_config: YAML-конфигурация.
    """
    if not yaml_config.has_subscription_tariffs():
        return

    logger.info("Проверка устаревших подписок...")

    async with DatabaseSession() as session:
        subscription_service = create_subscription_service(session, yaml_config)

        # Находим подписки, истёкшие более 7 дней назад
        # которые всё ещё в статусе PAST_DUE
        from sqlalchemy import select

        from src.db.models.subscription import Subscription

        stale_date = datetime.now(UTC) - timedelta(days=7)

        stmt = (
            select(Subscription)
            .where(
                Subscription.status == SubscriptionStatus.PAST_DUE,
                Subscription.period_end < stale_date,
            )
            .limit(50)
        )
        result = await session.execute(stmt)
        stale_subscriptions = list(result.scalars().all())

        logger.info("Найдено %d устаревших подписок", len(stale_subscriptions))

        for subscription in stale_subscriptions:
            try:
                await subscription_service.expire_subscription(subscription)
                logger.info(
                    "Подписка id=%d помечена как истёкшая",
                    subscription.id,
                )
            except Exception:
                logger.exception(
                    "Ошибка при истечении подписки id=%d",
                    subscription.id,
                )

        await session.commit()
        logger.info("Проверка устаревших подписок завершена")


async def _send_renewal_required_notification(
    bot: Bot,
    telegram_id: int,
    tariff_name: str,
) -> None:
    """Отправить уведомление о необходимости добавить метод оплаты.

    Args:
        bot: Telegram Bot.
        telegram_id: Telegram ID пользователя.
        tariff_name: Название тарифа для сообщения.
    """
    message = (
        f"⚠️ Для автопродления подписки «{tariff_name}» нужен сохранённый "
        f"способ оплаты.\n\n"
        f"Пожалуйста, продлите подписку вручную через /balance."
    )
    try:
        await bot.send_message(telegram_id, message)
    except Exception:
        logger.exception(
            "Ошибка отправки уведомления о методе оплаты telegram_id=%d",
            telegram_id,
        )


async def _send_renewal_failed_notification(
    bot: Bot,
    telegram_id: int,
    tariff_name: str,
) -> None:
    """Отправить уведомление о неудачном списании.

    Args:
        bot: Telegram Bot.
        telegram_id: Telegram ID пользователя.
        tariff_name: Название тарифа для сообщения.
    """
    message = (
        f"⚠️ Не удалось автоматически продлить подписку «{tariff_name}».\n\n"
        f"Мы попробуем снова завтра. Если проблема повторится, "
        f"пожалуйста, проверьте способ оплаты или продлите вручную через /balance."
    )
    try:
        await bot.send_message(telegram_id, message)
    except Exception:
        logger.exception(
            "Ошибка отправки уведомления о неудачном продлении telegram_id=%d",
            telegram_id,
        )


async def _send_renewal_success_notification(
    bot: Bot,
    telegram_id: int,
    tariff_name: str,
) -> None:
    """Отправить уведомление об успешном продлении после retry.

    Args:
        bot: Telegram Bot.
        telegram_id: Telegram ID пользователя.
        tariff_name: Название тарифа для сообщения.
    """
    message = (
        f"✅ Подписка «{tariff_name}» успешно продлена!\n\n"
        f"Токены начислены. Используйте /balance для проверки баланса."
    )
    try:
        await bot.send_message(telegram_id, message)
    except Exception:
        logger.exception(
            "Ошибка отправки уведомления об успешном продлении telegram_id=%d",
            telegram_id,
        )


async def _send_subscription_expired_notification(
    bot: Bot,
    telegram_id: int,
    tariff_name: str,
) -> None:
    """Отправить уведомление об истечении подписки.

    Args:
        bot: Telegram Bot.
        telegram_id: Telegram ID пользователя.
        tariff_name: Название тарифа для сообщения.
    """
    message = (
        f"😔 Подписка «{tariff_name}» истекла.\n\n"
        f"Не удалось списать оплату после нескольких попыток. "
        f"Вы можете оформить новую подписку через /balance."
    )
    try:
        await bot.send_message(telegram_id, message)
    except Exception:
        logger.exception(
            "Ошибка отправки уведомления об истечении подписки telegram_id=%d",
            telegram_id,
        )


# =============================================================================
# ЗАДАЧИ РАССЫЛОК
# =============================================================================


async def process_broadcasts(
    yaml_config: YamlConfig,
    bot: Bot,
) -> None:
    """Обработать активные рассылки.

    Периодическая задача, которая:
    1. Находит рассылки в статусе PENDING/RUNNING
    2. Для каждой отправляет батч сообщений
    3. Обновляет прогресс

    Вызывается scheduler'ом каждые 30 секунд.
    Если активных рассылок нет — быстро завершается.

    Args:
        yaml_config: YAML-конфигурация.
        bot: Telegram Bot для отправки сообщений.
    """

    import asyncio

    from src.db.repositories.broadcast_repo import BroadcastRepository
    from src.db.repositories.user_repo import UserRepository

    config = yaml_config.broadcast
    send_interval = 1.0 / config.messages_per_second

    async with DatabaseSession() as session:
        repo = BroadcastRepository(session)
        user_repo = UserRepository(session)

        # Получаем активные рассылки
        broadcasts = await repo.get_active_broadcasts()

        if not broadcasts:
            return  # Нет активных рассылок — быстрый выход

        logger.debug("Найдено %d активных рассылок", len(broadcasts))

        for i, broadcast in enumerate(broadcasts):
            try:
                await _process_single_broadcast(
                    broadcast=broadcast,
                    repo=repo,
                    user_repo=user_repo,
                    bot=bot,
                    config=config,
                    send_interval=send_interval,
                )
            except Exception:
                logger.exception("Ошибка обработки рассылки %d", broadcast.id)

            # Задержка между рассылками для снижения нагрузки на Telegram API
            if i < len(broadcasts) - 1:
                await asyncio.sleep(1.0)


async def _process_single_broadcast(
    broadcast: Broadcast,
    repo: BroadcastRepository,
    user_repo: UserRepository,
    bot: Bot,
    config: BroadcastConfig,
    send_interval: float,
) -> None:
    """Обработать одну рассылку — отправить батч сообщений.

    Args:
        broadcast: Рассылка для обработки.
        repo: Репозиторий рассылок.
        user_repo: Репозиторий пользователей.
        bot: Telegram Bot.
        config: Конфигурация рассылок.
        send_interval: Интервал между сообщениями (секунды).
    """
    import asyncio

    from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

    from src.db.models.broadcast import BroadcastStatus, ParseMode

    # Меняем статус на RUNNING если был PENDING
    if broadcast.status == BroadcastStatus.PENDING:
        await repo.set_status(broadcast.id, BroadcastStatus.RUNNING)

    # Получаем получателей для батча
    users = await user_repo.get_by_segment(
        language=broadcast.filter_language,
        has_payments=broadcast.filter_has_payments,
        source=broadcast.filter_source,
        registered_after=broadcast.filter_registered_after,
        registered_before=broadcast.filter_registered_before,
        exclude_blocked=broadcast.filter_exclude_blocked,
        after_user_id=broadcast.last_processed_user_id,
        limit=config.batch_size,
    )

    if not users:
        # Все сообщения отправлены — завершаем рассылку
        await repo.complete(broadcast)
        logger.info(
            "Рассылка завершена: id=%d, name=%s, sent=%d, failed=%d",
            broadcast.id,
            broadcast.name,
            broadcast.sent_count,
            broadcast.failed_count,
        )
        return

    # Определяем parse_mode
    parse_mode = None
    if broadcast.parse_mode != ParseMode.NONE:
        parse_mode = broadcast.parse_mode

    # Отправляем батч
    sent = 0
    failed = 0
    last_user_id = broadcast.last_processed_user_id

    for user in users:
        last_user_id = user.id

        try:
            await bot.send_message(
                chat_id=user.telegram_id,
                text=broadcast.message_text,
                parse_mode=parse_mode,
            )
            sent += 1

        except TelegramRetryAfter as e:
            # FloodWait — ждём требуемое время и прекращаем батч
            logger.warning(
                "FloodWait при рассылке %d: retry_after=%d сек. Ожидание...",
                broadcast.id,
                e.retry_after,
            )
            await asyncio.sleep(e.retry_after)
            # Не считаем как failed — это техническая пауза, не ошибка отправки
            break

        except TelegramForbiddenError:
            # Пользователь заблокировал бота
            logger.debug(
                "Рассылка %d: пользователь %d заблокировал бота",
                broadcast.id,
                user.telegram_id,
            )
            failed += 1

        except TimeoutError:
            # Таймаут соединения с Telegram
            logger.warning(
                "Таймаут при рассылке %d пользователю %d",
                broadcast.id,
                user.telegram_id,
            )
            failed += 1

        except Exception as e:
            # Неожиданные ошибки — логируем с полным traceback
            logger.exception(
                "Неожиданная ошибка отправки рассылки %d пользователю %d: %s",
                broadcast.id,
                user.telegram_id,
                type(e).__name__,
            )
            failed += 1

        # Rate limiting между сообщениями
        await asyncio.sleep(send_interval)

    # Обновляем прогресс
    await repo.increment_progress(
        broadcast_id=broadcast.id,
        sent_delta=sent,
        failed_delta=failed,
        last_processed_user_id=last_user_id or 0,
    )

    # Примечание: broadcast.sent_count может быть устаревшим (in-memory),
    # поэтому логируем только дельту этого батча
    logger.info(
        "Рассылка %d: батч +%d sent, +%d failed, last_user_id=%d",
        broadcast.id,
        sent,
        failed,
        last_user_id or 0,
    )
