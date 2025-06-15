import os
import logging
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import SQLAlchemyError

from .models import Base

logger = logging.getLogger(__name__)


class DatabaseConfig:
    """Database configuration class."""

    def __init__(self):
        # Always load from environment variables
        self.host = os.getenv("DB_HOST", "localhost")
        self.port = int(os.getenv("DB_PORT", "5432"))
        self.database = os.getenv("DB_NAME", "arbitrage_bot_db")
        self.username = os.getenv("DB_USER", "postgres")
        self.password = os.getenv("DB_PASSWORD", "")

        # Pool configuration
        self.pool_size = int(os.getenv("DB_POOL_SIZE", "10"))
        self.max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "20"))
        self.pool_timeout = int(os.getenv("DB_POOL_TIMEOUT", "30"))
        self.pool_recycle = int(os.getenv("DB_POOL_RECYCLE", "3600"))
        self.echo = os.getenv("DB_ECHO", "false").lower() == "true"

    @property
    def database_url(self) -> str:
        """Generate database URL for SQLAlchemy."""
        if self.password:
            return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"
        else:
            return f"postgresql://{self.username}@{self.host}:{self.port}/{self.database}"

    def test_connection(self) -> bool:
        """Test database connection."""
        try:
            from sqlalchemy import text
            engine = create_engine(self.database_url, echo=False)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            engine.dispose()
            return True
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False

    def validate_environment(self) -> tuple[bool, list[str]]:
        """Validate that all required environment variables are set."""
        errors = []

        if not self.host:
            errors.append("DB_HOST not set")
        if not self.database:
            errors.append("DB_NAME not set")
        if not self.username:
            errors.append("DB_USER not set")
        if not self.password:
            errors.append("DB_PASSWORD not set")

        return len(errors) == 0, errors

    def __str__(self):
        """String representation with masked password."""
        if self.password:
            masked_url = f"postgresql://{self.username}:***@{self.host}:{self.port}/{self.database}"
        else:
            masked_url = f"postgresql://{self.username}@{self.host}:{self.port}/{self.database}"

        return f"DatabaseConfig({masked_url})"


class DatabaseManager:
    """Database manager with automatic environment-based configuration."""

    def __init__(self):
        self.config = DatabaseConfig()
        self._engine: Optional[Engine] = None
        self._session_factory: Optional[sessionmaker] = None
        self.logger = logging.getLogger(__name__)

    def validate_config(self) -> None:
        """Validate database configuration before use."""
        is_valid, errors = self.config.validate_environment()

        if not is_valid:
            error_msg = f"Database configuration invalid: {', '.join(errors)}"
            self.logger.error(error_msg)
            raise ValueError(error_msg)

    @property
    def engine(self) -> Engine:
        """Get or create the database engine."""
        if self._engine is None:
            # Validate configuration first
            self.validate_config()

            try:
                self._engine = create_engine(
                    self.config.database_url,
                    poolclass=QueuePool,
                    pool_size=self.config.pool_size,
                    max_overflow=self.config.max_overflow,
                    pool_timeout=self.config.pool_timeout,
                    pool_recycle=self.config.pool_recycle,
                    echo=self.config.echo,
                    future=True,
                    connect_args={
                        "sslmode": "prefer",
                        "application_name": "arbitrage_bot"
                    }
                )

                # Test the connection
                from sqlalchemy import text
                with self._engine.connect() as conn:
                    conn.execute(text("SELECT 1"))

                self.logger.info(f"Database engine created successfully: {self.config}")

            except SQLAlchemyError as e:
                self.logger.error(f"Failed to create database engine: {e}")
                self.logger.error(f"Database config: {self.config}")
                raise
            except Exception as e:
                self.logger.error(f"Unexpected error creating database engine: {e}")
                raise

        return self._engine

    @property
    def session_factory(self) -> sessionmaker:
        """Get or create the session factory."""
        if self._session_factory is None:
            self._session_factory = sessionmaker(
                bind=self.engine,
                autocommit=False,
                autoflush=False,
                future=True
            )
        return self._session_factory

    def create_tables(self) -> None:
        """Create all database tables."""
        try:
            Base.metadata.create_all(bind=self.engine)
            self.logger.info("Database tables created successfully")
        except SQLAlchemyError as e:
            self.logger.error(f"Failed to create tables: {e}")
            raise

    def drop_tables(self) -> None:
        """Drop all database tables."""
        try:
            Base.metadata.drop_all(bind=self.engine)
            self.logger.info("Database tables dropped successfully")
        except SQLAlchemyError as e:
            self.logger.error(f"Failed to drop tables: {e}")
            raise

    def recreate_tables(self) -> None:
        """Drop and recreate all database tables."""
        self.drop_tables()
        self.create_tables()

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """Get a database session with automatic cleanup."""
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            self.logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()

    def get_session_sync(self) -> Session:
        """Get a database session (manual management required)."""
        return self.session_factory()

    def close(self) -> None:
        """Close the database engine."""
        if self._engine:
            self._engine.dispose()
            self._engine = None
            self._session_factory = None
            self.logger.info("Database engine closed")


# Global database manager instance
_db_manager: Optional[DatabaseManager] = None


def initialize_database() -> DatabaseManager:
    """Initialize the database manager using environment variables."""
    global _db_manager

    _db_manager = DatabaseManager()

    # Validate configuration immediately
    _db_manager.validate_config()

    # Test connection
    if not _db_manager.config.test_connection():
        logger.error("Database connection test failed. Please check your environment variables.")
        logger.error(f"Current config: {_db_manager.config}")
        raise ConnectionError("Could not connect to database")

    logger.info(f"Database initialized successfully: {_db_manager.config}")
    return _db_manager


def get_db_manager() -> DatabaseManager:
    """Get the global database manager instance."""
    if _db_manager is None:
        raise RuntimeError("Database not initialized. Call initialize_database() first.")
    return _db_manager


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Get a database session using the global database manager."""
    db_manager = get_db_manager()
    with db_manager.get_session() as session:
        yield session


def create_all_tables() -> None:
    """Create all database tables using the global database manager."""
    db_manager = get_db_manager()
    db_manager.create_tables()


def drop_all_tables() -> None:
    """Drop all database tables using the global database manager."""
    db_manager = get_db_manager()
    db_manager.drop_tables()


def recreate_all_tables() -> None:
    """Recreate all database tables using the global database manager."""
    db_manager = get_db_manager()
    db_manager.recreate_tables()