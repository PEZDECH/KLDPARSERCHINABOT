"""
Scraper manager for coordinating multiple scrapers and scheduling.
"""

import asyncio
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models import Item, Platform, Subscription, get_db
from scrapers.avito import AvitoScraper
from scrapers.base import ScrapedItem
from scrapers.grailed import GrailedScraper
from scrapers.mercari import MercariScraper
from utils.logger import logger


class ScraperManager:
    """
    Manager class for coordinating scrapers and scheduling tasks.
    """

    def __init__(self, bot=None) -> None:
        """
        Initialize scraper manager.

        Args:
            bot: Optional aiogram Bot instance for sending notifications
        """
        self.bot = bot
        self.scrapers: dict[Platform, object] = {}
        self.scheduler: Optional[AsyncIOScheduler] = None
        self._running = False
        self._lock = asyncio.Lock()

    async def initialize_scrapers(self) -> None:
        """Initialize all scraper instances."""
        self.scrapers = {
            Platform.AVITO: AvitoScraper(),
            Platform.GRAILED: GrailedScraper(),
            Platform.MERCARI: MercariScraper(),
        }
        logger.info(f"Initialized {len(self.scrapers)} scrapers")

    async def start_scheduler(self) -> None:
        """Start the APScheduler for periodic parsing."""
        if self.scheduler is None:
            self.scheduler = AsyncIOScheduler()

        # Add job for periodic parsing
        self.scheduler.add_job(
            self.run_all_parsing,
            trigger=IntervalTrigger(minutes=settings.parsing_interval_minutes),
            id="parsing_job",
            name="Parse all subscriptions",
            replace_existing=True,
        )

        self.scheduler.start()
        self._running = True
        logger.info(
            f"Scheduler started with interval: {settings.parsing_interval_minutes} minutes"
        )

    async def stop_scheduler(self) -> None:
        """Stop the scheduler."""
        if self.scheduler:
            self.scheduler.shutdown()
            self.scheduler = None
            self._running = False
            logger.info("Scheduler stopped")

    async def run_all_parsing(self) -> None:
        """Run parsing for all active subscriptions."""
        if not self._running:
            return

        async with self._lock:
            logger.info("Starting scheduled parsing for all subscriptions")

            try:
                async for session in get_db():
                    # Get all active subscriptions
                    from sqlalchemy import select

                    result = await session.execute(
                        select(Subscription).where(Subscription.is_active == True)
                    )
                    subscriptions = result.scalars().all()

                    logger.info(f"Found {len(subscriptions)} active subscriptions")

                    # Group subscriptions by platform for efficiency
                    by_platform: dict[Platform, list[Subscription]] = {}
                    for sub in subscriptions:
                        if sub.platform not in by_platform:
                            by_platform[sub.platform] = []
                        by_platform[sub.platform].append(sub)

                    # Process each platform
                    for platform, platform_subs in by_platform.items():
                        await self._process_platform_subscriptions(
                            platform, platform_subs, session
                        )

            except Exception as e:
                logger.error(f"Error during scheduled parsing: {e}")

    async def _process_platform_subscriptions(
        self,
        platform: Platform,
        subscriptions: list[Subscription],
        session: AsyncSession,
    ) -> None:
        """
        Process subscriptions for a specific platform.

        Args:
            platform: Platform enum value
            subscriptions: List of subscriptions for this platform
            session: Database session
        """
        scraper = self.scrapers.get(platform)
        if not scraper:
            logger.warning(f"No scraper found for platform: {platform}")
            return

        for subscription in subscriptions:
            try:
                await self._process_single_subscription(subscription, scraper, session)
            except Exception as e:
                logger.error(
                    f"Error processing subscription {subscription.id}: {e}"
                )
                # Continue with next subscription, don't break the loop
                continue

    async def _process_single_subscription(
        self,
        subscription: Subscription,
        scraper,
        session: AsyncSession,
    ) -> None:
        """
        Process a single subscription.

        Args:
            subscription: Subscription to process
            scraper: Scraper instance for the platform
            session: Database session
        """
        from sqlalchemy import select

        # Fetch items from platform
        items = await scraper.fetch_latest_items(
            query=subscription.query,
            min_price=subscription.min_price,
            max_price=subscription.max_price,
            limit=20,
        )

        if not items:
            return

        # Get already sent item IDs for this subscription
        result = await session.execute(
            select(Item.platform_item_id).where(
                Item.subscription_id == subscription.id
            )
        )
        sent_ids = {row[0] for row in result.all()}

        # Process new items
        new_items = []
        for item in items:
            if item.platform_item_id not in sent_ids:
                # Save to database
                db_item = Item(
                    subscription_id=subscription.id,
                    platform_item_id=item.platform_item_id,
                    title=item.title,
                    description=item.description,
                    price=item.price,
                    currency=item.currency,
                    url=item.url,
                    image_url=item.image_url,
                    location=item.location,
                    seller_name=item.seller_name,
                )
                session.add(db_item)
                new_items.append(item)

        if new_items:
            await session.commit()
            logger.info(
                f"Found {len(new_items)} new items for subscription {subscription.id}"
            )

            # Send notifications
            if self.bot:
                for item in new_items:
                    await self._send_notification(subscription, item)
        else:
            logger.debug(f"No new items for subscription {subscription.id}")

        # Update last checked timestamp
        from datetime import datetime

        subscription.last_checked_at = datetime.utcnow()
        await session.commit()

    async def _send_notification(
        self, subscription: Subscription, item: ScrapedItem
    ) -> None:
        """
        Send notification to user about new item.

        Args:
            subscription: User subscription
            item: New item found
        """
        if not self.bot:
            return

        try:
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

            # Build message
            message_text = (
                f"🔔 <b>Новый товар по вашей подписке!</b>\n\n"
                f"📋 Подписка: <code>{subscription.query}</code>\n"
                f"🛒 Площадка: {subscription.platform.value.title()}\n\n"
                f"{item.title[:100]}{'...' if len(item.title) > 100 else ''}\n"
                f"💰 <b>{item.price:,.0f} {item.currency}</b>\n"
            )

            if item.location:
                message_text += f"📍 {item.location}\n"

            # Build keyboard
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔗 Открыть товар",
                            url=item.url,
                        )
                    ]
                ]
            )

            # Send message
            await self.bot.send_message(
                chat_id=subscription.user.telegram_id,
                text=message_text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )

            logger.info(
                f"Notification sent to user {subscription.user.telegram_id} for item {item.platform_item_id}"
            )

        except Exception as e:
            logger.error(f"Failed to send notification: {e}")

    async def parse_single_subscription(
        self,
        subscription: Subscription,
        session: AsyncSession,
    ) -> list[ScrapedItem]:
        """
        Parse a single subscription on demand.

        Args:
            subscription: Subscription to parse
            session: Database session

        Returns:
            List of new items found
        """
        scraper = self.scrapers.get(subscription.platform)
        if not scraper:
            raise ValueError(f"No scraper for platform: {subscription.platform}")

        await self._process_single_subscription(subscription, scraper, session)

        # Return new items
        from sqlalchemy import select

        result = await session.execute(
            select(Item)
            .where(Item.subscription_id == subscription.id)
            .order_by(Item.created_at.desc())
            .limit(10)
        )
        return [item for item in result.scalars().all()]

    async def close(self) -> None:
        """Close all scrapers and stop scheduler."""
        await self.stop_scheduler()

        for platform, scraper in self.scrapers.items():
            try:
                await scraper.close()
                logger.info(f"Closed scraper for {platform.value}")
            except Exception as e:
                logger.error(f"Error closing scraper for {platform.value}: {e}")

        self.scrapers.clear()
        logger.info("Scraper manager closed")
