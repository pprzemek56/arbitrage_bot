# Arbitrage Bot Database Structure

This document describes the database structure and setup for the arbitrage betting bot project.

## Tech Stack

- **Python 3.x** - Core runtime
- **PostgreSQL 16** - Database
- **SQLAlchemy** - ORM and persistence layer
- **Pydantic v2** - Data models and validation
- **Celery 5** - Task and job orchestration

## Database Schema

The database consists of 6 main tables:

### Core Tables

1. **bookmakers** - Stores bookmaker information
   - `id` (Primary Key)
   - `name` (Unique bookmaker name)
   - `config_file` (Configuration file path)

2. **categories** - Event categories (Football, Tennis, etc.)
   - `id` (Primary Key)
   - `name` (Unique category name)

3. **events** - Events from different bookmakers
   - `id` (Primary Key)
   - `bookmaker_id` (Foreign Key to bookmakers)
   - `category_id` (Foreign Key to categories)
   - `timestamp` (Event timestamp)
   - `status` (Event status: active, inactive, etc.)

4. **normalized_events** - Normalized events across bookmakers
   - `id` (Primary Key)
   - `event_id` (Foreign Key to events)
   - `mapping_hash` (Hash for event mapping)

5. **markets** - Markets for normalized events
   - `id` (Primary Key)
   - `normalized_event_id` (Foreign Key to normalized_events)
   - `market_type` (Type of market: Match Winner, Over/Under, etc.)

6. **market_selections** - Selections and odds for markets
   - `id` (Primary Key)
   - `market_id` (Foreign Key to markets)
   - `selection` (Selection name)
   - `odds` (Decimal odds value)

## Setup Instructions

### 1. Environment Setup

Create a `.env` file in your project root:

```env
# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=arbitrage_bot
DB_USER=postgres
DB_PASSWORD=your_password

# Database Pool Configuration
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=3600
DB_ECHO=false

# Redis Configuration (for Celery)
REDIS_URL=redis://localhost:6379/0
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Database Setup

#### Initialize Database (recommended for first setup)
```bash
python db_init.py init
```

This will:
- Create all tables
- Seed initial data (bookmakers and categories)
- Validate the setup

#### Individual Operations

```bash
# Create tables only
python db_init.py create

# Drop all tables (use with caution!)
python db_init.py drop --force

# Recreate all tables
python db_init.py recreate --force

# Seed initial data
python db_init.py seed

# Check database connection
python db_init.py check

# Validate database structure
python db_init.py validate

# Show database information
python db_init.py info
```

### 4. Database Migrations

For schema changes, use Alembic:

```bash
# Initialize Alembic (first time only)
alembic init alembic

# Generate migration
alembic revision --autogenerate -m "Description of changes"

# Apply migrations
alembic upgrade head
```

## Usage Examples

### Basic Database Operations

```python
from database.config import initialize_database, get_db_session
from database.models import Bookmaker, Category, Event
from database.schemas import BookmakerCreate, EventCreate

# Initialize database
initialize_database()

# Create a new bookmaker
with get_db_session() as session:
    bookmaker = Bookmaker(name="New Bookmaker", config_file="config.json")
    session.add(bookmaker)
    session.commit()

# Query events
with get_db_session() as session:
    active_events = session.query(Event).filter(Event.status == "active").all()
    for event in active_events:
        print(f"Event {event.id}: {event.bookmaker.name} - {event.category.name}")
```

### Using Pydantic Schemas

```python
from database.schemas import BookmakerCreate, BookmakerResponse

# Validate input data
bookmaker_data = BookmakerCreate(
    name="Betfair",
    config_file="betfair_config.json"
)

# Convert SQLAlchemy model to Pydantic
with get_db_session() as session:
    bookmaker = session.query(Bookmaker).first()
    bookmaker_response = BookmakerResponse.model_validate(bookmaker)
    print(bookmaker_response.model_dump_json())
```

### Finding Arbitrage Opportunities

```python
from database.models import Market, MarketSelection
from sqlalchemy import func

with get_db_session() as session:
    # Find markets with multiple selections
    markets_with_selections = (
        session.query(Market)
        .join(MarketSelection)
        .group_by(Market.id)
        .having(func.count(MarketSelection.id) > 1)
        .all()
    )
    
    for market in markets_with_selections:
        selections = market.market_selections
        total_implied_prob = sum(1/float(sel.odds) for sel in selections)
        
        if total_implied_prob < 1.0:  # Arbitrage opportunity
            profit_margin = 1 - total_implied_prob
            print(f"Arbitrage opportunity: {profit_margin:.2%} profit")
