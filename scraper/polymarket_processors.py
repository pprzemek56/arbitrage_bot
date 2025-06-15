"""
Custom processors for Polymarket data processing and arbitrage detection.
These processors extend the base processor framework with Polymarket-specific logic.
"""

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any, List, Dict
from scraper.processor_registry import BaseProcessor, register_processor


class ArbitrageCalculatorProcessor(BaseProcessor):
    """Processor to calculate implied probability sum from outcome prices."""

    def __init__(self):
        super().__init__("arbitrage_calculator")

    def process(self, value: Any, **kwargs) -> str:
        """Calculate the sum of implied probabilities from outcome prices."""
        if value is None:
            return "1.0"

        try:
            # Parse the outcome prices (usually a JSON string like "[0.45, 0.60]")
            if isinstance(value, str):
                # Clean the string and parse JSON
                cleaned = value.strip().replace("'", '"')
                if cleaned.startswith('[') and cleaned.endswith(']'):
                    prices = json.loads(cleaned)
                else:
                    # Try to extract numbers with regex
                    numbers = re.findall(r'[0-9]+\.?[0-9]*', cleaned)
                    prices = [float(n) for n in numbers if float(n) <= 1.0]
            elif isinstance(value, list):
                prices = value
            else:
                return "1.0"

            # Calculate sum of probabilities
            if not prices:
                return "1.0"

            total_prob = sum(float(price) for price in prices if 0 <= float(price) <= 1)
            return f"{total_prob:.6f}"

        except (json.JSONDecodeError, ValueError, TypeError) as e:
            self.logger.warning(f"Could not parse outcome prices '{value}': {e}")
            return "1.0"


class ArbitrageDetectorProcessor(BaseProcessor):
    """Processor to detect arbitrage opportunities."""

    def __init__(self):
        super().__init__("arbitrage_detector")

    def process(self, value: Any, trading_fee: float = 0.01, min_profit: float = 0.005, **kwargs) -> str:
        """
        Detect if an arbitrage opportunity exists.

        Args:
            value: Outcome prices (JSON string or list)
            trading_fee: Estimated trading fees (default 1%)
            min_profit: Minimum profit threshold (default 0.5%)
        """
        if value is None:
            return "false"

        try:
            # Parse outcome prices
            if isinstance(value, str):
                cleaned = value.strip().replace("'", '"')
                if cleaned.startswith('[') and cleaned.endswith(']'):
                    prices = json.loads(cleaned)
                else:
                    numbers = re.findall(r'[0-9]+\.?[0-9]*', cleaned)
                    prices = [float(n) for n in numbers if float(n) <= 1.0]
            elif isinstance(value, list):
                prices = value
            else:
                return "false"

            if not prices or len(prices) < 2:
                return "false"

            # Calculate total implied probability
            total_prob = sum(float(price) for price in prices)

            # Account for trading fees
            fee_adjusted_total = total_prob + trading_fee

            # Check if arbitrage opportunity exists
            if fee_adjusted_total < (1.0 - min_profit):
                profit_potential = 1.0 - fee_adjusted_total
                return f"true,{profit_potential:.4f}"

            return "false"

        except (json.JSONDecodeError, ValueError, TypeError) as e:
            self.logger.warning(f"Could not detect arbitrage for '{value}': {e}")
            return "false"


class OutcomePriceExtractorProcessor(BaseProcessor):
    """Processor to extract individual outcome prices from JSON array."""

    def __init__(self):
        super().__init__("outcome_price_extractor")

    def process(self, value: Any, index: int = 0, **kwargs) -> str:
        """
        Extract a specific outcome price by index.

        Args:
            value: Outcome prices (JSON string or list)
            index: Index of the price to extract (0 = first, 1 = second, etc.)
        """
        if value is None:
            return "0.5"

        try:
            # Parse outcome prices
            if isinstance(value, str):
                cleaned = value.strip().replace("'", '"')
                if cleaned.startswith('[') and cleaned.endswith(']'):
                    prices = json.loads(cleaned)
                else:
                    numbers = re.findall(r'[0-9]+\.?[0-9]*', cleaned)
                    prices = [float(n) for n in numbers if float(n) <= 1.0]
            elif isinstance(value, list):
                prices = value
            else:
                return "0.5"

            # Extract price at specified index
            if index < len(prices):
                price = float(prices[index])
                return f"{price:.6f}"

            return "0.5"

        except (json.JSONDecodeError, ValueError, TypeError, IndexError) as e:
            self.logger.warning(f"Could not extract price at index {index} from '{value}': {e}")
            return "0.5"


