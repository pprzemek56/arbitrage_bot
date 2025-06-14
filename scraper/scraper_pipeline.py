"""
Main scraper pipeline that orchestrates the entire scraping process.
Coordinates fetching, instruction execution, data extraction, and persistence.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from contextlib import asynccontextmanager

from .config_schema import ScraperConfig, FetcherType
from .fetcher_strategies import FetcherFactory, FetcherStrategy, InteractiveFetcher
from .instruction_handlers import InstructionExecutor, InstructionContext
from .processor_registry import processor_registry
from database.config import get_db_manager
from database.models import Bookmaker, Category, Event, NormalizedEvent, Market, MarketSelection

logger = logging.getLogger(__name__)


class ScrapingResult:
    """Container for scraping results."""

    def __init__(self):
        self.events: List[Dict[str, Any]] = []
        self.markets: List[Dict[str, Any]] = []
        self.selections: List[Dict[str, Any]] = []
        self.errors: List[str] = []
        self.metadata: Dict[str, Any] = {}
        self.start_time: datetime = datetime.utcnow()
        self.end_time: Optional[datetime] = None

    def add_error(self, error: str):
        """Add an error to the results."""
        self.errors.append(error)
        logger.error(error)

    def finalize(self):
        """Mark the scraping as complete."""
        self.end_time = datetime.utcnow()
        self.metadata['duration_seconds'] = (self.end_time - self.start_time).total_seconds()
        self.metadata['total_events'] = len(self.events)
        self.metadata['total_markets'] = len(self.markets)
        self.metadata['total_selections'] = len(self.selections)
        self.metadata['error_count'] = len(self.errors)


class DatabasePersister:
    """Handles database persistence operations."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def get_or_create_bookmaker(self, name: str) -> Bookmaker:
        """Get or create bookmaker by name."""
        db_manager = get_db_manager()

        with db_manager.get_session() as session:
            bookmaker = session.query(Bookmaker).filter_by(name=name).first()

            if not bookmaker:
                bookmaker = Bookmaker(name=name)
                session.add(bookmaker)
                session.commit()
                self.logger.info(f"Created new bookmaker: {name}")

            return bookmaker

    def get_or_create_category(self, name: str) -> Category:
        """Get or create category by name."""
        db_manager = get_db_manager()

        with db_manager.get_session() as session:
            category = session.query(Category).filter_by(name=name).first()

            if not category:
                category = Category(name=name)
                session.add(category)
                session.commit()
                self.logger.info(f"Created new category: {name}")

            return category

    def save_event_data(self, event_data: Dict[str, Any], bookmaker_id: int, category_id: int) -> int:
        """Save event data to database."""
        db_manager = get_db_manager()

        with db_manager.get_session() as session:
            # Create event
            event = Event(
                bookmaker_id=bookmaker_id,
                category_id=category_id,
                status=event_data.get('status', 'active')
            )
            session.add(event)
            session.flush()  # Get event ID

            # Create normalized event
            mapping_hash = self._generate_mapping_hash(event_data)
            normalized_event = NormalizedEvent(
                event_id=event.id,
                mapping_hash=mapping_hash
            )
            session.add(normalized_event)
            session.flush()

            # Save markets and selections
            for market_data in event_data.get('markets', []):
                market = Market(
                    normalized_event_id=normalized_event.id,
                    market_type=market_data.get('type', 'unknown')
                )
                session.add(market)
                session.flush()

                for selection_data in market_data.get('selections', []):
                    selection = MarketSelection(
                        market_id=market.id,
                        selection=selection_data.get('name', ''),
                        odds=selection_data.get('odds', 0.0)
                    )
                    session.add(selection)

            session.commit()
            return event.id

    def _generate_mapping_hash(self, event_data: Dict[str, Any]) -> str:
        """Generate mapping hash for event normalization."""
        import hashlib

        # Use event name, teams, or other identifying information
        identifier = f"{event_data.get('name', '')}{event_data.get('teams', '')}{event_data.get('date', '')}"
        return hashlib.md5(identifier.encode()).hexdigest()


