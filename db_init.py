#!/usr/bin/env python3
"""
Fixed database initialization script with proper SQLAlchemy 2.0 syntax.
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

from database.config import DatabaseManager, initialize_database
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
                Bookmaker(name="Polymarket", config_file="polymarket_config.json"),
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
                Category(name="Prediction Markets"),
                Category(name="Politics"),
                Category(name="Economics"),
                Category(name="Entertainment"),
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
                    text("SELECT EXISTS (SELECT FROM pg_tables WHERE tablename = :table_name)"),
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
        logger.info(f"Database config: {db_manager.config}")

        with db_manager.get_session() as session:
            # Get current database name
            result = session.execute(text("SELECT current_database()"))
            current_db = result.scalar()
            logger.info(f"Connected to database: {current_db}")

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


def main():
    """Main function to handle command line arguments and execute actions."""
    parser = argparse.ArgumentParser(
        description="Database initialization and management script"
    )

    parser.add_argument(
        "action",
        choices=["init", "create", "drop", "recreate", "seed", "check", "validate", "info"],
        help="Action to perform"
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Force action without confirmation"
    )

    args = parser.parse_args()

    try:
        # Initialize database manager using environment variables
        db_manager = initialize_database()
        logger.info("Database manager initialized from environment variables")

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

    except Exception as e:
        logger.error(f"Error executing action '{args.action}': {e}")

    finally:
        try:
            db_manager.close()
        except:
            pass


if __name__ == "__main__":
    main()