```

## Project Structure

```
arbitrage-betting-scraper/
│
├── 📁 database/                          # Database layer (existing)
│   ├── __init__.py
│   ├── config.py                         # Database configuration & manager
│   ├── models.py                         # SQLAlchemy models for betting data
│   └── schemas.py                        # Pydantic schemas for validation
│
├── 📁 scraper/                           # New scraper package
│   ├── __init__.py
│   ├── config_schema.py                  # Pydantic config models & validation
│   ├── fetcher_strategies.py             # Strategy pattern for fetchers
│   ├── instruction_handlers.py           # Command pattern for instructions
│   ├── processor_registry.py             # Pluggable field processors
│   ├── scraper_pipeline.py               # Main orchestration pipeline
│   ├── cli.py                           # Rich CLI interface
│   └── testing_utilities.py             # Testing framework & utilities
│
├── 📁 configs/                          # Configuration files
│   ├── static_example.yml               # Static HTML scraper config
│   ├── interactive_example.yml          # Browser automation config
│   ├── api_example.yml                  # API scraper config
│   └── bet365_example.yml               # Real-world example config
│
├── 📁 tests/                            # Test suite
│   ├── __init__.py
│   ├── conftest.py                      # Pytest configuration
│   ├── test_config_schema.py            # Config validation tests
│   ├── test_fetcher_strategies.py       # Fetcher strategy tests
│   ├── test_instruction_handlers.py     # Instruction handler tests
│   ├── test_processor_registry.py       # Processor tests
│   ├── test_scraper_pipeline.py         # Integration tests
│   └── test_cli.py                      # CLI tests
│
├── 📁 logs/                             # Log files
│   ├── scraper.log                      # Main application log
│   └── error.log                        # Error-specific log
│
├── 📁 results/                          # Scraping results
│   ├── bet365_results.json              # JSON output files
│   └── arbitrage_opportunities.json     # Detected opportunities
│
├── 📁 docs/                             # Documentation
│   ├── README.md                        # Main documentation
│   ├── ARCHITECTURE.md                  # Architecture overview
│   ├── API.md                           # API documentation
│   └── DEPLOYMENT.md                    # Deployment guide
│
├── 📄 requirements.txt                   # Python dependencies
├── 📄 .env.example                      # Environment variables template
├── 📄 .gitignore                        # Git ignore rules
├── 📄 db_init.py                        # Database initialization script
├── 📄 comprehensive_example.py          # Complete example demonstration
├── 📄 monitoring_example.py             # Continuous monitoring script
└── 📄 setup.py                          # Package setup configuration
```

## Best Practices

1. **Always use sessions within context managers** to ensure proper cleanup
2. **Use Pydantic schemas** for data validation and API serialization
3. **Index frequently queried columns** for better performance
4. **Use database constraints** to maintain data integrity
5. **Regular database backups** before major operations
6. **Monitor connection pool** usage in production

## Performance Considerations

- The database includes strategic indexes on frequently queried columns
- Connection pooling is configured for optimal performance
- Use bulk operations for large data imports
- Consider partitioning for very large tables (events, market_selections)
- Monitor query performance and add indexes as needed

## Troubleshooting

### Common Issues

1. **Connection refused**: Check PostgreSQL service and credentials
2. **Table already exists**: Use `recreate` action to reset tables
3. **Migration conflicts**: Reset Alembic state if needed
4. **Pool timeout**: Increase pool size or check for connection leaks

### Logging

Enable SQL logging for debugging:
```python
config = DatabaseConfig.from_env()
config.echo = True
```

## Core Components

### Configuration System
from scraper.config_schema import (
    ScraperConfig,
    ConfigLoader,
    FetcherType,
    InstructionType
)

### Fetcher Strategies  
from scraper.fetcher_strategies import (
    FetcherFactory,
    StaticFetcher,
    BrowserFetcher,
    APIFetcher,
    InteractiveFetcher
)

### Instruction Handlers
from scraper.instruction_handlers import (
    InstructionExecutor,
    InstructionContext,
    ClickHandler,
    LoopHandler,
    CollectHandler
)

### Field Processors
from scraper.processor_registry import (
    processor_registry,
    register_processor,
    BaseProcessor,
    process_field
)

### Main Pipeline
from scraper.scraper_pipeline import (
    ScraperPipeline,
    ScraperRunner,
    ScrapingResult,
    run_scraper_sync
)

### Testing Utilities
from scraper.testing_utilities import (
    ScraperTestCase,
    MockFetcher,
    MockPage,
    assert_config_valid
)

## Database Integration

### Models (existing)
from database.models import (
    Bookmaker,
    Category,
    Event,
    NormalizedEvent,
    Market,
    MarketSelection
)

### Configuration
from database.config import (
    DatabaseConfig,
    DatabaseManager,
    initialize_database,
    get_db_session
)

## Usage Examples

### 1. Simple Scraper Run
```python
from scraper.config_schema import ConfigLoader
from scraper.scraper_pipeline import ScraperRunner

# Load config and run
config = ConfigLoader.load_from_yaml('configs/bet365.yml')
runner = ScraperRunner()
result = runner.run_scraper_sync(config)

