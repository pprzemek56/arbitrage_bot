#!/usr/bin/env python3
"""
Final setup script for environment-based Polymarket scraper.
No more URL passing - everything uses environment variables.
"""

import os
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def check_environment_variables():
    """Check if all required environment variables are set."""
    print("🔍 Checking environment variables...")

    required_vars = {
        'DB_HOST': os.getenv('DB_HOST'),
        'DB_PORT': os.getenv('DB_PORT'),
        'DB_NAME': os.getenv('DB_NAME'),
        'DB_USER': os.getenv('DB_USER'),
        'DB_PASSWORD': os.getenv('DB_PASSWORD')
    }

    missing_vars = []

    for var_name, var_value in required_vars.items():
        if var_value:
            print(f"  ✅ {var_name}: {var_value if var_name != 'DB_PASSWORD' else '***'}")
        else:
            missing_vars.append(var_name)
            print(f"  ❌ {var_name}: NOT SET")

    if missing_vars:
        print(f"\n⚠ Missing environment variables: {', '.join(missing_vars)}")
        print("Please set them in your .env file or export them:")
        for var in missing_vars:
            print(f"export {var}=your_value_here")
        return False

    print("✅ All required environment variables are set")
    return True


def load_environment():
    """Load environment variables from .env file."""
    print("\n📂 Loading environment variables...")

    try:
        from dotenv import load_dotenv

        env_file = Path('.env')
        if env_file.exists():
            load_dotenv(env_file)
            print(f"  ✅ Loaded {env_file}")
            return True
        else:
            print(f"  ⚠ .env file not found. Creating template...")

            env_content = """# Database Configuration for Arbitrage Bot
DB_HOST=localhost
DB_PORT=5432
DB_NAME=arbitrage_bot_db
DB_USER=postgres
DB_PASSWORD=1qazZAQ!

# Optional: Redis for background tasks
REDIS_URL=redis://localhost:6379/0

# Logging
LOG_LEVEL=INFO
"""

            with open(env_file, 'w') as f:
                f.write(env_content)

            print(f"  📝 Created {env_file} with your current settings")
            print(f"  ⚠ Please verify the credentials are correct")

            # Load the newly created file
            load_dotenv(env_file)
            return True

    except ImportError:
        print("  ❌ python-dotenv not installed. Install with: pip install python-dotenv")
        return False
    except Exception as e:
        print(f"  ❌ Error loading environment: {e}")
        return False


def test_database_connection():
    """Test database connection using environment variables."""
    print("\n🗄️ Testing database connection...")

    try:
        from database.config import DatabaseConfig

        config = DatabaseConfig()

        print(f"  📍 Connecting to: {config}")

        if config.test_connection():
            print("  ✅ Database connection successful!")
            return True
        else:
            print("  ❌ Database connection failed")
            print("  💡 Try running the database test script: python database_test.py")
            return False

    except Exception as e:
        print(f"  ❌ Database connection error: {e}")
        print("  💡 Make sure python-dotenv and psycopg2-binary are installed")
        return False


def initialize_database():
    """Initialize database tables."""
    print("\n🏗️ Initializing database...")

    try:
        from database.config import initialize_database

        db_manager = initialize_database()
        db_manager.create_tables()

        print("  ✅ Database tables created successfully")
        return True

    except Exception as e:
        print(f"  ❌ Database initialization failed: {e}")
        return False


def register_processors():
    """Register Polymarket processors."""
    print("\n⚙️ Registering Polymarket processors...")

    try:
        # Try to import and register custom processors
        try:
            from scraper.polymarket_processors import register_polymarket_processors
            register_polymarket_processors()
            print("  ✅ Polymarket custom processors registered")
        except ImportError:
            print("  ℹ Custom Polymarket processors not found, using basic processors")

        return True

    except Exception as e:
        print(f"  ❌ Error registering processors: {e}")
        return False


def test_scraper_configuration():
    """Test the scraper configuration."""
    print("\n🧪 Testing scraper configuration...")

    try:
        from scraper.config_schema import ConfigLoader

        config_path = "configs/polymarket_comprehensive.yml"

        if not Path(config_path).exists():
            print(f"  ❌ Config file not found: {config_path}")
            return False

        config = ConfigLoader.load_from_yaml(config_path)
        print(f"  ✅ Configuration loaded: {config.meta.name}")
        print(f"  📋 Fetcher: {config.fetcher.type}")
        print(f"  🏪 Bookmaker: {config.database.bookmaker_name}")
        print(f"  📊 Category: {config.database.category_name}")
        print(f"  🔧 Instructions: {len(config.instructions)}")

        return True

    except Exception as e:
        print(f"  ❌ Configuration error: {e}")
        return False


