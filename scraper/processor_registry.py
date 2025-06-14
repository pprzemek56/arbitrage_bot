"""
Field processor registry for data transformation and cleaning.
Implements a pluggable processor system with extensible processors.
"""

import re
import html
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type, Union
from urllib.parse import urljoin, urlparse
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta
import unicodedata

logger = logging.getLogger(__name__)


class ProcessorError(Exception):
    """Custom exception for processor errors."""
    pass


class BaseProcessor(ABC):
    """Abstract base class for field processors."""

    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"{self.__class__.__module__}.{self.__class__.__name__}")

    @abstractmethod
    def process(self, value: Any, **kwargs) -> Any:
        """
        Process the input value.

        Args:
            value: The value to process
            **kwargs: Additional processor-specific arguments

        Returns:
            The processed value
        """
        pass

    def validate_args(self, required_args: List[str], kwargs: Dict[str, Any]):
        """Validate that required arguments are present."""
        missing = [arg for arg in required_args if arg not in kwargs]
        if missing:
            raise ProcessorError(f"Processor {self.name} missing required arguments: {missing}")


class TrimProcessor(BaseProcessor):
    """Processor to trim whitespace."""

    def __init__(self):
        super().__init__("trim")

    def process(self, value: Any, **kwargs) -> str:
        """Trim whitespace from string value."""
        if value is None:
            return ""
        return str(value).strip()


class UppercaseProcessor(BaseProcessor):
    """Processor to convert to uppercase."""

    def __init__(self):
        super().__init__("uppercase")

    def process(self, value: Any, **kwargs) -> str:
        """Convert string to uppercase."""
        if value is None:
            return ""
        return str(value).upper()


class LowercaseProcessor(BaseProcessor):
    """Processor to convert to lowercase."""

    def __init__(self):
        super().__init__("lowercase")

    def process(self, value: Any, **kwargs) -> str:
        """Convert string to lowercase."""
        if value is None:
            return ""
        return str(value).lower()


class RegexProcessor(BaseProcessor):
    """Processor to apply regex transformations."""

    def __init__(self):
        super().__init__("regex")

    def process(self, value: Any, pattern: str = None, replacement: str = "",
                extract_group: int = None, **kwargs) -> str:
        """
        Apply regex transformation.

        Args:
            value: Input value
            pattern: Regex pattern
            replacement: Replacement string (for substitution)
            extract_group: Group number to extract (for extraction)
        """
        if value is None or pattern is None:
            return str(value) if value else ""

        value_str = str(value)

        try:
            if extract_group is not None:
                # Extract specific group
                match = re.search(pattern, value_str)
                if match and len(match.groups()) >= extract_group:
                    return match.group(extract_group)
                return ""
            else:
                # Replace pattern
                return re.sub(pattern, replacement, value_str)
        except re.error as e:
            self.logger.error(f"Regex error in pattern '{pattern}': {e}")
            return value_str


class ReplaceProcessor(BaseProcessor):
    """Processor to replace text."""

    def __init__(self):
        super().__init__("replace")

    def process(self, value: Any, search: str = None, replace: str = "", **kwargs) -> str:
        """
        Replace text in string.

        Args:
            value: Input value
            search: Text to search for
            replace: Replacement text
        """
        if value is None or search is None:
            return str(value) if value else ""

        return str(value).replace(search, replace)


class StripHtmlProcessor(BaseProcessor):
    """Processor to strip HTML tags."""

    def __init__(self):
        super().__init__("strip_html")

    def process(self, value: Any, **kwargs) -> str:
        """Strip HTML tags from string."""
        if value is None:
            return ""

        value_str = str(value)
        # Remove HTML tags
        clean = re.sub(r'<[^>]+>', '', value_str)
        # Decode HTML entities
        clean = html.unescape(clean)
        return clean.strip()


class AbsoluteUrlProcessor(BaseProcessor):
    """Processor to convert relative URLs to absolute."""

    def __init__(self):
        super().__init__("absolute_url")

    def process(self, value: Any, base_url: str = None, **kwargs) -> str:
        """
        Convert relative URL to absolute.

        Args:
            value: URL value
            base_url: Base URL for resolution
        """
        if value is None:
            return ""

        url_str = str(value).strip()
        if not url_str:
            return ""

        # Already absolute
        if url_str.startswith(('http://', 'https://')):
            return url_str

        # Protocol-relative
        if url_str.startswith('//'):
            return f"https:{url_str}"

        # Relative URL
        if base_url:
            return urljoin(base_url, url_str)

        return url_str


