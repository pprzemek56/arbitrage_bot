"""
Fetcher strategies implementing the Strategy pattern.
Each strategy handles different types of content fetching.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
import requests
from playwright.async_api import async_playwright, Page, Browser
from urllib.parse import urljoin, urlparse

from .config_schema import FetcherConfig, FetcherType

logger = logging.getLogger(__name__)


class FetchResult:
    """Result container for fetch operations."""

    def __init__(self, content: str, url: str, status_code: int = 200,
                 headers: Optional[Dict[str, str]] = None, metadata: Optional[Dict[str, Any]] = None):
        self.content = content
        self.url = url
        self.status_code = status_code
        self.headers = headers or {}
        self.metadata = metadata or {}
        self.timestamp = asyncio.get_event_loop().time()


class FetcherStrategy(ABC):
    """Abstract base class for fetching strategies."""

    def __init__(self, config: FetcherConfig):
        self.config = config
        self.logger = logging.getLogger(f"{self.__class__.__module__}.{self.__class__.__name__}")

    @abstractmethod
    async def fetch(self, url: str, **kwargs) -> FetchResult:
        """Fetch content from the given URL."""
        pass

    @abstractmethod
    async def cleanup(self):
        """Clean up resources."""
        pass

    def is_allowed_domain(self, url: str, allowed_domains: List[str]) -> bool:
        """Check if URL domain is in allowed domains list."""
        if not allowed_domains:
            return True

        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        return any(domain == allowed.lower() or domain.endswith(f'.{allowed.lower()}')
                   for allowed in allowed_domains)


class StaticFetcher(FetcherStrategy):
    """Static HTTP fetcher using requests."""

    def __init__(self, config: FetcherConfig):
        super().__init__(config)
        self.session = requests.Session()

        # Set up headers
        default_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        default_headers.update(config.headers)
        self.session.headers.update(default_headers)

    async def fetch(self, url: str, **kwargs) -> FetchResult:
        """Fetch content using HTTP requests."""
        self.logger.info(f"Fetching static content from: {url}")

        try:
            method = kwargs.get('method', self.config.method or 'GET')
            timeout = kwargs.get('timeout', self.config.timeout_ms / 1000)

            response = self.session.request(
                method=method,
                url=url,
                timeout=timeout,
                **kwargs
            )
            response.raise_for_status()

            self.logger.debug(f"Successfully fetched {url} ({len(response.text)} bytes)")

            return FetchResult(
                content=response.text,
                url=response.url,
                status_code=response.status_code,
                headers=dict(response.headers),
                metadata={'method': method, 'final_url': response.url}
            )

        except requests.RequestException as e:
            self.logger.error(f"Error fetching {url}: {e}")
            raise

    async def cleanup(self):
        """Close the session."""
        self.session.close()


class BrowserFetcher(FetcherStrategy):
    """Browser-based fetcher using Playwright."""

    def __init__(self, config: FetcherConfig):
        super().__init__(config)
        self.browser: Optional[Browser] = None
        self.context = None
        self._playwright = None

    async def _ensure_browser(self):
        """Ensure browser is initialized."""
        if self.browser is None:
            self._playwright = await async_playwright().start()

            browser_args = [
                '--disable-gpu',
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor'
            ]

            self.browser = await self._playwright.chromium.launch(
                headless=self.config.headless,
                args=browser_args
            )

            self.context = await self.browser.new_context(
                viewport=self.config.viewport,
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )

    async def fetch(self, url: str, **kwargs) -> FetchResult:
        """Fetch content using browser."""
        self.logger.info(f"Fetching browser content from: {url}")

        await self._ensure_browser()

        page = await self.context.new_page()

        try:
            # Set up request/response interceptors if needed
            await page.goto(
                url,
                wait_until='domcontentloaded',
                timeout=self.config.timeout_ms
            )

            # Wait for any additional conditions
            wait_condition = kwargs.get('wait_condition')
            if wait_condition:
                await self._handle_wait_condition(page, wait_condition)

            content = await page.content()
            final_url = page.url

            self.logger.debug(f"Successfully fetched browser content ({len(content)} bytes)")

            return FetchResult(
                content=content,
                url=final_url,
                status_code=200,
                metadata={'original_url': url, 'final_url': final_url}
            )

        except Exception as e:
            self.logger.error(f"Error fetching {url} with browser: {e}")
            raise
        finally:
            await page.close()

    async def _handle_wait_condition(self, page: Page, condition: Dict[str, Any]):
        """Handle wait conditions."""
        condition_type = condition.get('type', 'timeout')
        timeout = condition.get('timeout_ms', 30000)

        if condition_type == 'timeout':
            await page.wait_for_timeout(condition.get('value', 1000))
        elif condition_type == 'selector':
            await page.wait_for_selector(condition['value'], timeout=timeout)
        elif condition_type == 'url_contains':
            await page.wait_for_url(f"**/*{condition['value']}*", timeout=timeout)
        elif condition_type == 'element_count':
            # Wait for specific number of elements
            selector = condition.get('selector', 'body')
            count = condition.get('value', 1)
            await page.wait_for_function(
                f"document.querySelectorAll('{selector}').length >= {count}",
                timeout=timeout
            )

    async def cleanup(self):
        """Clean up browser resources."""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()


class APIFetcher(FetcherStrategy):
    """API-specific fetcher with authentication and JSON handling."""

    def __init__(self, config: FetcherConfig):
        super().__init__(config)
        self.session = requests.Session()

        # Set up headers for API
        default_headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        default_headers.update(config.headers)
        self.session.headers.update(default_headers)

        # Set up authentication
        if config.auth:
            auth_type = config.auth.get('type', 'basic')
            if auth_type == 'basic':
                self.session.auth = (config.auth['username'], config.auth['password'])
            elif auth_type == 'bearer':
                self.session.headers['Authorization'] = f"Bearer {config.auth['token']}"
            elif auth_type == 'api_key':
                key_header = config.auth.get('header', 'X-API-Key')
                self.session.headers[key_header] = config.auth['key']

    async def fetch(self, url: str, **kwargs) -> FetchResult:
        """Fetch content from API endpoint."""
        self.logger.info(f"Fetching API content from: {url}")

        try:
            method = kwargs.get('method', self.config.method or 'GET')
            timeout = kwargs.get('timeout', self.config.timeout_ms / 1000)

            request_kwargs = {
                'timeout': timeout,
                **kwargs
            }

            # Handle JSON body
            if method in ['POST', 'PUT', 'PATCH'] and self.config.body:
                request_kwargs['json'] = self.config.body

            response = self.session.request(method, url, **request_kwargs)
            response.raise_for_status()

            # Try to parse as JSON, fall back to text
            try:
                content = response.json()
                content_str = str(content)  # Convert to string for consistency
            except ValueError:
                content_str = response.text

            self.logger.debug(f"Successfully fetched API response ({len(content_str)} bytes)")

            return FetchResult(
                content=content_str,
                url=response.url,
                status_code=response.status_code,
                headers=dict(response.headers),
                metadata={'method': method, 'content_type': response.headers.get('content-type')}
            )

        except requests.RequestException as e:
            self.logger.error(f"Error fetching API {url}: {e}")
            raise

    async def cleanup(self):
        """Close the session."""
        self.session.close()


class InteractiveFetcher(BrowserFetcher):
    """Interactive fetcher that can execute instructions."""

    def __init__(self, config: FetcherConfig):
        super().__init__(config)
        self.current_page: Optional[Page] = None

    async def create_session(self) -> Page:
        """Create a persistent browser session."""
        await self._ensure_browser()
        self.current_page = await self.context.new_page()
        return self.current_page

    async def navigate(self, url: str) -> FetchResult:
        """Navigate to URL in current session."""
        if not self.current_page:
            await self.create_session()

        self.logger.info(f"Navigating to: {url}")

        await self.current_page.goto(
            url,
            wait_until='domcontentloaded',
            timeout=self.config.timeout_ms
        )

        content = await self.current_page.content()
        final_url = self.current_page.url

        return FetchResult(
            content=content,
            url=final_url,
            status_code=200,
            metadata={'original_url': url, 'final_url': final_url}
        )

    async def get_current_content(self) -> FetchResult:
        """Get current page content without navigation."""
        if not self.current_page:
            raise RuntimeError("No active session. Call create_session() first.")

        content = await self.current_page.content()
        url = self.current_page.url

        return FetchResult(
            content=content,
            url=url,
            status_code=200,
            metadata={'current_page': True}
        )

    async def fetch(self, url: str, **kwargs) -> FetchResult:
        """For compatibility, perform navigation."""
        return await self.navigate(url)

    async def close_session(self):
        """Close current session."""
        if self.current_page:
            await self.current_page.close()
            self.current_page = None


class FetcherFactory:
    """Factory for creating fetcher instances."""

    _strategies = {
        FetcherType.STATIC: StaticFetcher,
        FetcherType.BROWSER: BrowserFetcher,
        FetcherType.API: APIFetcher,
        FetcherType.INTERACTIVE: InteractiveFetcher
    }

    @classmethod
    def create(cls, config: FetcherConfig) -> FetcherStrategy:
        """Create a fetcher instance based on configuration."""
        strategy_class = cls._strategies.get(config.type)

        if not strategy_class:
            raise ValueError(f"Unsupported fetcher type: {config.type}")

        return strategy_class(config)

    @classmethod
    def register_strategy(cls, fetcher_type: FetcherType, strategy_class: type):
        """Register a new fetcher strategy."""
        cls._strategies[fetcher_type] = strategy_class

    @classmethod
    def get_supported_types(cls) -> List[FetcherType]:
        """Get list of supported fetcher types."""
        return list(cls._strategies.keys())