class ScraperPipeline:
    """Main scraper pipeline that orchestrates the entire process."""

    def __init__(self, config: ScraperConfig):
        self.config = config
        self.fetcher: Optional[FetcherStrategy] = None
        self.instruction_executor = InstructionExecutor()
        self.persister = DatabasePersister()
        self.logger = logging.getLogger(__name__)

    async def run(self) -> ScrapingResult:
        """Run the complete scraping pipeline."""
        result = ScrapingResult()

        try:
            self.logger.info(f"Starting scraper pipeline: {self.config.meta.name}")

            # Initialize fetcher
            self.fetcher = FetcherFactory.create(self.config.fetcher)

            # Execute scraping based on fetcher type
            if self.config.fetcher.type == FetcherType.INTERACTIVE:
                await self._run_interactive_scraping(result)
            else:
                await self._run_simple_scraping(result)

            # Persist results to database
            await self._persist_results(result)

        except Exception as e:
            result.add_error(f"Pipeline error: {str(e)}")
            self.logger.error(f"Pipeline failed: {e}", exc_info=True)

        finally:
            # Cleanup
            if self.fetcher:
                await self.fetcher.cleanup()

            result.finalize()
            self.logger.info(f"Pipeline completed. Events: {len(result.events)}, Errors: {len(result.errors)}")

        return result

    async def _run_simple_scraping(self, result: ScrapingResult):
        """Run simple scraping (static/browser fetching)."""
        try:
            # Fetch initial content
            fetch_result = await self.fetcher.fetch(self.config.meta.start_url)
            result.metadata['initial_fetch_size'] = len(fetch_result.content)

            # If no instructions, just extract from static content
            if not self.config.instructions:
                await self._extract_from_content(fetch_result.content, result)
            else:
                # This would require browser for instructions
                result.add_error("Instructions require interactive fetcher")

        except Exception as e:
            result.add_error(f"Simple scraping error: {str(e)}")

    async def _run_interactive_scraping(self, result: ScrapingResult):
        """Run interactive scraping with instruction execution."""
        if not isinstance(self.fetcher, InteractiveFetcher):
            result.add_error("Interactive scraping requires InteractiveFetcher")
            return

        try:
            # Create browser session
            page = await self.fetcher.create_session()

            # Navigate to start URL
            await self.fetcher.navigate(self.config.meta.start_url)

            # Create instruction context
            context = InstructionContext(page)

            # Execute instructions
            for instruction in self.config.instructions:
                success = await self.instruction_executor.execute_instruction(instruction, context)
                if not success:
                    self.logger.warning(f"Instruction failed: {instruction.type}")

            # Process collected data
            for collection_name, collected_items in context.collected_data.items():
                await self._process_collected_data(collection_name, collected_items, result)

            # If no collections were defined, extract from final page
            if not context.collected_data:
                final_content = await self.fetcher.get_current_content()
                await self._extract_from_content(final_content.content, result)

        except Exception as e:
            result.add_error(f"Interactive scraping error: {str(e)}")

        finally:
            if isinstance(self.fetcher, InteractiveFetcher):
                await self.fetcher.close_session()

    async def _extract_from_content(self, content: str, result: ScrapingResult):
        """Extract data from HTML content using basic extraction rules."""
        # This is a simplified extraction - in practice you'd want more sophisticated parsing
        # For now, just log that content was received
        self.logger.info(f"Extracting from content ({len(content)} chars)")

        # Here you would implement HTML parsing logic similar to the original extractor
        # but adapted for betting data

        # For demonstration, create a dummy event
        dummy_event = {
            'name': 'Sample Event',
            'status': 'active',
            'markets': [
                {
                    'type': 'match_winner',
                    'selections': [
                        {'name': 'Team A', 'odds': 2.5},
                        {'name': 'Team B', 'odds': 1.8}
                    ]
                }
            ]
        }
        result.events.append(dummy_event)

    async def _process_collected_data(self, collection_name: str, items: List[Dict[str, Any]], result: ScrapingResult):
        """Process collected data from instructions."""
        self.logger.info(f"Processing {len(items)} items from collection: {collection_name}")

        for item in items:
            # Process each field through configured processors
            processed_item = await self._process_item_fields(item)

            # Categorize the item based on collection name or content
            if 'event' in collection_name.lower():
                result.events.append(processed_item)
            elif 'market' in collection_name.lower():
                result.markets.append(processed_item)
            elif 'selection' in collection_name.lower() or 'odds' in collection_name.lower():
                result.selections.append(processed_item)
            else:
                # Default to events
                result.events.append(processed_item)

    async def _process_item_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Process item fields through configured processors."""
        processed_item = {}

        for field_name, field_value in item.items():
            # Get processor configuration for this field (if any)
            # This would come from field configuration in instructions
            processors = []  # Would be loaded from config

            if processors:
                # Apply processors
                processed_value = processor_registry.process_value(
                    field_value,
                    processors,
                    context={'base_url': self.config.meta.start_url}
                )
            else:
                processed_value = field_value

            processed_item[field_name] = processed_value

        return processed_item

    async def _persist_results(self, result: ScrapingResult):
        """Persist scraping results to database."""
        try:
            # Get or create bookmaker and category
            bookmaker = self.persister.get_or_create_bookmaker(self.config.database.bookmaker_name)
            category = self.persister.get_or_create_category(self.config.database.category_name)

            # Save events
            for event_data in result.events:
                try:
                    event_id = self.persister.save_event_data(event_data, bookmaker.id, category.id)
                    self.logger.debug(f"Saved event with ID: {event_id}")
                except Exception as e:
                    result.add_error(f"Failed to save event: {str(e)}")

            self.logger.info(f"Persisted {len(result.events)} events to database")

        except Exception as e:
            result.add_error(f"Persistence error: {str(e)}")


class ScraperRunner:
    """High-level interface for running scrapers."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    async def run_scraper(self, config: ScraperConfig) -> ScrapingResult:
        """Run a scraper with the given configuration."""
        pipeline = ScraperPipeline(config)
        return await pipeline.run()

    async def run_scraper_from_file(self, config_path: str) -> ScrapingResult:
        """Run a scraper from a configuration file."""
        from .config_schema import ConfigLoader

        try:
            config = ConfigLoader.load_from_yaml(config_path)
            return await self.run_scraper(config)
        except Exception as e:
            self.logger.error(f"Failed to load config from {config_path}: {e}")
            result = ScrapingResult()
            result.add_error(f"Config loading error: {str(e)}")
            result.finalize()
            return result

    def run_scraper_sync(self, config: ScraperConfig) -> ScrapingResult:
        """Synchronous wrapper for running scraper."""
        return asyncio.run(self.run_scraper(config))

    def run_scraper_from_file_sync(self, config_path: str) -> ScrapingResult:
        """Synchronous wrapper for running scraper from file."""
        return asyncio.run(self.run_scraper_from_file(config_path))