class PolymarketCategoryProcessor(BaseProcessor):
    """Processor to categorize Polymarket events based on tags and content."""

    def __init__(self):
        super().__init__("polymarket_category")

        # Define category mappings
        self.category_keywords = {
            'politics': ['election', 'president', 'congress', 'senate', 'vote', 'policy', 'government', 'politician'],
            'sports': ['nfl', 'nba', 'mlb', 'nhl', 'soccer', 'football', 'basketball', 'baseball', 'olympics',
                       'world cup'],
            'crypto': ['bitcoin', 'ethereum', 'crypto', 'defi', 'nft', 'blockchain', 'coinbase', 'binance'],
            'economics': ['fed', 'interest rate', 'inflation', 'gdp', 'unemployment', 'stock market', 'recession'],
            'entertainment': ['oscar', 'emmy', 'grammy', 'movie', 'tv show', 'celebrity', 'awards'],
            'science': ['spacex', 'nasa', 'climate', 'vaccine', 'discovery', 'research', 'technology'],
            'business': ['ipo', 'merger', 'earnings', 'ceo', 'company', 'startup', 'acquisition']
        }

    def process(self, value: Any, question_text: str = "", **kwargs) -> str:
        """
        Categorize based on tags and question content.

        Args:
            value: Tags (JSON string or list)
            question_text: Market question text for additional context
        """
        if value is None and not question_text:
            return "general"

        try:
            # Parse tags
            tags = []
            if value:
                if isinstance(value, str):
                    cleaned = value.strip().replace("'", '"')
                    if cleaned.startswith('[') and cleaned.endswith(']'):
                        tags = json.loads(cleaned)
                    else:
                        # Try to split on common delimiters
                        tags = [tag.strip() for tag in re.split(r'[,;|]', cleaned) if tag.strip()]
                elif isinstance(value, list):
                    tags = value

            # Combine tags and question for analysis
            text_to_analyze = ' '.join(tags + [question_text]).lower()

            # Score each category
            category_scores = {}
            for category, keywords in self.category_keywords.items():
                score = sum(1 for keyword in keywords if keyword in text_to_analyze)
                if score > 0:
                    category_scores[category] = score

            # Return the highest scoring category
            if category_scores:
                best_category = max(category_scores, key=category_scores.get)
                return best_category

            return "general"

        except (json.JSONDecodeError, ValueError, TypeError) as e:
            self.logger.warning(f"Could not categorize '{value}': {e}")
            return "general"


class VolumeFormatterProcessor(BaseProcessor):
    """Processor to format volume numbers with appropriate units."""

    def __init__(self):
        super().__init__("volume_formatter")

    def process(self, value: Any, currency: str = "USD", **kwargs) -> str:
        """
        Format volume with appropriate units (K, M, B).

        Args:
            value: Volume amount
            currency: Currency symbol (default USD)
        """
        if value is None:
            return f"0 {currency}"

        try:
            volume = float(value)

            if volume >= 1_000_000_000:
                return f"{volume / 1_000_000_000:.1f}B {currency}"
            elif volume >= 1_000_000:
                return f"{volume / 1_000_000:.1f}M {currency}"
            elif volume >= 1_000:
                return f"{volume / 1_000:.1f}K {currency}"
            else:
                return f"{volume:.2f} {currency}"

        except (ValueError, TypeError) as e:
            self.logger.warning(f"Could not format volume '{value}': {e}")
            return f"0 {currency}"


