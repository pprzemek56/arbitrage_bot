"""
Configuration schema for the arbitrage betting scraper.
Uses Pydantic for validation and type safety.
"""

from typing import Dict, List, Optional, Union, Any, Literal
from pydantic import BaseModel, Field, validator, root_validator
from enum import Enum


class FetcherType(str, Enum):
    """Supported fetcher types."""
    STATIC = "static"
    BROWSER = "browser"
    API = "api"
    INTERACTIVE = "interactive"


class InstructionType(str, Enum):
    """Supported instruction types."""
    CLICK = "click"
    WAIT = "wait"
    LOOP = "loop"
    IF = "if"
    COLLECT = "collect"
    NAVIGATE = "navigate"
    INPUT = "input"
    SELECT = "select"
    SCROLL = "scroll"


class WaitCondition(BaseModel):
    """Wait condition configuration."""
    type: Literal["timeout", "selector", "url_contains", "element_count"] = "timeout"
    value: Union[str, int] = Field(..., description="Timeout in ms, selector, URL substring, or count")
    timeout_ms: Optional[int] = Field(30000, description="Maximum wait timeout")


class ClickInstruction(BaseModel):
    """Click instruction configuration."""
    type: Literal["click"] = "click"
    selector: str = Field(..., description="CSS selector or XPath for element to click")
    wait_after: Optional[WaitCondition] = None
    optional: bool = Field(False, description="Don't fail if element not found")
    all_matching: bool = Field(False, description="Click all elements matching selector")


class WaitInstruction(BaseModel):
    """Wait instruction configuration."""
    type: Literal["wait"] = "wait"
    condition: WaitCondition


class LoopInstruction(BaseModel):
    """Loop instruction configuration."""
    type: Literal["loop"] = "loop"
    iterator: str = Field(..., description="Loop type: 'pagination', 'dropdown_options', 'count', 'while'")
    max_iterations: Optional[int] = Field(100, description="Maximum loop iterations")
    break_condition: Optional[WaitCondition] = None
    instructions: List['Instruction'] = Field([], description="Instructions to execute in loop")

    # Pagination specific
    next_selector: Optional[str] = None

    # Dropdown specific
    dropdown_selector: Optional[str] = None
    skip_first_option: bool = False

    # Count specific
    count: Optional[int] = None

    # While specific
    while_condition: Optional[WaitCondition] = None


class IfInstruction(BaseModel):
    """Conditional instruction configuration."""
    type: Literal["if"] = "if"
    condition: WaitCondition
    then_instructions: List['Instruction'] = Field([], description="Instructions if condition is true")
    else_instructions: List['Instruction'] = Field([], description="Instructions if condition is false")


class CollectInstruction(BaseModel):
    """Data collection instruction."""
    type: Literal["collect"] = "collect"
    name: str = Field(..., description="Name for this collection")
    container_selector: str = Field(..., description="Container selector for items")
    item_selector: str = Field(..., description="Individual item selector")
    fields: Dict[str, 'FieldConfig']
    limit: Optional[int] = None


class NavigateInstruction(BaseModel):
    """Navigate to URL instruction."""
    type: Literal["navigate"] = "navigate"
    url: str = Field(..., description="URL to navigate to")
    wait_after: Optional[WaitCondition] = None


class InputInstruction(BaseModel):
    """Input text instruction."""
    type: Literal["input"] = "input"
    selector: str = Field(..., description="Input field selector")
    value: str = Field(..., description="Text to input")
    clear_first: bool = Field(True, description="Clear field before input")


class SelectInstruction(BaseModel):
    """Select option instruction."""
    type: Literal["select"] = "select"
    selector: str = Field(..., description="Select element selector")
    value: Optional[str] = None
    text: Optional[str] = None
    index: Optional[int] = None


class ScrollInstruction(BaseModel):
    """Scroll instruction."""
    type: Literal["scroll"] = "scroll"
    direction: Literal["up", "down", "to_element"] = "down"
    amount: Optional[int] = Field(None, description="Pixels to scroll or scroll count")
    selector: Optional[str] = Field(None, description="Element to scroll to (for 'to_element')")


