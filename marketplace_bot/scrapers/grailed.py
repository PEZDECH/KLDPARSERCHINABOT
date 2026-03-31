"""
Grailed scraper using aiohttp with API requests.
"""

import json
from typing import Optional
from urllib.parse import quote

import aiohttp

from config import settings
from scrapers.base import BaseScraper, ScrapedItem
from utils.logger import logger
from utils.retry import retry_with_backoff


class GrailedScraper(BaseScraper):
    """
    Scraper for Grailed marketplace.
    Uses aiohttp for API-based scraping.
    """

    def __init__(self, proxy: Optional[str] = None) -> None:
        """Initialize Grailed scraper."""
        super().__init__(proxy)
        self.session: Optional[aiohttp.ClientSession] = None
        self.api_base = "https://www.grailed.com/api"

    @property
    def platform_name(self) -> str:
        """Return platform name."""
        return "grailed"

    @property
    def base_url(self) -> str:
        """Return Grailed base URL."""
        return "https://www.grailed.com"

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self.session is None or self.session.closed:
            connector = aiohttp.TCPConnector(
                limit=10,
                limit_per_host=5,
                ttl_dns_cache=300,
            )

            timeout = aiohttp.ClientTimeout(total=settings.request_timeout)

            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers=self.get_headers(),
            )
        return self.session

    def build_search_url(
        self,
        query: str,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
    ) -> str:
        """
        Build Grailed search URL.

        Args:
            query: Search query
            min_price: Minimum price
            max_price: Maximum price

        Returns:
            Grailed search URL
        """
        encoded_query = quote(query)
        url = f"{self.base_url}/shop?query={encoded_query}"

        if min_price is not None:
            url += f"&price_min={int(min_price)}"
        if max_price is not None:
            url += f"&price_max={int(max_price)}"

        # Sort by new
        url += "&sort=newly_listed"

        return url

    @retry_with_backoff(
        exceptions=(aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError),
        max_retries=3,
    )
    async def fetch_latest_items(
        self,
        query: str,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        limit: int = 10,
    ) -> list[ScrapedItem]:
        """
        Fetch latest items from Grailed.

        Args:
            query: Search query
            min_price: Minimum price filter
            max_price: Maximum price filter
            limit: Maximum items to return

        Returns:
            List of ScrapedItem objects
        """
        self.logger.info(f"Fetching items from Grailed for query: {query}")

        session = await self._get_session()
        items = []

        try:
            # Grailed uses a GraphQL API, we'll use their search endpoint
            search_url = f"{self.api_base}/listings"

            params = {
                "query": query,
                "sort": "newly_listed",
                "per_page": limit,
            }

            if min_price is not None:
                params["price_min"] = int(min_price)
            if max_price is not None:
                params["price_max"] = int(max_price)

            async with session.get(
                search_url,
                params=params,
                proxy=self.proxy,
            ) as response:
                if response.status == 403:
                    self.logger.error("Grailed returned 403 - access denied")
                    raise aiohttp.ClientError("Access denied by Grailed")

                if response.status == 429:
                    self.logger.warning("Grailed rate limit hit")
                    raise aiohttp.ClientError("Rate limited by Grailed")

                response.raise_for_status()

                data = await response.json()

                # Parse listings from response
                listings = data.get("listings", [])

                for listing in listings[:limit]:
                    try:
                        item = self._parse_listing(listing)
                        if item and self.is_price_in_range(item.price, min_price, max_price):
                            items.append(item)
                    except Exception as e:
                        self.logger.warning(f"Failed to parse Grailed listing: {e}")
                        continue

            self.logger.info(f"Successfully fetched {len(items)} items from Grailed")

        except Exception as e:
            self.logger.error(f"Error fetching from Grailed: {e}")
            raise

        return items

    def _parse_listing(self, listing: dict) -> Optional[ScrapedItem]:
        """
        Parse a single Grailed listing from API response.

        Args:
            listing: Listing data from API

        Returns:
            ScrapedItem or None if parsing fails
        """
        try:
            item_id = str(listing.get("id", ""))
            if not item_id:
                return None

            title = listing.get("title", "Unknown Item")

            # Get price - Grailed prices are in USD
            price_data = listing.get("price", {})
            price = 0.0
            if isinstance(price_data, dict):
                price = float(price_data.get("amount", 0))
            elif isinstance(price_data, (int, float)):
                price = float(price_data)

            # Build URL
            slug = listing.get("slug", "")
            item_url = f"{self.base_url}/listings/{item_id}" if not slug else f"{self.base_url}/listings/{slug}"

            # Get images
            photos = listing.get("photos", [])
            image_url = None
            if photos and len(photos) > 0:
                image_url = photos[0].get("url", None)

            # Get location
            location = None
            seller = listing.get("seller", {})
            if seller:
                location = seller.get("location", None)

            seller_name = seller.get("username", None) if seller else None

            # Get description
            description = listing.get("description", None)

            return ScrapedItem(
                platform_item_id=item_id,
                title=title.strip(),
                price=price,
                url=item_url,
                description=description,
                image_url=image_url,
                location=location,
                seller_name=seller_name,
                currency="USD",
            )

        except Exception as e:
            self.logger.warning(f"Error parsing Grailed listing: {e}")
            return None

    async def close(self) -> None:
        """Close aiohttp session."""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
        self.logger.info("Grailed scraper closed")


# Import for retry decorator
import asyncio
