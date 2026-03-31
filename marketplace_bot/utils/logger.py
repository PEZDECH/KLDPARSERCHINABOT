"""
Logging configuration using Loguru.
"""

import sys

from loguru import logger

from config import settings

# Remove default handler
logger.remove()

# Add console handler with custom format
logger.add(
    sys.stdout,
    level=settings.log_level,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
           "<level>{level: <8}</level> | "
           "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
           "<level>{message}</level>",
    colorize=True,
)

# Add file handler for errors
logger.add(
    "logs/error.log",
    level="ERROR",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
    rotation="10 MB",
    retention="7 days",
    compression="zip",
    enqueue=True,
)

# Add file handler for all logs
logger.add(
    "logs/bot.log",
    level=settings.log_level,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
    rotation="10 MB",
    retention="7 days",
    compression="zip",
    enqueue=True,
)

logger.info("Logger initialized")
