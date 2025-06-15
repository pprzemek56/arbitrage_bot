#!/usr/bin/env python3
"""
Integration script to add Polymarket custom processors to the scraper.
Run this after setting up the Polymarket configuration.
"""

import os
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def setup_polymarket_processors():
    """Set up Polymarket custom processors."""
    try:
        # Import and register Polymarket processors
        from scraper.processor_registry import register_processor, BaseProcessor

        # Simple Polymarket-specific processors
        class PolymarketPriceProcessor(BaseProcessor):
            def __init__(self):
                super().__init__("polymarket_price")

            def process(self, value, **kwargs):
                """Process Polymarket price values."""
                if value is None:
                    return "0.5"

                try:
                    # Handle JSON arrays like "[0.45, 0.60]"
                    if isinstance(value, str) and value.startswith('['):
                        import json
                        prices = json.loads(value.replace("'", '"'))
                        return str(float(prices[0]) if prices else 0.5)

                    return str(float(value))
                except (ValueError, TypeError, json.JSONDecodeError):
                    return "0.5"

        # Register the processor
        register_processor(PolymarketPriceProcessor())
        print("✓ Polymarket processors registered successfully")
        return True

    except ImportError as e:
        print(f"⚠ Could not import processor registry: {e}")
        return False
    except Exception as e:
        print(f"✗ Error setting up processors: {e}")
        return False


def create_simple_polymarket_config():
    """Create a simple Polymarket configuration for testing."""
    config_dir = Path("configs")
    config_dir.mkdir(exist_ok=True)

    simple_config = """meta:
  name: "polymarket_simple_test"
  description: "Simple Polymarket test configuration"
  start_url: "https://gamma-api.polymarket.com/markets"

fetcher:
  type: "api"
  method: "GET"
  timeout_ms: 30000
  headers:
    Accept: "application/json"

database:
  url: "postgresql://postgres:password@localhost:5432/arbitrage_bot"
  bookmaker_name: "Polymarket"
  category_name: "Prediction Markets"

instructions:
  - type: "collect"
    name: "test_markets"
    container_selector: "$"
    item_selector: "$[0:5]"
    limit: 5
    fields:
      market_id:
        selector: "$.id"
        attribute: "text"
        processors: ["trim"]

      question:
        selector: "$.question"
        attribute: "text"
        processors: ["trim"]

      volume:
        selector: "$.volume"
        attribute: "text"
        processors: ["number"]
        default: "0"
"""

    config_path = config_dir / "polymarket_simple_test.yml"
    with open(config_path, 'w') as f:
        f.write(simple_config)

    print(f"✓ Created simple test config: {config_path}")
    return config_path


def main():
    """Main setup function."""
    print("🚀 Setting up Polymarket integration...")

    # Setup processors
    processor_success = setup_polymarket_processors()

    # Create test config
    test_config_path = create_simple_polymarket_config()

    # Test validation
    if processor_success:
        try:
            from scraper.config_schema import ConfigLoader
            config = ConfigLoader.load_from_yaml(str(test_config_path))
            print("✓ Configuration validation successful")

            print(f"\n📋 Next steps:")
            print(f"1. Test the simple config: python -m scraper.cli validate {test_config_path}")
            print(f"2. Run a test scrape: python -m scraper.cli run {test_config_path}")
            print(f"3. Check the full Polymarket config: configs/polymarket_comprehensive.yml")

        except Exception as e:
            print(f"⚠ Configuration validation failed: {e}")
            print("Check that all dependencies are installed and the config syntax is correct")

    print("\n✅ Polymarket integration setup complete!")


if __name__ == "__main__":
    main()