class CLOBTokenExtractorProcessor(BaseProcessor):
    """Processor to extract CLOB token IDs from JSON string."""

    def __init__(self):
        super().__init__("clob_token_extractor")

    def process(self, value: Any, index: int = 0, **kwargs) -> str:
        """
        Extract CLOB token ID by index.

        Args:
            value: CLOB token IDs (JSON string)
            index: Index of token to extract
        """
        if value is None:
            return ""

        try:
            # Parse CLOB token IDs
            if isinstance(value, str):
                cleaned = value.strip().replace("'", '"')
                if cleaned.startswith('[') and cleaned.endswith(']'):
                    token_ids = json.loads(cleaned)
                else:
                    # Try to extract large numbers (token IDs are very long)
                    token_ids = re.findall(r'\d{50,}', cleaned)
            elif isinstance(value, list):
                token_ids = value
            else:
                return ""

            # Extract token at specified index
            if index < len(token_ids):
                return str(token_ids[index])

            return ""

        except (json.JSONDecodeError, ValueError, TypeError, IndexError) as e:
            self.logger.warning(f"Could not extract CLOB token at index {index} from '{value}': {e}")
            return ""


class MarketStatusNormalizerProcessor(BaseProcessor):
    """Processor to normalize market status values."""

    def __init__(self):
        super().__init__("market_status_normalizer")

    def process(self, value: Any, **kwargs) -> str:
        """Normalize market status to standard values."""
        if value is None:
            return "unknown"

        status = str(value).lower().strip()

        # Map various status values to standard ones
        status_mapping = {
            'true': 'active',
            'false': 'inactive',
            '1': 'active',
            '0': 'inactive',
            'open': 'active',
            'closed': 'closed',
            'resolved': 'resolved',
            'cancelled': 'cancelled',
            'suspended': 'suspended'
        }

        return status_mapping.get(status, status)


class ProfitCalculatorProcessor(BaseProcessor):
    """Processor to calculate potential profit from arbitrage opportunity."""

    def __init__(self):
        super().__init__("profit_calculator")

    def process(self, value: Any, investment: float = 100.0, trading_fee: float = 0.01, **kwargs) -> str:
        """
        Calculate potential profit from arbitrage.

        Args:
            value: Outcome prices (JSON string or list)
            investment: Investment amount (default $100)
            trading_fee: Trading fee percentage (default 1%)
        """
        if value is None:
            return "0.00"

        try:
            # Parse outcome prices
            if isinstance(value, str):
                cleaned = value.strip().replace("'", '"')
                if cleaned.startswith('[') and cleaned.endswith(']'):
                    prices = json.loads(cleaned)
                else:
                    numbers = re.findall(r'[0-9]+\.?[0-9]*', cleaned)
                    prices = [float(n) for n in numbers if float(n) <= 1.0]
            elif isinstance(value, list):
                prices = value
            else:
                return "0.00"

            if not prices or len(prices) < 2:
                return "0.00"

            # Calculate arbitrage profit
            total_prob = sum(float(price) for price in prices)

            if total_prob < 1.0:
                # Calculate optimal position sizing
                position_sizes = [investment * (1 / price) / sum(1 / p for p in prices) for price in prices]

                # Calculate expected profit (before fees)
                expected_return = min(sum(position_sizes) / price for price in prices)
                gross_profit = expected_return - investment

                # Account for trading fees
                total_fees = sum(pos * trading_fee for pos in position_sizes)
                net_profit = gross_profit - total_fees

                return f"{net_profit:.2f}"

            return "0.00"

        except (json.JSONDecodeError, ValueError, TypeError, ZeroDivisionError) as e:
            self.logger.warning(f"Could not calculate profit for '{value}': {e}")
            return "0.00"


# Register all custom processors
def register_polymarket_processors():
    """Register all Polymarket-specific processors."""
    processors = [
        ArbitrageCalculatorProcessor(),
        ArbitrageDetectorProcessor(),
        OutcomePriceExtractorProcessor(),
        PolymarketCategoryProcessor(),
        VolumeFormatterProcessor(),
        CLOBTokenExtractorProcessor(),
        MarketStatusNormalizerProcessor(),
        ProfitCalculatorProcessor()
    ]

    for processor in processors:
        register_processor(processor)

    print(f"Registered {len(processors)} Polymarket-specific processors")


# Auto-register when module is imported
if __name__ == "__main__":
    register_polymarket_processors()
else:
    register_polymarket_processors()