def run_test_scraper():
    """Run a quick test of the scraper."""
    print("\n🚀 Running test scraper...")

    try:
        from scraper.scraper_pipeline import ScraperRunner
        from scraper.config_schema import ConfigLoader

        # Load config
        config = ConfigLoader.load_from_yaml("configs/polymarket_comprehensive.yml")

        # Limit to 3 items for quick test
        for instruction in config.instructions:
            if hasattr(instruction, 'limit'):
                instruction.limit = 3

        # Run scraper
        runner = ScraperRunner()
        result = runner.run_scraper_sync(config)

        # Display results
        print(f"  📊 Results:")
        print(f"    Events: {len(result.events)}")
        print(f"    Errors: {len(result.errors)}")
        print(f"    Duration: {result.metadata.get('duration_seconds', 0):.2f}s")

        if result.errors:
            print(f"  ❌ Errors:")
            for error in result.errors:
                print(f"    - {error}")
            return False

        if result.events:
            print(f"  ✅ Successfully scraped {len(result.events)} markets")
            sample = result.events[0]
            question = sample.get('question', 'N/A')
            print(f"  📝 Sample market: {question[:60]}...")
            return True
        else:
            print(f"  ⚠ No events scraped")
            return False

    except Exception as e:
        print(f"  ❌ Test scraper error: {e}")
        return False


def show_usage():
    """Show usage instructions."""
    print("\n📖 Usage Instructions:")
    print("=" * 50)

    print("\n✅ Your scraper is ready! Here's how to use it:")

    print("\n1. 🏃‍♂️ Run the Polymarket scraper:")
    print("   python -m scraper.cli run configs/polymarket_comprehensive.yml")

    print("\n2. 📊 Save results to file:")
    print("   python -m scraper.cli run configs/polymarket_comprehensive.yml --output polymarket_data.json")

    print("\n3. 🧪 Validate configuration:")
    print("   python -m scraper.cli validate configs/polymarket_comprehensive.yml")

    print("\n4. 📚 List available processors:")
    print("   python -m scraper.cli list-processors")

    print("\n5. 🗄️ Database management:")
    print("   python db_init.py info          # Show database info")
    print("   python db_init.py recreate      # Reset database tables")

    print("\n💡 Tips:")
    print("   - All database credentials come from .env file")
    print("   - No need to specify database URLs in configs anymore")
    print("   - Check logs/ directory for detailed output")
    print("   - Use --dry-run to test configs without running")


def main():
    """Main setup function."""
    print("🎯 Polymarket Arbitrage Bot - Environment Setup")
    print("=" * 50)

    success_count = 0
    total_steps = 6

    # Step 1: Load environment
    if load_environment():
        success_count += 1

    # Step 2: Check environment variables
    if check_environment_variables():
        success_count += 1

    # Step 3: Test database connection
    if test_database_connection():
        success_count += 1

        # Step 4: Initialize database
        if initialize_database():
            success_count += 1

    # Step 5: Register processors
    if register_processors():
        success_count += 1

    # Step 6: Test configuration
    if test_scraper_configuration():
        success_count += 1

    # Summary
    print(f"\n📊 Setup Summary: {success_count}/{total_steps} steps completed")

    if success_count == total_steps:
        print("🎉 Setup completed successfully!")

        # Run quick test
        test_success = run_test_scraper()
        if test_success:
            print("\n✅ Test scraper run successful!")
            show_usage()
        else:
            print("\n⚠ Test scraper had issues - check the errors above")
    else:
        print("⚠ Setup incomplete - please resolve the issues above")

        if success_count < 3:
            print("\n💡 Most common issues:")
            print("   1. Make sure PostgreSQL is running: sudo systemctl start postgresql")
            print("   2. Check .env file has correct database credentials")
            print("   3. Create database if it doesn't exist:")
            print("      sudo -u postgres createdb arbitrage_bot_db")
            print("      sudo -u postgres psql -c \"GRANT ALL PRIVILEGES ON DATABASE arbitrage_bot_db TO postgres;\"")


if __name__ == "__main__":
    main()