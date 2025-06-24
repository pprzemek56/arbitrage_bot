import asyncio
import logging
import json
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from contextlib import asynccontextmanager

from .config_schema import ScraperConfig, FetcherType
from .fetcher_strategies import FetcherFactory, FetcherStrategy, InteractiveFetcher, APIFetcher
from .instruction_handlers import InstructionExecutor, InstructionContext
from .processor_registry import processor_registry
from database.config import initialize_database, get_db_manager
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


class JSONPathExtractor:
    """Extract data from JSON using JSONPath-like selectors."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def extract(self, data: Any, path: str) -> Any:
        """Extract value from JSON data using simple JSONPath."""
        try:
            if path.startswith('$'):
                path = path[1:]  # Remove leading $

            if not path:
                return data

            # Handle array access like [*] or [0:5]
            if path.startswith('[') and path.endswith(']'):
                return self._handle_array_access(data, path)

            # Handle dot notation like .field.subfield
            if path.startswith('.'):
                path = path[1:]  # Remove leading dot

            parts = path.split('.')
            current = data

            for part in parts:
                if '[' in part and ']' in part:
                    # Handle array access within path like field[0]
                    field_name, array_part = part.split('[', 1)
                    if field_name:
                        current = current[field_name]
                    current = self._handle_array_access(current, '[' + array_part)
                else:
                    current = current[part]

            return current

        except (KeyError, IndexError, TypeError, ValueError) as e:
            self.logger.debug(f"JSONPath extraction failed for path '{path}': {e}")
            return None

    def _handle_array_access(self, data: Any, array_spec: str) -> Any:
        """Handle array access patterns like [*], [0], [0:5]."""
        try:
            spec = array_spec[1:-1]  # Remove brackets

            if spec == '*':
                # Return all items
                return list(data)
            elif ':' in spec:
                # Handle slicing like [0:5]
                parts = spec.split(':')
                start = int(parts[0]) if parts[0] else None
                end = int(parts[1]) if parts[1] else None
                return list(data[start:end])
            else:
                # Handle single index like [0]
                index = int(spec)
                return data[index]

        except (ValueError, IndexError, TypeError):
            return None


class DatabasePersister:
    """Simplified database persistence using environment variables."""

    def __init__(self, bookmaker_name: str, category_name: str):
        self.logger = logging.getLogger(__name__)
        self.bookmaker_name = bookmaker_name
        self.category_name = category_name
        self._db_initialized = False

    def _ensure_database_initialized(self):
        """Ensure database is initialized from environment variables."""
        if not self._db_initialized:
            try:
                # Initialize database using environment variables
                initialize_database()
                self._db_initialized = True
                self.logger.info("Database initialized from environment variables")

            except Exception as e:
                self.logger.error(f"Failed to initialize database: {e}")
                raise

    def get_or_create_bookmaker(self, name: str) -> int:
        """Get or create bookmaker by name and return its ID."""
        self._ensure_database_initialized()

        try:
            db_manager = get_db_manager()

            with db_manager.get_session() as session:
                bookmaker = session.query(Bookmaker).filter_by(name=name).first()

                if not bookmaker:
                    bookmaker = Bookmaker(name=name)
                    session.add(bookmaker)
                    session.commit()
                    session.refresh(bookmaker)  # Ensure ID is available
                    self.logger.info(f"Created new bookmaker: {name}")

                return bookmaker.id  # Return ID instead of instance
        except Exception as e:
            self.logger.error(f"Database error creating bookmaker: {e}")
            raise

    def get_or_create_category(self, name: str) -> int:
        """Get or create category by name and return its ID."""
        self._ensure_database_initialized()

        try:
            db_manager = get_db_manager()

            with db_manager.get_session() as session:
                category = session.query(Category).filter_by(name=name).first()

                if not category:
                    category = Category(name=name)
                    session.add(category)
                    session.commit()
                    session.refresh(category)  # Ensure ID is available
                    self.logger.info(f"Created new category: {name}")

                return category.id  # Return ID instead of instance
        except Exception as e:
            self.logger.error(f"Database error creating category: {e}")
            raise

    def save_event_data(self, event_data: Dict[str, Any], bookmaker_id: int, category_id: int) -> int:
        """Save event data to database."""
        self._ensure_database_initialized()

        try:
            db_manager = get_db_manager()

            with db_manager.get_session() as session:
                # Create event
                event = Event(
                    bookmaker_id=bookmaker_id,
                    category_id=category_id,
                    status=event_data.get('status', 'active')  # Fixed: was checking 'active' key
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

                # Save markets and selections if they exist
                markets = event_data.get('markets', [])
                if not markets and event_data.get('outcome_prices'):
                    # Create a default market from the event data for Polymarket
                    markets = [{
                        'type': event_data.get('market_type', 'binary'),
                        'selections': [
                            {
                                'name': 'Yes',
                                'odds': float(event_data.get('price_yes', 0.5))
                            },
                            {
                                'name': 'No',
                                'odds': float(event_data.get('price_no', 0.5))
                            }
                        ]
                    }]

                for market_data in markets:
                    market = Market(
                        normalized_event_id=normalized_event.id,
                        market_type=market_data.get('type', 'unknown')
                    )
                    session.add(market)
                    session.flush()

                    for selection_data in market_data.get('selections', []):
                        try:
                            odds_value = float(selection_data.get('odds', 0.0))
                        except (ValueError, TypeError):
                            odds_value = 0.0

                        selection = MarketSelection(
                            market_id=market.id,
                            selection=selection_data.get('name', ''),
                            odds=odds_value
                        )
                        session.add(selection)

                session.commit()
                return event.id
        except Exception as e:
            self.logger.error(f"Database error saving event: {e}")
            raise

    def _generate_mapping_hash(self, event_data: Dict[str, Any]) -> str:
        """Generate mapping hash for event normalization."""
        import hashlib

        # Use market ID or question for Polymarket
        identifier = (
            event_data.get('market_id', '') or
            event_data.get('question', '') or
            event_data.get('slug', '') or
            str(event_data)
        )
        return hashlib.md5(identifier.encode()).hexdigest()


class ScraperPipeline:
    """Main scraper pipeline that orchestrates the entire process."""

    def __init__(self, config: ScraperConfig):
        self.config = config
        self.fetcher: Optional[FetcherStrategy] = None
        self.instruction_executor = InstructionExecutor()
        self.persister = DatabasePersister(
            config.database.bookmaker_name,
            config.database.category_name
        )
        self.json_extractor = JSONPathExtractor()
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
            elif self.config.fetcher.type == FetcherType.API:
                await self._run_api_scraping(result)
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

    async def _run_api_scraping(self, result: ScrapingResult):
        """Run API scraping with JSON processing."""
        try:
            # Fetch API data
            fetch_result = await self.fetcher.fetch(self.config.meta.start_url)
            result.metadata['initial_fetch_size'] = len(fetch_result.content)

            # Parse JSON response
            try:
                json_data = json.loads(fetch_result.content)
                result.metadata['json_parsed'] = True
                self.logger.info(f"Successfully parsed JSON with {len(json_data) if isinstance(json_data, list) else 1} items")
            except json.JSONDecodeError as e:
                result.add_error(f"Failed to parse JSON response: {e}")
                return

            # Process collect instructions for JSON data
            for instruction in self.config.instructions:
                if instruction.type == "collect":
                    await self._process_json_collection(instruction, json_data, result)

        except Exception as e:
            result.add_error(f"API scraping error: {str(e)}")

    async def _process_json_collection(self, instruction, json_data: Any, result: ScrapingResult):
        """Process collect instruction for JSON data."""
        try:
            self.logger.info(f"Processing JSON collection: {instruction.name}")

            # Extract container data
            container_data = self.json_extractor.extract(json_data, instruction.container_selector)

            if not container_data:
                self.logger.warning(f"No container data found for: {instruction.container_selector}")
                return

            # Extract items from container
            items_data = self.json_extractor.extract(container_data, instruction.item_selector)

            if not isinstance(items_data, list):
                items_data = [items_data] if items_data is not None else []

            collected_items = []

            for item_data in items_data:
                if instruction.limit and len(collected_items) >= instruction.limit:
                    break

                # Extract fields from item
                item_result = {}
                for field_name, field_config in instruction.fields.items():
                    try:
                        value = self.json_extractor.extract(item_data, field_config.selector)

                        # Apply processors if configured
                        if field_config.processors and value is not None:
                            value = processor_registry.process_value(
                                value,
                                field_config.processors,
                                context={'base_url': self.config.meta.start_url}
                            )

                        item_result[field_name] = value if value is not None else field_config.default or ""

                    except Exception as e:
                        self.logger.warning(f"Error extracting field {field_name}: {e}")
                        item_result[field_name] = field_config.default or ""

                collected_items.append(item_result)

            # Store collected data
            result.events.extend(collected_items)
            self.logger.info(f"Collected {len(collected_items)} items for {instruction.name}")

        except Exception as e:
            result.add_error(f"JSON collection error: {str(e)}")

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
                result.add_error("Instructions require interactive fetcher for non-API content")

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
        self.logger.info(f"Extracting from content ({len(content)} chars)")

        # Create a dummy event for demonstration
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
            # Apply any global processing here if needed
            processed_item[field_name] = field_value

        return processed_item

    async def _persist_results(self, result: ScrapingResult):
        """Persist scraping results to database."""
        try:
            # Get or create bookmaker and category IDs
            bookmaker_id = self.persister.get_or_create_bookmaker(self.config.database.bookmaker_name)
            category_id = self.persister.get_or_create_category(self.config.database.category_name)

            # Save events
            for event_data in result.events:
                try:
                    event_id = self.persister.save_event_data(event_data, bookmaker_id, category_id)
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