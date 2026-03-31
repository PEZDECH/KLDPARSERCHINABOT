"""
Main entry point for Marketplace Monitor Bot.
"""

import asyncio
import os
import signal
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import settings
from handlers import commands_router, subscriptions_router
from models import db
from scrapers import ScraperManager
from utils.logger import logger


class MarketplaceBot:
    """Main bot class managing all components."""

    def __init__(self) -> None:
        """Initialize bot components."""
        # Initialize bot and dispatcher
        self.bot = Bot(
            token=settings.bot_token,
            parse_mode=ParseMode.HTML,
        )
        self.dp = Dispatcher(storage=MemoryStorage())

        # Initialize scraper manager
        self.scraper_manager = ScraperManager(bot=self.bot)

        # Setup shutdown event
        self._shutdown_event = asyncio.Event()

    async def setup(self) -> None:
        """Setup bot components."""
        # Create logs directory
        os.makedirs("logs", exist_ok=True)

        # Initialize database
        await db.create_tables()
        logger.info("Database initialized")

        # Initialize scrapers
        await self.scraper_manager.initialize_scrapers()

        # Register handlers
        self.dp.include_router(commands_router)
        self.dp.include_router(subscriptions_router)

        # Register startup and shutdown handlers
        self.dp.startup.register(self.on_startup)
        self.dp.shutdown.register(self.on_shutdown)

        # Setup signal handlers
        for sig in (signal.SIGINT, signal.SIGTERM):
            asyncio.get_event_loop().add_signal_handler(
                sig, lambda: asyncio.create_task(self.shutdown())
            )

        logger.info("Bot setup completed")

    async def on_startup(self) -> None:
        """Handle bot startup."""
        logger.info("Bot starting up...")

        # Start the scheduler
        await self.scraper_manager.start_scheduler()

        # Notify admin (optional)
        logger.info("Bot is running!")

    async def on_shutdown(self) -> None:
        """Handle bot shutdown."""
        logger.info("Bot shutting down...")

        # Stop scraper manager
        await self.scraper_manager.close()

        # Close database
        await db.close()

        # Close bot session
        await self.bot.session.close()

        logger.info("Bot shutdown completed")

    async def shutdown(self) -> None:
        """Initiate shutdown."""
        logger.info("Shutdown signal received")
        self._shutdown_event.set()

    async def run(self) -> None:
        """Run the bot."""
        await self.setup()

        try:
            # Start polling
            await self.dp.start_polling(
                self.bot,
                skip_updates=True,
                on_startup=self.on_startup,
                on_shutdown=self.on_shutdown,
            )
        except Exception as e:
            logger.error(f"Error during bot execution: {e}")
            raise
        finally:
            await self.on_shutdown()


async def main() -> None:
    """Main entry point."""
    bot = MarketplaceBot()
    await bot.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise
