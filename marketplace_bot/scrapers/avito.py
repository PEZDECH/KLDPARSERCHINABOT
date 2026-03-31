"""
Avito scraper using Playwright with stealth mode.
"""

import asyncio
from typing import Optional
from urllib.parse import quote

from playwright.async_api import Browser, BrowserContext, Page, async_playwright
from playwright_stealth import stealth_async

from config import settings
from scrapers.base import BaseScraper, ScrapedItem
from utils.logger import logger
from utils.retry import retry_with_backoff


class AvitoScraper(BaseScraper):
    """
    Scraper for Avito.ru marketplace.
    Uses Playwright with stealth mode to bypass detection.
    """

    def __init__(self, proxy: Optional[str] = None) -> None:
        """Initialize Avito scraper with Playwright."""
        super().__init__(proxy)
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self._lock = asyncio.Lock()

    @property
    def platform_name(self) -> str:
        """Return platform name."""
        return "avito"

    @property
    def base_url(self) -> str:
        """Return Avito base URL."""
        return "https://www.avito.ru"

    async def _init_browser(self) -> None:
        """Initialize Playwright browser if not already initialized."""
        if self.browser is None:
            async with self._lock:
                if self.browser is None:
                    self.playwright = await async_playwright().start()

                    browser_args = []
                    if self.proxy:
                        browser_args.append(f"--proxy-server={self.proxy}")

                    self.browser = await self.playwright.chromium.launch(
                        headless=settings.playwright_headless,
                        args=browser_args,
                    )

                    self.context = await self.browser.new_context(
                        viewport={"width": 1920, "height": 1080},
                        user_agent=self.ua.random,
                        locale="ru-RU",
                        timezone_id="Europe/Moscow",
                    )

                    logger.info("Playwright browser initialized for Avito")

    async def _get_page(self) -> Page:
        """Get a new page from the browser context."""
        await self._init_browser()
        page = await self.context.new_page()
        await stealth_async(page)
        return page

    def build_search_url(
        self,
        query: str,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
    ) -> str:
        """
        Build Avito search URL.

        Args:
            query: Search query
            min_price: Minimum price
            max_price: Maximum price

        Returns:
            Avito search URL
        """
        encoded_query = quote(query)
        url = f"{self.base_url}/rossiya?q={encoded_query}"

        params = []
        if min_price is not None:
            params.append(f"pmin={int(min_price)}")
        if max_price is not None:
            params.append(f"pmax={int(max_price)}")

        if params:
            url += "&" + "&".join(params)

        # Add sorting by date (newest first)
        url += "&s=104"  # 104 = sort by date

        return url

    @retry_with_backoff(
        exceptions=(Exception,),
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
        Fetch latest items from Avito.

        Args:
            query: Search query
            min_price: Minimum price filter
            max_price: Maximum price filter
            limit: Maximum items to return

        Returns:
            List of ScrapedItem objects
        """
        url = self.build_search_url(query, min_price, max_price)
        self.logger.info(f"Fetching items from Avito: {url}")

        page = None
        items = []

        try:
            page = await self._get_page()

            # Navigate to search page
            await page.goto(url, wait_until="networkidle", timeout=settings.playwright_timeout)

            # Wait for items to load
            await page.wait_for_selector("[data-marker='item']", timeout=10000)

            # Extract items
            item_elements = await page.query_selector_all("[data-marker='item']")

            for element in item_elements[:limit]:
                try:
                    item = await self._parse_item(element)
                    if item and self.is_price_in_range(item.price, min_price, max_price):
                        items.append(item)
                except Exception as e:
                    self.logger.warning(f"Failed to parse item: {e}")
                    continue

            self.logger.info(f"Successfully fetched {len(items)} items from Avito")

        except Exception as e:
            self.logger.error(f"Error fetching from Avito: {e}")
            raise

        finally:
            if page:
                await page.close()

        return items

    async def _parse_item(self, element) -> Optional[ScrapedItem]:
        """
        Parse a single item element from Avito page.

        Args:
            element: Playwright element handle

        Returns:
            ScrapedItem or None if parsing fails
        """
        try:
            # Extract item ID
            item_id = await element.get_attribute("data-item-id")
            if not item_id:
                return None

            # Extract title
            title_elem = await element.query_selector("[itemprop='name']")
            if not title_elem:
                title_elem = await element.query_selector("h3")
            title = await title_elem.inner_text() if title_elem else "Без названия"

            # Extract price
            price_elem = await element.query_selector("[itemprop='price']")
            if not price_elem:
                price_elem = await element.query_selector("[data-marker='item-price']")

            price_text = ""
            if price_elem:
                price_text = await price_elem.get_attribute("content") or await price_elem.inner_text()

            price = self.normalize_price(price_text) if price_text else 0.0

            # Extract URL
            link_elem = await element.query_selector("[itemprop='url']")
            if not link_elem:
                link_elem = await element.query_selector("a[data-marker='item-title']")

            item_url = ""
            if link_elem:
                href = await link_elem.get_attribute("href")
                if href:
                    item_url = href if href.startswith("http") else f"{self.base_url}{href}"

            # Extract image
            image_elem = await element.query_selector("img")
            image_url = None
            if image_elem:
                image_url = await image_elem.get_attribute("src")
                if not image_url:
                    image_url = await image_elem.get_attribute("data-src")

            # Extract location
            location_elem = await element.query_selector("[data-marker='item-address']")
            location = await location_elem.inner_text() if location_elem else None

            # Extract seller info (if available)
            seller_elem = await element.query_selector("[data-marker='seller-info/name']")
            seller_name = await seller_elem.inner_text() if seller_elem else None

            return ScrapedItem(
                platform_item_id=item_id,
                title=title.strip(),
                price=price,
                url=item_url,
                image_url=image_url,
                location=location.strip() if location else None,
                seller_name=seller_name.strip() if seller_name else None,
                currency="RUB",
            )

        except Exception as e:
            self.logger.warning(f"Error parsing Avito item: {e}")
            return None

    async def close(self) -> None:
        """Close Playwright browser and context."""
        if self.context:
            await self.context.close()
            self.context = None

        if self.browser:
            await self.browser.close()
            self.browser = None

        if self.playwright:
            await self.playwright.stop()
            self.playwright = None

        self.logger.info("Avito scraper closed")
