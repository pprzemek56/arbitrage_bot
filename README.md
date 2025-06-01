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
arbitrage_bot/
├── database/
│   ├── __init__.py
│   ├── models.py          # SQLAlchemy models
│   ├── schemas.py         # Pydantic schemas
│   ├── config.py          # Database configuration
│   └── migrations/        # Alembic migrations
├── db_init.py            # Database initialization script
├── requirements.txt      # Python dependencies
├── .env                  # Environment variables
├── .gitignore           # Git ignore rules
└── README.md            # This file
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

For any issues, check the logs and validate your environment configuration.