class NumberProcessor(BaseProcessor):
    """Processor to extract and format numbers."""

    def __init__(self):
        super().__init__("number")

    def process(self, value: Any, decimal_places: int = None, **kwargs) -> Union[str, float, int]:
        """
        Extract and format numbers.

        Args:
            value: Input value
            decimal_places: Number of decimal places to round to
        """
        if value is None:
            return 0

        value_str = str(value)

        # Extract numbers from string
        number_match = re.search(r'[\d,]+\.?\d*', value_str.replace(' ', ''))
        if not number_match:
            return 0

        number_str = number_match.group().replace(',', '')

        try:
            if '.' in number_str:
                num = float(number_str)
                if decimal_places is not None:
                    return round(num, decimal_places)
                return num
            else:
                return int(number_str)
        except ValueError:
            return 0


class DateProcessor(BaseProcessor):
    """Processor to parse and format dates."""

    def __init__(self):
        super().__init__("date")

    def process(self, value: Any, input_format: str = None, output_format: str = "%Y-%m-%d", **kwargs) -> str:
        """
        Parse and format dates.

        Args:
            value: Date value
            input_format: Input date format (strptime format)
            output_format: Output date format (strftime format)
        """
        if value is None:
            return ""

        value_str = str(value).strip()
        if not value_str:
            return ""

        try:
            if input_format:
                # Parse with specific format
                date_obj = datetime.strptime(value_str, input_format)
            else:
                # Try common formats
                formats = [
                    "%Y-%m-%d",
                    "%d/%m/%Y",
                    "%m/%d/%Y",
                    "%d-%m-%Y",
                    "%Y-%m-%d %H:%M:%S",
                    "%d/%m/%Y %H:%M",
                ]

                date_obj = None
                for fmt in formats:
                    try:
                        date_obj = datetime.strptime(value_str, fmt)
                        break
                    except ValueError:
                        continue

                if not date_obj:
                    return value_str  # Return original if can't parse

            return date_obj.strftime(output_format)

        except ValueError as e:
            self.logger.warning(f"Could not parse date '{value_str}': {e}")
            return value_str


class CleanTextProcessor(BaseProcessor):
    """Processor to clean and normalize text."""

    def __init__(self):
        super().__init__("clean_text")

    def process(self, value: Any, normalize_unicode: bool = True,
                remove_extra_spaces: bool = True, **kwargs) -> str:
        """
        Clean and normalize text.

        Args:
            value: Input text
            normalize_unicode: Normalize unicode characters
            remove_extra_spaces: Remove extra whitespace
        """
        if value is None:
            return ""

        text = str(value)

        if normalize_unicode:
            # Normalize unicode characters
            text = unicodedata.normalize('NFKD', text)

        if remove_extra_spaces:
            # Remove extra whitespace
            text = re.sub(r'\s+', ' ', text)

        return text.strip()


class SplitProcessor(BaseProcessor):
    """Processor to split text and extract parts."""

    def __init__(self):
        super().__init__("split")

    def process(self, value: Any, delimiter: str = " ", index: int = 0, **kwargs) -> str:
        """
        Split text and extract part.

        Args:
            value: Input text
            delimiter: Split delimiter
            index: Index of part to extract
        """
        if value is None:
            return ""

        parts = str(value).split(delimiter)

        try:
            return parts[index].strip()
        except IndexError:
            return ""


