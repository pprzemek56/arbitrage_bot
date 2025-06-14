#!/usr/bin/env python3
"""
Comprehensive example showing how to use the arbitrage betting scraper.
Demonstrates the complete integration of all components.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Dict, Any, List
import yaml

# Import scraper components
from scraper.config_schema import ConfigLoader, ScraperConfig
from scraper.scraper_pipeline import ScraperRunner, run_scraper_sync
from scraper.processor_registry import register_processor, BaseProcessor
from scraper.fetcher_strategies import FetcherFactory
from database.config import initialize_database, DatabaseConfig


def setup_example_environment():
    """Setup the environment for examples."""
    # Create directories
    dirs = ['configs', 'logs', 'results']
    for dir_name in dirs:
        Path(dir_name).mkdir(exist_ok=True)

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/scraper.log'),
            logging.StreamHandler()
        ]
    )

    print("✓ Environment setup complete")


def create_example_configs():
    """Create example configuration files."""

    # Example 1: Simple static scraper
    static_config = {
        'meta': {
            'name': 'example_static_scraper',
            'description': 'Example static HTML scraper for betting odds',
            'start_url': 'https://example-sportsbook.com/odds',
            'allowed_domains': ['example-sportsbook.com']
        },
        'fetcher': {
            'type': 'static',
            'timeout_ms': 30000,
            'headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        },
        'database': {
            'url': os.getenv('DATABASE_URL', 'postgresql://postgres:password@localhost:5432/arbitrage_bot'),
            'bookmaker_name': 'Example Sportsbook',
            'category_name': 'Football'
        },
        'instructions': [
            {
                'type': 'wait',
                'condition': {
                    'type': 'timeout',
                    'value': 2000
                }
            },
            {
                'type': 'collect',
                'name': 'football_matches',
                'container_selector': '.matches-container',
                'item_selector': '.match-row',
                'limit': 50,
                'fields': {
                    'match_name': {
                        'selector': '.match-name',
                        'attribute': 'text',
                        'processors': ['trim', 'clean_text'],
                        'required': True
                    },
                    'home_team': {
                        'selector': '.team-home',
                        'attribute': 'text',
                        'processors': ['trim']
                    },
                    'away_team': {
                        'selector': '.team-away',
                        'attribute': 'text',
                        'processors': ['trim']
                    },
                    'match_date': {
                        'selector': '.match-date',
                        'attribute': 'text',
                        'processors': ['trim', {'name': 'date', 'args': {'output_format': '%Y-%m-%d %H:%M'}}]
                    },
                    'home_odds': {
                        'selector': '.odds-home',
                        'attribute': 'text',
                        'processors': ['trim', 'odds'],
                        'required': True
                    },
                    'draw_odds': {
                        'selector': '.odds-draw',
                        'attribute': 'text',
                        'processors': ['trim', 'odds']
                    },
                    'away_odds': {
                        'selector': '.odds-away',
                        'attribute': 'text',
                        'processors': ['trim', 'odds'],
                        'required': True
                    },
                    'market_type': {
                        'selector': 'body',  # Dummy selector
                        'attribute': 'text',
                        'default': 'match_winner'
                    }
                }
            }
        ]
    }

    # Example 2: Interactive browser scraper with complex logic
    interactive_config = {
        'meta': {
            'name': 'advanced_interactive_scraper',
            'description': 'Advanced scraper with user interactions and pagination',
            'start_url': 'https://betting-exchange.com/football',
            'allowed_domains': ['betting-exchange.com']
        },
        'fetcher': {
            'type': 'interactive',
            'headless': True,
            'timeout_ms': 60000,
            'viewport': {
                'width': 1920,
                'height': 1080
            }
        },
        'database': {
            'url': os.getenv('DATABASE_URL', 'postgresql://postgres:password@localhost:5432/arbitrage_bot'),
            'bookmaker_name': 'Betting Exchange',
            'category_name': 'Football'
        },
        'instructions': [
            # Handle cookie consent
            {
                'type': 'if',
                'condition': {
                    'type': 'selector',
                    'value': '#cookie-consent-banner',
                    'timeout_ms': 5000
                },
                'then_instructions': [
                    {
                        'type': 'click',
                        'selector': '#accept-cookies',
                        'wait_after': {
                            'type': 'timeout',
                            'value': 2000
                        }
                    }
                ]
            },

            # Wait for main content
            {
                'type': 'wait',
                'condition': {
                    'type': 'selector',
                    'value': '.market-list',
                    'timeout_ms': 15000
                }
            },

            # Loop through different leagues
            {
                'type': 'loop',
                'iterator': 'dropdown_options',
                'dropdown_selector': '#league-selector',
                'skip_first_option': True,
                'max_iterations': 8,
                'instructions': [
                    # Wait for league data to load
                    {
                        'type': 'wait',
                        'condition': {
                            'type': 'timeout',
                            'value': 3000
                        }
                    },

                    # Collect matches for current league
                    {
                        'type': 'collect',
                        'name': 'league_matches',
                        'container_selector': '.market-list',
                        'item_selector': '.market-row',
                        'limit': 25,
                        'fields': {
                            'league_name': {
                                'selector': '#league-selector option:checked',
                                'attribute': 'text'
                            },
                            'event_name': {
                                'selector': '.event-name',
                                'attribute': 'text',
                                'processors': ['trim', 'clean_text']
                            },
                            'back_price': {
                                'selector': '.back-price',
                                'attribute': 'text',
                                'processors': ['trim', 'odds']
                            },
                            'lay_price': {
                                'selector': '.lay-price',
                                'attribute': 'text',
                                'processors': ['trim', 'odds']
                            },
                            'volume': {
                                'selector': '.volume-matched',
                                'attribute': 'text',
                                'processors': ['trim', 'number']
                            }
                        }
                    }
                ]
            },

            # Pagination through results
            {
                'type': 'loop',
                'iterator': 'pagination',
                'next_selector': '.pagination .next:not(.disabled)',
                'max_iterations': 5,
                'break_condition': {
                    'type': 'selector',
                    'value': '.pagination .next.disabled'
                },
                'instructions': [
                    {
                        'type': 'wait',
                        'condition': {
                            'type': 'timeout',
                            'value': 2000
                        }
                    },
                    {
                        'type': 'collect',
                        'name': 'paginated_matches',
                        'container_selector': '.market-list',
                        'item_selector': '.market-row',
                        'fields': {
                            'event_name': {
                                'selector': '.event-name',
                                'attribute': 'text'
                            },
                            'back_price': {
                                'selector': '.back-price',
                                'attribute': 'text',
                                'processors': ['odds']
                            },
                            'lay_price': {
                                'selector': '.lay-price',
                                'attribute': 'text',
                                'processors': ['odds']
                            }
                        }
                    }
                ]
            }
        ]
    }

    # Example 3: API scraper
    api_config = {
        'meta': {
            'name': 'api_odds_scraper',
            'description': 'API-based odds scraper',
            'start_url': 'https://api.sportsbook.com/v1/odds'
        },
        'fetcher': {
            'type': 'api',
            'method': 'GET',
            'timeout_ms': 30000,
            'headers': {
                'Accept': 'application/json',
                'X-API-Key': os.getenv('SPORTSBOOK_API_KEY', 'your-api-key-here')
            },
            'auth': {
                'type': 'bearer',
                'token': os.getenv('SPORTSBOOK_TOKEN', 'your-token-here')
            }
        },
        'database': {
            'url': os.getenv('DATABASE_URL', 'postgresql://postgres:password@localhost:5432/arbitrage_bot'),
            'bookmaker_name': 'API Sportsbook',
            'category_name': 'Multiple Sports'
        },
        'instructions': [
            {
                'type': 'collect',
                'name': 'api_odds',
                'container_selector': '$.data.events',  # JSONPath for API
                'item_selector': '$',
                'fields': {
                    'event_id': {
                        'selector': '$.id',
                        'attribute': 'text'
                    },
                    'sport': {
                        'selector': '$.sport.name',
                        'attribute': 'text'
                    },
                    'home_team': {
                        'selector': '$.competitors[0].name',
                        'attribute': 'text'
                    },
                    'away_team': {
                        'selector': '$.competitors[1].name',
                        'attribute': 'text'
                    },
                    'start_time': {
                        'selector': '$.start_time',
                        'attribute': 'text',
                        'processors': ['date']
                    },
                    'home_odds': {
                        'selector': '$.markets.moneyline.outcomes[0].price',
                        'attribute': 'text',
                        'processors': ['odds']
                    },
                    'away_odds': {
                        'selector': '$.markets.moneyline.outcomes[1].price',
                        'attribute': 'text',
                        'processors': ['odds']
                    }
                }
            }
        ]
    }

    # Save configurations
    configs = [
        ('static_example.yml', static_config),
        ('interactive_example.yml', interactive_config),
        ('api_example.yml', api_config)
    ]

    for filename, config in configs:
        config_path = Path('configs') / filename
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, indent=2)
        print(f"✓ Created {filename}")

    return [str(Path('configs') / filename) for filename, _ in configs]


def create_custom_processor():
    """Create and register a custom processor for this example."""

    class SpreadProcessor(BaseProcessor):
        """Custom processor for betting spreads."""

        def __init__(self):
            super().__init__("spread")

        def process(self, value: Any, **kwargs) -> str:
            """Process betting spread values."""
            if value is None:
                return ""

            # Clean spread value (e.g., "+2.5", "-1.5")
            import re
            cleaned = re.sub(r'[^\d.+-]', '', str(value))

            try:
                spread_value = float(cleaned)
                return f"{spread_value:+.1f}"  # Format with sign
            except ValueError:
                return str(value)

    # Register the custom processor
    register_processor(SpreadProcessor())
    print("✓ Custom spread processor registered")


def setup_test_database():
    """Setup test database for examples."""
    try:
        # Initialize database
        db_config = DatabaseConfig(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', '5432')),
            database=os.getenv('DB_NAME', 'arbitrage_bot'),
            username=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD', 'password')
        )

        db_manager = initialize_database(db_config)
        db_manager.create_tables()

        print("✓ Database initialized")
        return True

    except Exception as e:
        print(f"⚠ Database setup failed: {e}")
        print("  Some examples may not work without database connectivity")
        return False


async def run_example_scraper(config_path: str, description: str):
    """Run an example scraper."""
    print(f"\n{'=' * 60}")
    print(f"Running: {description}")
    print(f"Config: {config_path}")
    print(f"{'=' * 60}")

    try:
        # Load configuration
        config = ConfigLoader.load_from_yaml(config_path)
        print(f"✓ Configuration loaded: {config.meta.name}")

        # Create and run scraper
        runner = ScraperRunner()
        result = await runner.run_scraper(config)

        # Display results
        print(f"\nResults:")
        print(f"  Events collected: {len(result.events)}")
        print(f"  Markets collected: {len(result.markets)}")
        print(f"  Selections collected: {len(result.selections)}")
        print(f"  Errors: {len(result.errors)}")
        print(f"  Duration: {result.metadata.get('duration_seconds', 0):.2f}s")

        if result.errors:
            print(f"\nErrors encountered:")
            for error in result.errors:
                print(f"  - {error}")

        # Show sample data
        if result.events:
            print(f"\nSample events (showing first 3):")
            for i, event in enumerate(result.events[:3]):
                print(f"  Event {i + 1}: {event}")

        # Save results
        import json
        results_file = Path('results') / f"{config.meta.name}_results.json"
        with open(results_file, 'w') as f:
            json.dump({
                'metadata': result.metadata,
                'events': result.events,
                'markets': result.markets,
                'selections': result.selections,
                'errors': result.errors
            }, f, indent=2, default=str)

        print(f"✓ Results saved to: {results_file}")

        return result

    except Exception as e:
        print(f"✗ Error running scraper: {e}")
        logging.error(f"Scraper error: {e}", exc_info=True)
        return None


def demonstrate_arbitrage_detection(results: List[Any]):
    """Demonstrate basic arbitrage detection logic."""
    print(f"\n{'=' * 60}")
    print("ARBITRAGE OPPORTUNITY DETECTION")
    print(f"{'=' * 60}")

    # This is a simplified example - real arbitrage detection would be more complex
    all_events = []
    for result in results:
        if result and result.events:
            all_events.extend(result.events)

    if not all_events:
        print("No events available for arbitrage detection")
        return

    print(f"Analyzing {len(all_events)} events for arbitrage opportunities...")

    # Group events by teams/name for comparison
    from collections import defaultdict
    event_groups = defaultdict(list)

    for event in all_events:
        # Create a normalized key for matching events
        key = f"{event.get('home_team', '')}_vs_{event.get('away_team', '')}"
        key = key.lower().replace(' ', '_')
        event_groups[key].append(event)

    arbitrage_opportunities = []

    for event_key, events in event_groups.items():
        if len(events) < 2:
            continue  # Need at least 2 bookmakers

        # Find best odds for each outcome
        best_home_odds = 0
        best_away_odds = 0
        best_home_source = ""
        best_away_source = ""

        for event in events:
            try:
                home_odds = float(event.get('home_odds', 0))
                away_odds = float(event.get('away_odds', 0))
                source = event.get('source', 'Unknown')

                if home_odds > best_home_odds:
                    best_home_odds = home_odds
                    best_home_source = source

                if away_odds > best_away_odds:
                    best_away_odds = away_odds
                    best_away_source = source

            except ValueError:
                continue

        if best_home_odds > 0 and best_away_odds > 0:
            # Calculate arbitrage percentage
            arbitrage_percentage = (1 / best_home_odds + 1 / best_away_odds) * 100

            if arbitrage_percentage < 100:  # Arbitrage opportunity exists
                profit_margin = 100 - arbitrage_percentage

                arbitrage_opportunities.append({
                    'event': event_key.replace('_', ' '),
                    'home_odds': best_home_odds,
                    'home_source': best_home_source,
                    'away_odds': best_away_odds,
                    'away_source': best_away_source,
                    'arbitrage_percentage': arbitrage_percentage,
                    'profit_margin': profit_margin
                })

    if arbitrage_opportunities:
        print(f"\n🎯 Found {len(arbitrage_opportunities)} arbitrage opportunities!")

        for opp in sorted(arbitrage_opportunities, key=lambda x: x['profit_margin'], reverse=True):
            print(f"\nEvent: {opp['event']}")
            print(f"  Home: {opp['home_odds']} ({opp['home_source']})")
            print(f"  Away: {opp['away_odds']} ({opp['away_source']})")
            print(f"  Profit Margin: {opp['profit_margin']:.2f}%")
            print(f"  Arbitrage %: {opp['arbitrage_percentage']:.2f}%")
    else:
        print("No arbitrage opportunities detected in current data")


def create_monitoring_example():
    """Create an example of continuous monitoring setup."""
    monitoring_script = '''#!/usr/bin/env python3
"""
Continuous monitoring script for arbitrage opportunities.
This script runs scrapers periodically and checks for arbitrage.
"""

import schedule
import time
import logging
from datetime import datetime
from scraper.scraper_pipeline import ScraperRunner
from scraper.config_schema import ConfigLoader

def run_scheduled_scraping():
    """Run all configured scrapers."""
    config_files = [
        'configs/static_example.yml',
        'configs/interactive_example.yml',
        'configs/api_example.yml'
    ]

    results = []
    runner = ScraperRunner()

    for config_file in config_files:
        try:
            config = ConfigLoader.load_from_yaml(config_file)
            result = runner.run_scraper_sync(config)
            results.append(result)
            logging.info(f"Completed scraping: {config.meta.name}")
        except Exception as e:
            logging.error(f"Failed to run {config_file}: {e}")

    # Check for arbitrage opportunities
    # (Implementation would go here)

    return results

# Schedule scrapers to run every 15 minutes
schedule.every(15).minutes.do(run_scheduled_scraping)

# Schedule database cleanup every hour
schedule.every().hour.do(lambda: logging.info("Database cleanup scheduled"))

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.info("Starting continuous monitoring...")

    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute
'''

    with open('monitoring_example.py', 'w') as f:
        f.write(monitoring_script)

    print("✓ Created monitoring_example.py")


async def main():
    """Main example execution."""
    print("🚀 Arbitrage Betting Scraper - Comprehensive Example")
    print("=" * 60)

    # Setup environment
    setup_example_environment()

    # Setup database (optional)
    db_available = setup_test_database()

    # Create custom processors
    create_custom_processor()

    # Create example configurations
    config_files = create_example_configs()

    # Create monitoring example
    create_monitoring_example()

    print(f"\n📋 Example Overview:")
    print(f"  • {len(config_files)} example configurations created")
    print(f"  • Database: {'✓ Available' if db_available else '⚠ Not available'}")
    print(f"  • Custom processors: ✓ Registered")
    print(f"  • Monitoring example: ✓ Created")

    # Run examples (with user confirmation for real sites)
    print(f"\n⚠  Note: These examples use fictional websites.")
    print(f"   Real scraping requires updating URLs and selectors.")

    if input("\nRun example scrapers with mock data? (y/N): ").lower().startswith('y'):
        results = []

        # Run each example scraper
        for config_file in config_files:
            try:
                result = await run_example_scraper(
                    config_file,
                    f"Example scraper from {Path(config_file).name}"
                )
                results.append(result)
            except Exception as e:
                print(f"Example failed: {e}")
                results.append(None)

        # Demonstrate arbitrage detection
        demonstrate_arbitrage_detection(results)

    print(f"\n✅ Example complete!")
    print(f"\nNext steps:")
    print(f"  1. Update configuration files with real URLs and selectors")
    print(f"  2. Set up database connection (see database/config.py)")
    print(f"  3. Test individual scrapers: python -m scraper.cli run configs/static_example.yml")
    print(f"  4. Set up monitoring: python monitoring_example.py")
    print(f"  5. Implement arbitrage alerts and betting logic")


def sync_main():
    """Synchronous wrapper for main."""
    asyncio.run(main())


if __name__ == "__main__":
    sync_main()