# Union type for all instructions
Instruction = Union[
    ClickInstruction,
    WaitInstruction,
    LoopInstruction,
    IfInstruction,
    CollectInstruction,
    NavigateInstruction,
    InputInstruction,
    SelectInstruction,
    ScrollInstruction
]


class ProcessorConfig(BaseModel):
    """Field processor configuration."""
    name: str
    args: Optional[Dict[str, Any]] = {}


class FieldConfig(BaseModel):
    """Field extraction configuration."""
    selector: Union[str, List[str]] = Field(..., description="CSS selector or XPath")
    attribute: str = Field("text", description="Attribute to extract: text, href, src, etc.")
    processors: List[Union[str, ProcessorConfig]] = Field([], description="Post-processing pipeline")
    required: bool = False
    default: Optional[str] = None


class FetcherConfig(BaseModel):
    """Fetcher configuration."""
    type: FetcherType
    timeout_ms: int = Field(30000, description="Request timeout in milliseconds")
    headers: Dict[str, str] = Field({}, description="HTTP headers")

    # Browser specific
    headless: bool = Field(True, description="Run browser in headless mode")
    viewport: Dict[str, int] = Field({"width": 1920, "height": 1080})

    # API specific
    method: Optional[Literal["GET", "POST", "PUT", "DELETE"]] = "GET"
    body: Optional[Dict[str, Any]] = None
    auth: Optional[Dict[str, str]] = None


class DatabaseConfig(BaseModel):
    """Database configuration."""
    url: str = Field(..., description="Database connection URL")
    bookmaker_name: str = Field(..., description="Bookmaker name for categorization")
    category_name: str = Field("General", description="Event category name")


class MetaConfig(BaseModel):
    """Metadata configuration."""
    name: str = Field(..., description="Scraper name")
    description: Optional[str] = None
    start_url: str = Field(..., description="Starting URL")
    allowed_domains: List[str] = Field([], description="Allowed domains for navigation")


class ScraperConfig(BaseModel):
    """Main scraper configuration."""
    meta: MetaConfig
    fetcher: FetcherConfig
    database: DatabaseConfig
    instructions: List[Instruction] = Field([], description="Scraping instructions")
    collections: Dict[str, CollectInstruction] = Field({}, description="Named data collections")

    @validator('instructions')
    def validate_instructions(cls, v):
        """Validate that instructions are properly structured."""
        if not v:
            raise ValueError("At least one instruction must be provided")
        return v

    @root_validator
    def validate_config(cls, values):
        """Cross-field validation."""
        fetcher_config = values.get('fetcher', {})
        instructions = values.get('instructions', [])

        # If using browser fetcher, ensure we have browser-compatible instructions
        if fetcher_config.get('type') == FetcherType.BROWSER:
            browser_instructions = ['click', 'wait', 'input', 'select', 'scroll']
            has_browser_instruction = any(
                inst.get('type') in browser_instructions for inst in instructions
            )
            if not has_browser_instruction:
                raise ValueError("Browser fetcher requires at least one browser-compatible instruction")

        return values


# Forward references
LoopInstruction.model_rebuild()
IfInstruction.model_rebuild()
CollectInstruction.model_rebuild()


class ConfigLoader:
    """Configuration loader with validation."""

    @staticmethod
    def load_from_yaml(file_path: str) -> ScraperConfig:
        """Load configuration from YAML file."""
        import yaml
        from pathlib import Path

        config_path = Path(file_path)
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {file_path}")

        with open(config_path, 'r', encoding='utf-8') as f:
            raw_config = yaml.safe_load(f)

        return ScraperConfig(**raw_config)

    @staticmethod
    def load_from_dict(config_dict: Dict[str, Any]) -> ScraperConfig:
        """Load configuration from dictionary."""
        return ScraperConfig(**config_dict)

    @staticmethod
    def validate_config(config_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Validate configuration without creating instance."""
        try:
            ScraperConfig(**config_dict)
            return {"valid": True, "errors": []}
        except Exception as e:
            return {"valid": False, "errors": [str(e)]}