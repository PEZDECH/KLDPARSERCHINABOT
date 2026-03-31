"""
Scrapers module for Marketplace Monitor Bot.
"""

from scrapers.base import BaseScraper, ScrapedItem
from scrapers.avito import AvitoScraper
from scrapers.grailed import GrailedScraper
from scrapers.mercari import MercariScraper
from scrapers.manager import ScraperManager

__all__ = [
    "BaseScraper",
    "ScrapedItem",
    "AvitoScraper",
    "GrailedScraper",
    "MercariScraper",
    "ScraperManager",
]