print(f"Scraped {len(result.events)} events")
```

### 2. Custom Processor
```python
from scraper.processor_registry import BaseProcessor, register_processor

class MyProcessor(BaseProcessor):
    def __init__(self):
        super().__init__("my_processor")
    
    def process(self, value, **kwargs):
        return value.upper()

register_processor(MyProcessor())
```

### 3. Programmatic Configuration
```python
from scraper.config_schema import ScraperConfig, MetaConfig, FetcherConfig

config = ScraperConfig(
    meta=MetaConfig(
        name="programmatic_scraper",
        start_url="https://example.com"
    ),
    fetcher=FetcherConfig(type="browser"),
    database=DatabaseConfig(
        url="postgresql://localhost/db",
        bookmaker_name="Example",
        category_name="Sports"
    ),
    instructions=[
        {
            "type": "collect",
            "name": "odds",
            "container_selector": ".odds-table",
            "item_selector": ".odds-row",
            "fields": {
                "odds": {"selector": ".odds", "attribute": "text"}
            }
        }
    ]
)
```

### 4. CLI Usage
```bash
# Validate configuration
python -m scraper.cli validate configs/my_config.yml

# Run scraper
python -m scraper.cli run configs/my_config.yml --output results.json

# Create new config template  
python -m scraper.cli create --name "MyBookmaker" --url "https://example.com" --output new_config.yml

# Batch processing
python -m scraper.cli batch --config-dir configs/ --parallel 3
```

### 5. Testing
```python
from scraper.testing_utilities import ScraperTestCase, run_mock_scraper

class TestMyScraper(ScraperTestCase):
    async def test_scraper(self):
        config = self.create_test_config()
        html = self.create_test_html([{"name": "Test Match"}])
        
        result = await run_mock_scraper(config, html)
        assert len(result.events) > 0
```

## Key Architecture Features

### 🎯 Strategy Pattern (Fetchers)
- **StaticFetcher**: Simple HTTP requests for static content
- **BrowserFetcher**: Playwright for JavaScript-heavy sites  
- **APIFetcher**: REST API calls with authentication
- **InteractiveFetcher**: Complex user interactions & workflows

### 🎯 Command Pattern (Instructions)
- **ClickHandler**: Click elements and wait for responses
- **LoopHandler**: Pagination, dropdown iteration, conditional loops
- **CollectHandler**: Extract structured data from DOM
- **ConditionalHandler**: If/else logic for dynamic pages

### 🎯 Pipeline Architecture
```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────────┐
│   CONFIG    │───▶│    FETCH     │───▶│   EXTRACT   │───▶│   PERSIST    │
│ Validation  │    │ (Strategies) │    │ (Handlers)  │    │ (Database)   │
└─────────────┘    └──────────────┘    └─────────────┘    └──────────────┘
                           │                    │
                           ▼                    ▼
                   ┌──────────────┐    ┌─────────────┐
                   │  PROCESSORS  │    │   RESULTS   │
                   │ (Transform)  │    │ (Analysis)  │
                   └──────────────┘    └─────────────┘
```

### 🎯 Extensibility Points
- **Custom Processors**: Add new field transformation logic
- **Custom Handlers**: Implement new instruction types
- **Custom Fetchers**: Support new protocols or authentication
- **Custom Validators**: Add config validation rules

### 🎯 Production Features
- **Error Handling**: Comprehensive error catching and reporting
- **Logging**: Structured logging with configurable levels  
- **Monitoring**: Built-in performance metrics and health checks
- **Testing**: Full test suite with mocks and fixtures
- **CLI**: Rich command-line interface for operations
- **Database**: Full integration with SQLAlchemy models

## Configuration File Structure

```yaml
meta:                              # Scraper metadata
  name: "scraper_name"             # Unique identifier
  description: "Description"       # Human-readable description  
  start_url: "https://..."         # Starting URL
  allowed_domains: [...]           # Allowed domains for navigation

fetcher:                           # Fetching strategy
  type: "static|browser|api|interactive"
  timeout_ms: 30000               # Request timeout
  headless: true                  # Browser mode (browser fetchers)
  headers: {...}                  # HTTP headers
  auth: {...}                     # Authentication config

database:                          # Database configuration
  url: "postgresql://..."          # Connection string
  bookmaker_name: "Bookmaker"     # Bookmaker identification
  category_name: "Sport"          # Event category

instructions:                      # Scraping instructions
  - type: "click|wait|loop|if|collect|navigate|input|select|scroll"
    # ... instruction-specific parameters

collections:                       # Reusable data collection definitions  
  collection_name:
    container_selector: "..."
    item_selector: "..." 
    fields: {...}
```

This architecture provides a robust, extensible foundation for arbitrage betting scraping with clean separation of concerns, comprehensive testing, and production-ready features.
```