#!/usr/bin/env python3
"""
Database initialization script for the arbitrage betting bot.

This script handles:
- Database creation
- Table creation
- Initial data seeding
- Database migration support
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import List

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text

# Load environment variables from .env file
from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()

# Assuming the models and config are in the same package
from database.config import (
    DatabaseConfig,
    DatabaseManager,
    initialize_database,
    get_db_manager
)
from database.models import (
    Bookmaker,
    Category,
    Event,
    NormalizedEvent,
    Market,
    MarketSelection
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_tables(db_manager: DatabaseManager) -> None:
    """Create all database tables."""
    try:
        logger.info("Creating database tables...")
        db_manager.create_tables()
        logger.info("Database tables created successfully.")
    except SQLAlchemyError as e:
        logger.error(f"Error creating tables: {e}")
        raise


def drop_tables(db_manager: DatabaseManager) -> None:
    """Drop all database tables."""
    try:
        logger.info("Dropping database tables...")
        db_manager.drop_tables()
        logger.info("Database tables dropped successfully.")
    except SQLAlchemyError as e:
        logger.error(f"Error dropping tables: {e}")
        raise


def seed_initial_data(db_manager: DatabaseManager) -> None:
    """Seed the database with initial data."""
    try:
        logger.info("Seeding initial data...")

        with db_manager.get_session() as session:
            # Check if data already exists
            if session.query(Bookmaker).first() is not None:
                logger.info("Initial data already exists. Skipping seeding.")
                return

            # Create initial bookmakers
            bookmakers = [
                Bookmaker(name="Bet365", config_file="bet365_config.json"),
                Bookmaker(name="William Hill", config_file="williamhill_config.json"),
                Bookmaker(name="Betfair", config_file="betfair_config.json"),
                Bookmaker(name="Pinnacle", config_file="pinnacle_config.json"),
                Bookmaker(name="1xBet", config_file="1xbet_config.json"),
            ]

            for bookmaker in bookmakers:
                session.add(bookmaker)

            # Create initial categories
            categories = [
                Category(name="Football"),
                Category(name="Basketball"),
                Category(name="Tennis"),
                Category(name="Hockey"),
                Category(name="Baseball"),
                Category(name="Soccer"),
                Category(name="American Football"),
                Category(name="Boxing"),
                Category(name="MMA"),
                Category(name="Cricket"),
            ]

            for category in categories:
                session.add(category)

            session.commit()
            logger.info("Initial data seeded successfully.")

    except SQLAlchemyError as e:
        logger.error(f"Error seeding initial data: {e}")
        raise


def check_database_connection(db_manager: DatabaseManager) -> bool:
    """Check if database connection is working."""
    try:
        logger.info("Checking database connection...")
        with db_manager.get_session() as session:
            session.execute(text("SELECT 1"))
        logger.info("Database connection successful.")
        return True
    except SQLAlchemyError as e:
        logger.error(f"Database connection failed: {e}")
        return False


def validate_database_structure(db_manager: DatabaseManager) -> bool:
    """Validate that all required tables exist."""
    try:
        logger.info("Validating database structure...")

        required_tables = [
            "bookmakers",
            "categories",
            "events",
            "normalized_events",
            "markets",
            "market_selections"
        ]

        with db_manager.get_session() as session:
            for table_name in required_tables:
                result = session.execute(
                    text(f"SELECT EXISTS (SELECT FROM pg_tables WHERE tablename = :table_name)"),
                    {"table_name": table_name}
                )
                exists = result.scalar()
                if not exists:
                    logger.error(f"Required table '{table_name}' does not exist.")
                    return False

        logger.info("Database structure validation successful.")
        return True

    except SQLAlchemyError as e:
        logger.error(f"Error validating database structure: {e}")
        return False


def print_database_info(db_manager: DatabaseManager) -> None:
    """Print database information and statistics."""
    try:
        logger.info("Database Information:")
        # Hide password in logs for security
        safe_url = db_manager.config.database_url
        if '@' in safe_url:
            # Replace password with asterisks
            protocol, rest = safe_url.split('://', 1)
            if '@' in rest:
                credentials, host_part = rest.split('@', 1)
                if ':' in credentials:
                    user, _ = credentials.split(':', 1)
                    safe_url = f"{protocol}://{user}:***@{host_part}"

        logger.info(f"Database URL: {safe_url}")

        with db_manager.get_session() as session:
            # Count records in each table
            bookmaker_count = session.query(Bookmaker).count()
            category_count = session.query(Category).count()
            event_count = session.query(Event).count()
            normalized_event_count = session.query(NormalizedEvent).count()
            market_count = session.query(Market).count()
            selection_count = session.query(MarketSelection).count()

            logger.info("Table Statistics:")
            logger.info(f"  Bookmakers: {bookmaker_count}")
            logger.info(f"  Categories: {category_count}")
            logger.info(f"  Events: {event_count}")
            logger.info(f"  Normalized Events: {normalized_event_count}")
            logger.info(f"  Markets: {market_count}")
            logger.info(f"  Market Selections: {selection_count}")

    except SQLAlchemyError as e:
        logger.error(f"Error getting database info: {e}")


def print_config_debug_info(config: DatabaseConfig) -> None:
    """Print configuration information for debugging."""
    logger.info("Configuration Debug Information:")
    logger.info(f"  Host: {config.host}")
    logger.info(f"  Port: {config.port}")
    logger.info(f"  Database: {config.database}")
    logger.info(f"  Username: {config.username}")
    logger.info(f"  Password: {'***' if config.password else 'NOT SET'}")
    logger.info(f"  Pool Size: {config.pool_size}")
    logger.info(f"  Echo: {config.echo}")


def main():
    """Main function to handle command line arguments and execute actions."""
    parser = argparse.ArgumentParser(
        description="Database initialization and management script"
    )

    parser.add_argument(
        "action",
        choices=["init", "create", "drop", "recreate", "seed", "check", "validate", "info", "debug"],
        help="Action to perform"
    )

    parser.add_argument(
        "--db-host",
        default=None,
        help="Database host (overrides environment variable)"
    )

    parser.add_argument(
        "--db-port",
        type=int,
        default=None,
        help="Database port (overrides environment variable)"
    )

    parser.add_argument(
        "--db-name",
        default=None,
        help="Database name (overrides environment variable)"
    )

    parser.add_argument(
        "--db-user",
        default=None,
        help="Database user (overrides environment variable)"
    )

    parser.add_argument(
        "--db-password",
        default=None,
        help="Database password (overrides environment variable)"
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Force action without confirmation"
    )

    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to .env file (default: .env)"
    )

    args = parser.parse_args()

    try:
        # Load .env file if specified and exists
        env_file_path = Path(args.env_file)
        if env_file_path.exists():
            logger.info(f"Loading environment variables from: {env_file_path}")
            load_dotenv(env_file_path)
        else:
            logger.warning(f"Environment file not found: {env_file_path}")

        # Create database configuration
        config = DatabaseConfig.from_env()

        # Override with command line arguments if provided
        if args.db_host:
            config.host = args.db_host
        if args.db_port:
            config.port = args.db_port
        if args.db_name:
            config.database = args.db_name
        if args.db_user:
            config.username = args.db_user
        if args.db_password:
            config.password = args.db_password

        # Initialize database manager
        db_manager = initialize_database(config)

        # Execute requested action
        if args.action == "init":
            logger.info("Initializing database...")
            if not check_database_connection(db_manager):
                sys.exit(1)
            create_tables(db_manager)
            seed_initial_data(db_manager)
            logger.info("Database initialization completed.")

        elif args.action == "create":
            create_tables(db_manager)

        elif args.action == "drop":
            if not args.force:
                response = input("Are you sure you want to drop all tables? [y/N]: ")
                if response.lower() != 'y':
                    logger.info("Operation cancelled.")
                    sys.exit(0)
            drop_tables(db_manager)

        elif args.action == "recreate":
            if not args.force:
                response = input("Are you sure you want to recreate all tables? [y/N]: ")
                if response.lower() != 'y':
                    logger.info("Operation cancelled.")
                    sys.exit(0)
            drop_tables(db_manager)
            create_tables(db_manager)

        elif args.action == "seed":
            seed_initial_data(db_manager)

        elif args.action == "check":
            if check_database_connection(db_manager):
                logger.info("Database check passed.")
            else:
                logger.error("Database check failed.")
                sys.exit(1)

        elif args.action == "validate":
            if validate_database_structure(db_manager):
                logger.info("Database validation passed.")
            else:
                logger.error("Database validation failed.")
                sys.exit(1)

        elif args.action == "info":
            print_database_info(db_manager)

        elif args.action == "debug":
            print_config_debug_info(config)

    except Exception as e:
        logger.error(f"Error executing action '{args.action}': {e}")

    finally:
        # Clean up database connections
        try:
            db_manager = get_db_manager()
            db_manager.close()
        except:
            pass


if __name__ == "__main__":
    main()