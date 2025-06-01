"""
SQLAlchemy database models for arbitrage betting bot.
Based on the database structure diagram provided.
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Index
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, Mapped

Base = declarative_base()


class Bookmaker(Base):
    """
    Table to store bookmaker information and configuration.
    """
    __tablename__ = "bookmakers"

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = Column(String(100), nullable=False, unique=True)
    config_file: Mapped[Optional[str]] = Column(String(255), nullable=True)

    # Relationships
    events: Mapped[List["Event"]] = relationship("Event", back_populates="bookmaker")

    def __repr__(self):
        return f"<Bookmaker(id={self.id}, name='{self.name}')>"


class Category(Base):
    """
    Table to store event categories (e.g., Football, Tennis, Basketball).
    """
    __tablename__ = "categories"

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = Column(String(100), nullable=False, unique=True)

    # Relationships
    events: Mapped[List["Event"]] = relationship("Event", back_populates="category")

    def __repr__(self):
        return f"<Category(id={self.id}, name='{self.name}')>"


class Event(Base):
    """
    Table to store events from different bookmakers.
    """
    __tablename__ = "events"

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    bookmaker_id: Mapped[int] = Column(Integer, ForeignKey("bookmakers.id"), nullable=False)
    category_id: Mapped[int] = Column(Integer, ForeignKey("categories.id"), nullable=False)
    timestamp: Mapped[datetime] = Column(DateTime, nullable=False, default=datetime.utcnow)
    status: Mapped[str] = Column(String(50), nullable=False, default="active")

    # Relationships
    bookmaker: Mapped["Bookmaker"] = relationship("Bookmaker", back_populates="events")
    category: Mapped["Category"] = relationship("Category", back_populates="events")
    normalized_events: Mapped[List["NormalizedEvent"]] = relationship(
        "NormalizedEvent", back_populates="event"
    )

    # Indexes for better performance
    __table_args__ = (
        Index("idx_events_bookmaker_category", "bookmaker_id", "category_id"),
        Index("idx_events_timestamp", "timestamp"),
        Index("idx_events_status", "status"),
    )

    def __repr__(self):
        return f"<Event(id={self.id}, bookmaker_id={self.bookmaker_id}, status='{self.status}')>"


class NormalizedEvent(Base):
    """
    Table to store normalized events that map equivalent events across bookmakers.
    """
    __tablename__ = "normalized_events"

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = Column(Integer, ForeignKey("events.id"), nullable=False)
    mapping_hash: Mapped[str] = Column(String(64), nullable=False)

    # Relationships
    event: Mapped["Event"] = relationship("Event", back_populates="normalized_events")
    markets: Mapped[List["Market"]] = relationship("Market", back_populates="normalized_event")

    # Constraints
    __table_args__ = (
        UniqueConstraint("event_id", "mapping_hash", name="uq_normalized_event_mapping"),
        Index("idx_normalized_events_mapping_hash", "mapping_hash"),
    )

    def __repr__(self):
        return f"<NormalizedEvent(id={self.id}, event_id={self.event_id}, mapping_hash='{self.mapping_hash}')>"


class Market(Base):
    """
    Table to store markets for normalized events (e.g., Match Winner, Over/Under).
    """
    __tablename__ = "markets"

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    normalized_event_id: Mapped[int] = Column(
        Integer, ForeignKey("normalized_events.id"), nullable=False
    )
    market_type: Mapped[str] = Column(String(100), nullable=False)

    # Relationships
    normalized_event: Mapped["NormalizedEvent"] = relationship(
        "NormalizedEvent", back_populates="markets"
    )
    market_selections: Mapped[List["MarketSelection"]] = relationship(
        "MarketSelection", back_populates="market"
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "normalized_event_id", "market_type", name="uq_market_normalized_event_type"
        ),
        Index("idx_markets_normalized_event", "normalized_event_id"),
        Index("idx_markets_type", "market_type"),
    )

    def __repr__(self):
        return f"<Market(id={self.id}, normalized_event_id={self.normalized_event_id}, market_type='{self.market_type}')>"


class MarketSelection(Base):
    """
    Table to store selections and odds for each market.
    """
    __tablename__ = "market_selections"

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    market_id: Mapped[int] = Column(Integer, ForeignKey("markets.id"), nullable=False)
    selection: Mapped[str] = Column(String(200), nullable=False)
    odds: Mapped[Decimal] = Column(Numeric(10, 4), nullable=False)

    # Relationships
    market: Mapped["Market"] = relationship("Market", back_populates="market_selections")

    # Constraints
    __table_args__ = (
        UniqueConstraint("market_id", "selection", name="uq_market_selection"),
        Index("idx_market_selections_market", "market_id"),
        Index("idx_market_selections_odds", "odds"),
    )

    def __repr__(self):
        return f"<MarketSelection(id={self.id}, market_id={self.market_id}, selection='{self.selection}', odds={self.odds})>"