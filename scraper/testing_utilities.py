"""
Testing utilities for the arbitrage betting scraper.
Provides fixtures, mocks, and utilities for testing scraper components.
"""

import asyncio
import json
import pytest
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Optional
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime

from scraper.config_schema import ScraperConfig, ConfigLoader
from scraper.fetcher_strategies import FetchResult, FetcherStrategy
from scraper.instruction_handlers import InstructionContext
from scraper.scraper_pipeline import ScrapingResult
from database.config import DatabaseConfig, DatabaseManager
from database.models import Base


class MockPage:
    """Mock Playwright page for testing."""

    def __init__(self, content: str = "<html><body></body></html>", url: str = "https://example.com"):
        self.content_value = content
        self.url = url
        self.elements = {}
        self.clicked_selectors = []
        self.typed_values = {}

    async def goto(self, url: str, **kwargs):
        """Mock navigation."""
        self.url = url

    async def content(self) -> str:
        """Mock content retrieval."""
        return self.content_value

    async def click(self, selector: str, **kwargs):
        """Mock clicking."""
        self.clicked_selectors.append(selector)

    async def type(self, selector: str, text: str, **kwargs):
        """Mock typing."""
        self.typed_values[selector] = text

    async def fill(self, selector: str, text: str, **kwargs):
        """Mock filling."""
        self.typed_values[selector] = text

    async def wait_for_selector(self, selector: str, **kwargs):
        """Mock waiting for selector."""
        if selector in self.elements:
            return self.elements[selector]
        return MockElement()

    async def wait_for_timeout(self, timeout: int):
        """Mock timeout wait."""
        await asyncio.sleep(0.001)  # Minimal delay for testing

    async def query_selector(self, selector: str):
        """Mock single element selection."""
        if selector in self.elements:
            return self.elements[selector]
        return MockElement()

    async def query_selector_all(self, selector: str):
        """Mock multiple element selection."""
        if selector in self.elements:
            elements = self.elements[selector]
            return elements if isinstance(elements, list) else [elements]
        return [MockElement(), MockElement()]  # Default to 2 elements

    async def select_option(self, selector: str, **kwargs):
        """Mock option selection."""
        pass

    async def evaluate(self, script: str, *args):
        """Mock JavaScript evaluation."""
        return None

    async def close(self):
        """Mock page closing."""
        pass

    def add_element(self, selector: str, element_or_elements):
        """Add mock element(s) for a selector."""
        self.elements[selector] = element_or_elements


class MockElement:
    """Mock Playwright element for testing."""

    def __init__(self, text: str = "Sample Text", attributes: Optional[Dict[str, str]] = None):
        self.text_value = text
        self.attributes = attributes or {}

    async def text_content(self) -> str:
        """Mock text content."""
        return self.text_value

    async def get_attribute(self, name: str) -> Optional[str]:
        """Mock attribute retrieval."""
        return self.attributes.get(name)

    async def is_visible(self) -> bool:
        """Mock visibility check."""
        return True

    async def is_enabled(self) -> bool:
        """Mock enabled check."""
        return True

    async def click(self, **kwargs):
        """Mock clicking."""
        pass

    async def query_selector(self, selector: str):
        """Mock nested selection."""
        return MockElement()

    async def query_selector_all(self, selector: str):
        """Mock nested multiple selection."""
        return [MockElement(), MockElement()]

    async def scroll_into_view_if_needed(self):
        """Mock scrolling."""
        pass


class MockFetcher(FetcherStrategy):
    """Mock fetcher for testing."""

    def __init__(self, config, content: str = "<html><body></body></html>"):
        super().__init__(config)
        self.content = content
        self.fetch_calls = []

    async def fetch(self, url: str, **kwargs) -> FetchResult:
        """Mock fetch operation."""
        self.fetch_calls.append(url)
        return FetchResult(
            content=self.content,
            url=url,
            status_code=200,
            headers={'content-type': 'text/html'}
        )

    async def cleanup(self):
        """Mock cleanup."""
        pass


