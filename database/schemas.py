"""
Pydantic schemas for data validation and serialization.
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, validator


# Base schemas
class BaseSchema(BaseModel):
    """Base schema with common configuration."""
    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
        str_strip_whitespace=True
    )


# Bookmaker schemas
class BookmakerBase(BaseSchema):
    """Base bookmaker schema."""
    name: str = Field(..., min_length=1, max_length=100)
    config_file: Optional[str] = Field(None, max_length=255)


class BookmakerCreate(BookmakerBase):
    """Schema for creating a bookmaker."""
    pass


class BookmakerUpdate(BaseSchema):
    """Schema for updating a bookmaker."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    config_file: Optional[str] = Field(None, max_length=255)


class BookmakerResponse(BookmakerBase):
    """Schema for bookmaker response."""
    id: int


# Category schemas
class CategoryBase(BaseSchema):
    """Base category schema."""
    name: str = Field(..., min_length=1, max_length=100)


class CategoryCreate(CategoryBase):
    """Schema for creating a category."""
    pass


class CategoryUpdate(BaseSchema):
    """Schema for updating a category."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)


class CategoryResponse(CategoryBase):
    """Schema for category response."""
    id: int


# Event schemas
class EventBase(BaseSchema):
    """Base event schema."""
    bookmaker_id: int = Field(..., gt=0)
    category_id: int = Field(..., gt=0)
    status: str = Field("active", max_length=50)

    @validator('status')
    def validate_status(cls, v):
        """Validate event status."""
        allowed_statuses = ['active', 'inactive', 'suspended', 'finished', 'cancelled']
        if v not in allowed_statuses:
            raise ValueError(f'Status must be one of: {", ".join(allowed_statuses)}')
        return v


class EventCreate(EventBase):
    """Schema for creating an event."""
    timestamp: Optional[datetime] = None


class EventUpdate(BaseSchema):
    """Schema for updating an event."""
    bookmaker_id: Optional[int] = Field(None, gt=0)
    category_id: Optional[int] = Field(None, gt=0)
    status: Optional[str] = Field(None, max_length=50)

    @validator('status')
    def validate_status(cls, v):
        """Validate event status."""
        if v is not None:
            allowed_statuses = ['active', 'inactive', 'suspended', 'finished', 'cancelled']
            if v not in allowed_statuses:
                raise ValueError(f'Status must be one of: {", ".join(allowed_statuses)}')
        return v


class EventResponse(EventBase):
    """Schema for event response."""
    id: int
    timestamp: datetime
    bookmaker: Optional[BookmakerResponse] = None
    category: Optional[CategoryResponse] = None


# Normalized Event schemas
class NormalizedEventBase(BaseSchema):
    """Base normalized event schema."""
    event_id: int = Field(..., gt=0)
    mapping_hash: str = Field(..., min_length=1, max_length=64)


class NormalizedEventCreate(NormalizedEventBase):
    """Schema for creating a normalized event."""
    pass


class NormalizedEventUpdate(BaseSchema):
    """Schema for updating a normalized event."""
    event_id: Optional[int] = Field(None, gt=0)
    mapping_hash: Optional[str] = Field(None, min_length=1, max_length=64)


class NormalizedEventResponse(NormalizedEventBase):
    """Schema for normalized event response."""
    id: int
    event: Optional[EventResponse] = None


# Market schemas
class MarketBase(BaseSchema):
    """Base market schema."""
    normalized_event_id: int = Field(..., gt=0)
    market_type: str = Field(..., min_length=1, max_length=100)


class MarketCreate(MarketBase):
    """Schema for creating a market."""
    pass


class MarketUpdate(BaseSchema):
    """Schema for updating a market."""
    normalized_event_id: Optional[int] = Field(None, gt=0)
    market_type: Optional[str] = Field(None, min_length=1, max_length=100)


class MarketResponse(MarketBase):
    """Schema for market response."""
    id: int
    normalized_event: Optional[NormalizedEventResponse] = None


# Market Selection schemas
class MarketSelectionBase(BaseSchema):
    """Base market selection schema."""
    market_id: int = Field(..., gt=0)
    selection: str = Field(..., min_length=1, max_length=200)
    odds: Decimal = Field(..., gt=0, decimal_places=4)

    @validator('odds')
    def validate_odds(cls, v):
        """Validate odds are positive and reasonable."""
        if v <= 0:
            raise ValueError('Odds must be positive')
        if v > 1000:
            raise ValueError('Odds seem unreasonably high')
        return v


class MarketSelectionCreate(MarketSelectionBase):
    """Schema for creating a market selection."""
    pass


class MarketSelectionUpdate(BaseSchema):
    """Schema for updating a market selection."""
    market_id: Optional[int] = Field(None, gt=0)
    selection: Optional[str] = Field(None, min_length=1, max_length=200)
    odds: Optional[Decimal] = Field(None, gt=0, decimal_places=4)

    @validator('odds')
    def validate_odds(cls, v):
        """Validate odds are positive and reasonable."""
        if v is not None:
            if v <= 0:
                raise ValueError('Odds must be positive')
            if v > 1000:
                raise ValueError('Odds seem unreasonably high')
        return v


class MarketSelectionResponse(MarketSelectionBase):
    """Schema for market selection response."""
    id: int
    market: Optional[MarketResponse] = None


# Extended response schemas with relationships
class MarketResponseWithSelections(MarketResponse):
    """Market response with selections."""
    market_selections: List[MarketSelectionResponse] = []


class NormalizedEventResponseWithMarkets(NormalizedEventResponse):
    """Normalized event response with markets."""
    markets: List[MarketResponseWithSelections] = []


class EventResponseWithNormalizedEvents(EventResponse):
    """Event response with normalized events."""
    normalized_events: List[NormalizedEventResponseWithMarkets] = []


class BookmakerResponseWithEvents(BookmakerResponse):
    """Bookmaker response with events."""
    events: List[EventResponse] = []


class CategoryResponseWithEvents(CategoryResponse):
    """Category response with events."""
    events: List[EventResponse] = []


# Arbitrage opportunity schema
class ArbitrageOpportunity(BaseSchema):
    """Schema for arbitrage opportunities."""
    normalized_event_id: int
    market_type: str
    selections: List[MarketSelectionResponse]
    total_probability: Decimal = Field(..., description="Sum of implied probabilities")
    profit_margin: Decimal = Field(..., description="Potential profit margin as decimal")
    profit_percentage: Decimal = Field(..., description="Potential profit as percentage")

    @validator('profit_margin', 'profit_percentage')
    def validate_profit(cls, v):
        """Validate profit values."""
        if v < 0:
            raise ValueError('Profit values cannot be negative')
        return v


# Pagination schemas
class PaginationParams(BaseSchema):
    """Schema for pagination parameters."""
    page: int = Field(1, ge=1)
    size: int = Field(10, ge=1, le=100)


class PaginatedResponse(BaseSchema):
    """Generic paginated response schema."""
    items: List[BaseSchema]
    total: int
    page: int
    size: int
    pages: int

    @validator('pages', pre=True, always=True)
    def calculate_pages(cls, v, values):
        """Calculate total pages."""
        total = values.get('total', 0)
        size = values.get('size', 10)
        return (total + size - 1) // size if total > 0 else 0