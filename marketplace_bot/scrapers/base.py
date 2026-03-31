"""
Base scraper class and data models.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from fake_useragent import UserAgent

from config import settings
from utils.logger import logger


@dataclass
class ScrapedItem:
    """Data class representing a scraped item."""

    platform_item_id: str
    title: str
    price: float
    url: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    location: Optional[str] = None
    seller_name: Optional[str] = None
    currency: str = "RUB"

    def __post_init__(self) -> None:
        """Validate scraped item data."""
        if not self.platform_item_id:
            raise ValueError("platform_item_id is required")
        if not self.title:
            raise ValueError("title is required")
        if self.price < 0:
            raise ValueError("price cannot be negative")
        if not self.url:
            raise ValueError("url is required")


class BaseScraper(ABC):
    """
    Abstract base class for all marketplace scrapers.

    All scrapers must inherit from this class and implement
    the required abstract methods.
    """

    def __init__(self, proxy: Optional[str] = None) -> None:
        """
        Initialize scraper with optional proxy.

        Args:
            proxy: Proxy URL in format http://user:pass@host:port
        """
        self.proxy = proxy or settings.http_proxy
        self.ua = UserAgent()
        self.logger = logger.bind(scraper=self.__class__.__name__)

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Return platform name (e.g., 'avito', 'grailed')."""
        pass

    @property
    @abstractmethod
    def base_url(self) -> str:
        """Return platform base URL."""
        pass

    def get_headers(self) -> dict[str, str]:
        """
        Get HTTP headers with randomized User-Agent.

        Returns:
            Dictionary of HTTP headers
        """
        return {
            "User-Agent": self.ua.random,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }

    @abstractmethod
    async def fetch_latest_items(
        self,
        query: str,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        limit: int = 10,
    ) -> list[ScrapedItem]:
        """
        Fetch latest items matching the query and price range.

        Args:
            query: Search query string
            min_price: Minimum price filter (optional)
            max_price: Maximum price filter (optional)
            limit: Maximum number of items to return

        Returns:
            List of ScrapedItem objects
        """
        pass

    def build_search_url(
        self,
        query: str,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
    ) -> str:
        """
        Build search URL with query and price filters.

        Args:
            query: Search query string
            min_price: Minimum price filter
            max_price: Maximum price filter

        Returns:
            Complete search URL
        """
        # Override in subclass for platform-specific URL building
        raise NotImplementedError("Subclasses must implement build_search_url")

    def normalize_price(self, price_text: str) -> float:
        """
        Extract numeric price from text.

        Args:
            price_text: Price text (e.g., "1 500 ₽", "$100")

        Returns:
            Numeric price value
        """
        import re

        # Remove all non-numeric characters except decimal point
        cleaned = re.sub(r"[^\d.,]", "", price_text)
        cleaned = cleaned.replace(",", ".")

        # Handle multiple decimal points (keep only last)
        parts = cleaned.split(".")
        if len(parts) > 2:
            cleaned = "".join(parts[:-1]) + "." + parts[-1]

        try:
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            self.logger.warning(f"Could not parse price from: {price_text}")
            return 0.0

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    @abstractmethod
    async def close(self) -> None:
        """Close scraper resources (sessions, browsers, etc.)."""
        pass

    def is_price_in_range(
        self,
        price: float,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
    ) -> bool:
        """
        Check if price is within specified range.

        Args:
            price: Item price
            min_price: Minimum allowed price
            max_price: Maximum allowed price

        Returns:
            True if price is in range
        """
        if min_price is not None and price < min_price:
            return False
        if max_price is not None and price > max_price:
            return False
        return True