class OddsProcessor(BaseProcessor):
    """Processor specifically for betting odds."""

    def __init__(self):
        super().__init__("odds")

    def process(self, value: Any, format_type: str = "decimal", **kwargs) -> str:
        """
        Process betting odds.

        Args:
            value: Odds value
            format_type: Output format (decimal, fractional, american)
        """
        if value is None:
            return ""

        value_str = str(value).strip()
        if not value_str:
            return ""

        try:
            # Extract decimal odds
            if '/' in value_str:
                # Fractional odds (e.g., "5/2")
                parts = value_str.split('/')
                if len(parts) == 2:
                    decimal = (float(parts[0]) / float(parts[1])) + 1.0
                else:
                    decimal = 1.0
            else:
                # Assume decimal odds
                decimal = float(re.sub(r'[^\d.]', '', value_str))

            if format_type == "decimal":
                return f"{decimal:.2f}"
            elif format_type == "fractional":
                # Convert to fractional
                frac = decimal - 1.0
                # Simplified fraction conversion
                return f"{frac:.2f}/1"
            elif format_type == "american":
                # Convert to American odds
                if decimal >= 2.0:
                    american = (decimal - 1) * 100
                    return f"+{american:.0f}"
                else:
                    american = -100 / (decimal - 1)
                    return f"{american:.0f}"

            return f"{decimal:.2f}"

        except (ValueError, ZeroDivisionError) as e:
            self.logger.warning(f"Could not process odds '{value_str}': {e}")
            return value_str


class ProcessorRegistry:
    """Registry for managing field processors."""

    def __init__(self):
        self._processors: Dict[str, BaseProcessor] = {}
        self.logger = logging.getLogger(__name__)

        # Register default processors
        self._register_default_processors()

    def _register_default_processors(self):
        """Register default processors."""
        default_processors = [
            TrimProcessor(),
            UppercaseProcessor(),
            LowercaseProcessor(),
            RegexProcessor(),
            ReplaceProcessor(),
            StripHtmlProcessor(),
            AbsoluteUrlProcessor(),
            NumberProcessor(),
            DateProcessor(),
            CleanTextProcessor(),
            SplitProcessor(),
            OddsProcessor(),
        ]

        for processor in default_processors:
            self._processors[processor.name] = processor

    def register(self, processor: BaseProcessor):
        """Register a custom processor."""
        self._processors[processor.name] = processor
        self.logger.info(f"Registered processor: {processor.name}")

    def get(self, name: str) -> Optional[BaseProcessor]:
        """Get a processor by name."""
        return self._processors.get(name)

    def list_processors(self) -> List[str]:
        """Get list of available processor names."""
        return list(self._processors.keys())

    def process_value(self, value: Any, processors: List[Union[str, Dict[str, Any]]],
                      context: Optional[Dict[str, Any]] = None) -> Any:
        """
        Process a value through a pipeline of processors.

        Args:
            value: Input value
            processors: List of processor names or configs
            context: Additional context for processors

        Returns:
            Processed value
        """
        current_value = value
        context = context or {}

        for processor_config in processors:
            if isinstance(processor_config, str):
                # Simple processor name
                processor_name = processor_config
                processor_args = {}
            elif isinstance(processor_config, dict):
                # Processor with arguments
                processor_name = processor_config.get('name')
                processor_args = processor_config.get('args', {})
            else:
                self.logger.warning(f"Invalid processor config: {processor_config}")
                continue

            processor = self.get(processor_name)
            if not processor:
                self.logger.warning(f"Unknown processor: {processor_name}")
                continue

            try:
                # Merge context with processor args
                merged_args = {**context, **processor_args}
                current_value = processor.process(current_value, **merged_args)
            except Exception as e:
                self.logger.error(f"Error in processor {processor_name}: {e}")
                # Continue with current value on error

        return current_value


# Global processor registry instance
processor_registry = ProcessorRegistry()


def register_processor(processor: BaseProcessor):
    """Convenience function to register a processor."""
    processor_registry.register(processor)


def process_field(value: Any, processors: List[Union[str, Dict[str, Any]]],
                  context: Optional[Dict[str, Any]] = None) -> Any:
    """Convenience function to process a field value."""
    return processor_registry.process_value(value, processors, context)


# Example custom processor
class BookmakerNameProcessor(BaseProcessor):
    """Custom processor for normalizing bookmaker names."""

    def __init__(self):
        super().__init__("bookmaker_name")

    def process(self, value: Any, **kwargs) -> str:
        """Normalize bookmaker names."""
        if value is None:
            return ""

        name = str(value).strip()

        # Common normalization rules
        normalizations = {
            'bet365': 'Bet365',
            'william hill': 'William Hill',
            'betfair': 'Betfair',
            'pinnacle': 'Pinnacle',
            '1xbet': '1xBet',
        }

        name_lower = name.lower()
        for pattern, normalized in normalizations.items():
            if pattern in name_lower:
                return normalized

        return name


# Register custom processor
register_processor(BookmakerNameProcessor())