# Context manager for automatic cleanup
@asynccontextmanager
async def scraper_session(config: ScraperConfig):
    """Context manager for scraper sessions with automatic cleanup."""
    pipeline = ScraperPipeline(config)

    try:
        # Initialize fetcher
        pipeline.fetcher = FetcherFactory.create(config.fetcher)
        yield pipeline
    finally:
        # Cleanup
        if pipeline.fetcher:
            await pipeline.fetcher.cleanup()


# Convenience functions
async def run_scraper(config: ScraperConfig) -> ScrapingResult:
    """Convenience function to run a scraper."""
    runner = ScraperRunner()
    return await runner.run_scraper(config)


async def run_scraper_from_file(config_path: str) -> ScrapingResult:
    """Convenience function to run a scraper from file."""
    runner = ScraperRunner()
    return await runner.run_scraper_from_file(config_path)


def run_scraper_sync(config: ScraperConfig) -> ScrapingResult:
    """Synchronous convenience function to run a scraper."""
    runner = ScraperRunner()
    return runner.run_scraper_sync(config)


def run_scraper_from_file_sync(config_path: str) -> ScrapingResult:
    """Synchronous convenience function to run a scraper from file."""
    runner = ScraperRunner()
    return runner.run_scraper_from_file_sync(config_path)


# Example usage
if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python scraper_pipeline.py <config_file>")
        sys.exit(1)

    config_file = sys.argv[1]

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Run scraper
    result = run_scraper_from_file_sync(config_file)

    # Print results
    print(f"Scraping completed:")
    print(f"  Events: {len(result.events)}")
    print(f"  Markets: {len(result.markets)}")
    print(f"  Selections: {len(result.selections)}")
    print(f"  Errors: {len(result.errors)}")
    print(f"  Duration: {result.metadata.get('duration_seconds', 0):.2f}s")

    if result.errors:
        print("\nErrors:")
        for error in result.errors:
            print(f"  - {error}")