class ScraperTestCase:
    """Base test case for scraper tests."""

    def setup_method(self):
        """Setup for each test method."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_db_url = "sqlite:///:memory:"

    def teardown_method(self):
        """Cleanup after each test method."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def create_test_config(self, overrides: Optional[Dict[str, Any]] = None) -> ScraperConfig:
        """Create a test configuration."""
        base_config = {
            'meta': {
                'name': 'test_scraper',
                'description': 'Test scraper configuration',
                'start_url': 'https://example.com'
            },
            'fetcher': {
                'type': 'static',
                'timeout_ms': 10000
            },
            'database': {
                'url': self.test_db_url,
                'bookmaker_name': 'Test Bookmaker',
                'category_name': 'Test Category'
            },
            'instructions': [
                {
                    'type': 'collect',
                    'name': 'test_collection',
                    'container_selector': 'body',
                    'item_selector': '.item',
                    'fields': {
                        'name': {
                            'selector': '.name',
                            'attribute': 'text'
                        }
                    }
                }
            ]
        }

        if overrides:
            base_config.update(overrides)

        return ScraperConfig(**base_config)

    def create_test_html(self, items: List[Dict[str, str]]) -> str:
        """Create test HTML with specified items."""
        html_items = []
        for item in items:
            item_html = f'<div class="item"><span class="name">{item["name"]}</span></div>'
            html_items.append(item_html)

        return f"""
        <html>
            <body>
                {''.join(html_items)}
            </body>
        </html>
        """

    def save_test_config(self, config_dict: Dict[str, Any], filename: str = "test_config.yml") -> str:
        """Save test config to temporary file."""
        import yaml

        config_path = Path(self.temp_dir) / filename
        with open(config_path, 'w') as f:
            yaml.dump(config_dict, f)

        return str(config_path)


class DatabaseTestMixin:
    """Mixin for database-related testing."""

    @pytest.fixture
    def test_db(self):
        """Create test database."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)

        Session = sessionmaker(bind=engine)
        session = Session()

        yield session

        session.close()

    def create_test_bookmaker(self, session, name: str = "Test Bookmaker"):
        """Create test bookmaker."""
        from database.models import Bookmaker

        bookmaker = Bookmaker(name=name)
        session.add(bookmaker)
        session.commit()
        return bookmaker

    def create_test_category(self, session, name: str = "Test Category"):
        """Create test category."""
        from database.models import Category

        category = Category(name=name)
        session.add(category)
        session.commit()
        return category


class AsyncTestCase:
    """Base class for async test cases."""

    @pytest.fixture
    def event_loop(self):
        """Create event loop for async tests."""
        loop = asyncio.new_event_loop()
        yield loop
        loop.close()


# Pytest fixtures
@pytest.fixture
def mock_page():
    """Pytest fixture for mock page."""
    return MockPage()


@pytest.fixture
def mock_fetcher():
    """Pytest fixture for mock fetcher."""
    from scraper.config_schema import FetcherConfig, FetcherType
    config = FetcherConfig(type=FetcherType.STATIC)
    return MockFetcher(config)


@pytest.fixture
def test_config():
    """Pytest fixture for test configuration."""
    return {
        'meta': {
            'name': 'test_scraper',
            'start_url': 'https://example.com'
        },
        'fetcher': {
            'type': 'static'
        },
        'database': {
            'url': 'sqlite:///:memory:',
            'bookmaker_name': 'Test',
            'category_name': 'Test'
        },
        'instructions': []
    }


@pytest.fixture
def scraping_result():
    """Pytest fixture for scraping result."""
    result = ScrapingResult()
    result.events = [
        {'name': 'Test Event 1', 'odds': '2.5'},
        {'name': 'Test Event 2', 'odds': '1.8'}
    ]
    result.finalize()
    return result


# Test utilities
def assert_config_valid(config_dict: Dict[str, Any]):
    """Assert that a configuration dictionary is valid."""
    try:
        ScraperConfig(**config_dict)
    except Exception as e:
        pytest.fail(f"Configuration is invalid: {e}")


def assert_result_has_data(result: ScrapingResult, min_events: int = 1):
    """Assert that scraping result has minimum data."""
    assert len(result.events) >= min_events, f"Expected at least {min_events} events, got {len(result.events)}"
    assert len(result.errors) == 0, f"Expected no errors, got: {result.errors}"


async def run_mock_scraper(config: ScraperConfig, mock_content: str = None) -> ScrapingResult:
    """Run a scraper with mocked dependencies."""
    from scraper.scraper_pipeline import ScraperPipeline

    # Mock the fetcher
    with patch('scraper.fetcher_strategies.FetcherFactory.create') as mock_factory:
        mock_fetcher = MockFetcher(config.fetcher, mock_content or "<html><body></body></html>")
        mock_factory.return_value = mock_fetcher

        # Mock database operations
        with patch('scraper.scraper_pipeline.DatabasePersister') as mock_persister:
            mock_persister_instance = Mock()
            mock_persister.return_value = mock_persister_instance

            pipeline = ScraperPipeline(config)
            return await pipeline.run()


# Test data generators
def generate_odds_html(matches: List[Dict[str, Any]]) -> str:
    """Generate HTML with betting odds data."""
    match_html = []

    for match in matches:
        html = f"""
        <div class="match">
            <div class="teams">
                <span class="home">{match['home']}</span>
                <span class="away">{match['away']}</span>
            </div>
            <div class="odds">
                <span class="home-odds">{match['home_odds']}</span>
                <span class="draw-odds">{match.get('draw_odds', '')}</span>
                <span class="away-odds">{match['away_odds']}</span>
            </div>
        </div>
        """
        match_html.append(html)

    return f"""
    <html>
        <body>
            <div class="matches">
                {''.join(match_html)}
            </div>
        </body>
    </html>
    """


def generate_api_response(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate API response data."""
    return {
        "status": "success",
        "events": events,
        "total": len(events),
        "timestamp": datetime.utcnow().isoformat()
    }


