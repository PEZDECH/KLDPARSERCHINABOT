"""
Mercari scraper using aiohttp with API requests.
"""

import asyncio
import json
from typing import Optional
from urllib.parse import quote

import aiohttp

from config import settings
from scrapers.base import BaseScraper, ScrapedItem
from utils.logger import logger
from utils.retry import retry_with_backoff


class MercariScraper(BaseScraper):
    """
    Scraper for Mercari marketplace.
    Uses aiohttp for API-based scraping.
    """

    def __init__(self, proxy: Optional[str] = None) -> None:
        """Initialize Mercari scraper."""
        super().__init__(proxy)
        self.session: Optional[aiohttp.ClientSession] = None
        self.api_base = "https://api.mercari.jp"
        self.dpof_base = "https://www.mercari.com"

    @property
    def platform_name(self) -> str:
        """Return platform name."""
        return "mercari"

    @property
    def base_url(self) -> str:
        """Return Mercari base URL."""
        return "https://www.mercari.com"

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self.session is None or self.session.closed:
            connector = aiohttp.TCPConnector(
                limit=10,
                limit_per_host=5,
                ttl_dns_cache=300,
            )

            timeout = aiohttp.ClientTimeout(total=settings.request_timeout)

            headers = self.get_headers()
            # Mercari-specific headers
            headers.update({
                "X-Platform": "web",
                "Accept": "application/json, text/plain, */*",
            })

            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers=headers,
            )
        return self.session

    def build_search_url(
        self,
        query: str,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
    ) -> str:
        """
        Build Mercari search URL.

        Args:
            query: Search query
            min_price: Minimum price
            max_price: Maximum price

        Returns:
            Mercari search URL
        """
        encoded_query = quote(query)
        url = f"{self.base_url}/search/?keyword={encoded_query}"

        if min_price is not None:
            url += f"&price_min={int(min_price)}"
        if max_price is not None:
            url += f"&price_max={int(max_price)}"

        # Sort by new
        url += "&sort=created_time&order=desc"

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
        Fetch latest items from Mercari.

        Args:
            query: Search query
            min_price: Minimum price filter
            max_price: Maximum price filter
            limit: Maximum items to return

        Returns:
            List of ScrapedItem objects
        """
        self.logger.info(f"Fetching items from Mercari for query: {query}")

        session = await self._get_session()
        items = []

        try:
            # Mercari uses a complex API, we'll use their search endpoint
            search_url = f"{self.dpof_base}/v1/api"

            # Build search parameters
            search_params = {
                "keyword": query,
                "sortBy": "created_time",
                "sortOrder": "desc",
                "limit": limit,
            }

            if min_price is not None:
                search_params["priceMin"] = int(min_price)
            if max_price is not None:
                search_params["priceMax"] = int(max_price)

            # Try alternative approach using search endpoint
            payload = {
                "operationName": "Search",
                "variables": search_params,
                "query": """
                query Search($keyword: String!, $limit: Int, $priceMin: Int, $priceMax: Int) {
                    search(keyword: $keyword, limit: $limit, priceMin: $priceMin, priceMax: $priceMax) {
                        items {
                            id
                            name
                            price
                            status
                            photos
                            seller {
                                id
                                name
                            }
                        }
                    }
                }
                """
            }

            async with session.post(
                search_url,
                json=payload,
                proxy=self.proxy,
            ) as response:
                if response.status == 403:
                    self.logger.error("Mercari returned 403 - access denied")
                    raise aiohttp.ClientError("Access denied by Mercari")

                if response.status == 429:
                    self.logger.warning("Mercari rate limit hit")
                    raise aiohttp.ClientError("Rate limited by Mercari")

                response.raise_for_status()

                data = await response.json()

                # Parse items from response
                search_data = data.get("data", {}).get("search", {})
                mercari_items = search_data.get("items", [])

                for item_data in mercari_items[:limit]:
                    try:
                        item = self._parse_item(item_data)
                        if item and self.is_price_in_range(item.price, min_price, max_price):
                            items.append(item)
                    except Exception as e:
                        self.logger.warning(f"Failed to parse Mercari item: {e}")
                        continue

            self.logger.info(f"Successfully fetched {len(items)} items from Mercari")

        except Exception as e:
            self.logger.error(f"Error fetching from Mercari: {e}")
            # Return empty list instead of raising to avoid breaking the bot
            # Mercari has strong anti-bot protection
            return []

        return items

    def _parse_item(self, item_data: dict) -> Optional[ScrapedItem]:
        """
        Parse a single Mercari item from API response.

        Args:
            item_data: Item data from API

        Returns:
            ScrapedItem or None if parsing fails
        """
        try:
            item_id = str(item_data.get("id", ""))
            if not item_id:
                return None

            title = item_data.get("name", "Unknown Item")

            # Get price - Mercari prices are in JPY (Japan) or USD (US)
            price = float(item_data.get("price", 0))

            # Build URL
            item_url = f"{self.base_url}/item/{item_id}"

            # Get images
            photos = item_data.get("photos", [])
            image_url = None
            if photos and len(photos) > 0:
                image_url = photos[0]

            # Get seller info
            seller = item_data.get("seller", {})
            seller_name = seller.get("name", None) if seller else None

            # Determine currency based on seller location (default to USD for US Mercari)
            currency = "USD"

            return ScrapedItem(
                platform_item_id=item_id,
                title=title.strip(),
                price=price,
                url=item_url,
                image_url=image_url,
                seller_name=seller_name,
                currency=currency,
            )

        except Exception as e:
            self.logger.warning(f"Error parsing Mercari item: {e}")
            return None

    async def close(self) -> None:
        """Close aiohttp session."""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
        self.logger.info("Mercari scraper closed")