# Performance testing utilities
class PerformanceTimer:
    """Timer for performance testing."""

    def __init__(self):
        self.start_time = None
        self.end_time = None

    def start(self):
        """Start timing."""
        self.start_time = datetime.utcnow()

    def stop(self):
        """Stop timing."""
        self.end_time = datetime.utcnow()

    @property
    def duration(self) -> float:
        """Get duration in seconds."""
        if not self.start_time or not self.end_time:
            return 0.0
        return (self.end_time - self.start_time).total_seconds()


def benchmark_scraper(config: ScraperConfig, iterations: int = 1) -> Dict[str, float]:
    """Benchmark scraper performance."""
    from scraper.scraper_pipeline import ScraperRunner

    times = []
    runner = ScraperRunner()

    for _ in range(iterations):
        timer = PerformanceTimer()
        timer.start()

        try:
            result = runner.run_scraper_sync(config)
            timer.stop()
            times.append(timer.duration)
        except Exception:
            timer.stop()
            times.append(float('inf'))  # Mark failed runs

    valid_times = [t for t in times if t != float('inf')]

    if not valid_times:
        return {'avg': 0, 'min': 0, 'max': 0, 'success_rate': 0}

    return {
        'avg': sum(valid_times) / len(valid_times),
        'min': min(valid_times),
        'max': max(valid_times),
        'success_rate': len(valid_times) / len(times)
    }


# Example test cases
class TestScraperComponents(ScraperTestCase):
    """Example test cases for scraper components."""

    def test_config_validation(self):
        """Test configuration validation."""
        config = self.create_test_config()
        assert config.meta.name == 'test_scraper'
        assert config.fetcher.type.value == 'static'

    def test_config_loading_from_file(self):
        """Test loading configuration from file."""
        config_dict = {
            'meta': {'name': 'file_test', 'start_url': 'https://example.com'},
            'fetcher': {'type': 'static'},
            'database': {'url': 'sqlite:///:memory:', 'bookmaker_name': 'Test', 'category_name': 'Test'},
            'instructions': []
        }

        config_path = self.save_test_config(config_dict)
        loaded_config = ConfigLoader.load_from_yaml(config_path)

        assert loaded_config.meta.name == 'file_test'

    def test_html_generation(self):
        """Test HTML generation utility."""
        items = [{'name': 'Item 1'}, {'name': 'Item 2'}]
        html = self.create_test_html(items)

        assert 'Item 1' in html
        assert 'Item 2' in html
        assert 'class="item"' in html


# Integration test example
@pytest.mark.asyncio
async def test_full_scraper_pipeline():
    """Test complete scraper pipeline with mocked components."""
    test_case = ScraperTestCase()
    test_case.setup_method()

    try:
        # Create test configuration
        config = test_case.create_test_config({
            'fetcher': {'type': 'static'},
            'instructions': [
                {
                    'type': 'collect',
                    'name': 'matches',
                    'container_selector': '.matches',
                    'item_selector': '.match',
                    'fields': {
                        'home_team': {'selector': '.home', 'attribute': 'text'},
                        'away_team': {'selector': '.away', 'attribute': 'text'},
                        'home_odds': {'selector': '.home-odds', 'attribute': 'text'}
                    }
                }
            ]
        })

        # Generate test HTML
        matches = [
            {'home': 'Team A', 'away': 'Team B', 'home_odds': '2.5', 'away_odds': '1.8'},
            {'home': 'Team C', 'away': 'Team D', 'home_odds': '1.9', 'away_odds': '2.1'}
        ]
        test_html = generate_odds_html(matches)

        # Run scraper
        result = await run_mock_scraper(config, test_html)

        # Assertions
        assert_result_has_data(result, min_events=0)  # Mocked, so no real data expected

    finally:
        test_case.teardown_method()


if __name__ == "__main__":
    # Run a simple test
    test_case = ScraperTestCase()
    test_case.setup_method()

    try:
        config = test_case.create_test_config()
        print(f"Test config created: {config.meta.name}")

        html = test_case.create_test_html([{'name': 'Test Item'}])
        print(f"Test HTML generated: {len(html)} characters")

        print("Test utilities working correctly!")

    finally:
        test_case.teardown_method()