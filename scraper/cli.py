#!/usr/bin/env python3
"""
Command-line interface for the arbitrage betting scraper.
Provides a comprehensive CLI for running scrapers and managing configurations.
"""

import asyncio
import sys
import json
import logging
from pathlib import Path
from typing import Optional, List
import argparse
from datetime import datetime

import click
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.json import JSON
from rich import print as rprint

from scraper.config_schema import ConfigLoader, ScraperConfig
from scraper.scraper_pipeline import ScraperRunner, ScrapingResult
from scraper.processor_registry import processor_registry
from scraper.fetcher_strategies import FetcherFactory
from database.config import initialize_database, DatabaseConfig

console = Console()


class CLIError(Exception):
    """CLI-specific error."""
    pass


def setup_logging(verbose: bool = False, log_file: Optional[str] = None):
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO

    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    # File handler
    handlers = [console_handler]
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    # Configure root logger
    logging.basicConfig(
        level=level,
        handlers=handlers,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


@click.group()
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
@click.option('--log-file', help='Log file path')
@click.pass_context
def cli(ctx, verbose, log_file):
    """Arbitrage Betting Scraper CLI"""
    ctx.ensure_object(dict)
    ctx.obj['verbose'] = verbose
    setup_logging(verbose, log_file)


@cli.command()
@click.argument('config_file', type=click.Path(exists=True, dir_okay=False))
@click.option('--dry-run', is_flag=True, help='Validate config without running')
@click.option('--output', '-o', help='Output file for results (JSON)')
@click.option('--no-database', is_flag=True, help='Skip database persistence')
@click.pass_context
def run(ctx, config_file, dry_run, output, no_database):
    """Run a scraper with the specified configuration file."""
    try:
        console.print(f"[blue]Loading configuration from:[/blue] {config_file}")

        # Load and validate configuration
        config = ConfigLoader.load_from_yaml(config_file)
        console.print("[green]✓[/green] Configuration loaded successfully")

        if dry_run:
            console.print("[yellow]Dry run mode - configuration is valid[/yellow]")
            _display_config_summary(config)
            return

        # Initialize database if needed
        if not no_database:
            console.print("[blue]Initializing database...[/blue]")
            try:
                db_config = DatabaseConfig.from_env()
                initialize_database(db_config)
                console.print("[green]✓[/green] Database initialized")
            except Exception as e:
                console.print(f"[red]✗[/red] Database initialization failed: {e}")
                if not click.confirm("Continue without database?"):
                    raise CLIError("Database required but initialization failed")
                no_database = True

        # Run scraper
        console.print(f"[blue]Starting scraper:[/blue] {config.meta.name}")

        with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
        ) as progress:
            task = progress.add_task("Running scraper...", total=None)

            # Run the scraper
            runner = ScraperRunner()
            result = runner.run_scraper_sync(config)

        # Display results
        _display_results(result)

        # Save output if requested
        if output:
            _save_results(result, output)
            console.print(f"[green]Results saved to:[/green] {output}")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        if ctx.obj['verbose']:
            console.print_exception()
        sys.exit(1)


@cli.command()
@click.argument('config_file', type=click.Path(exists=True, dir_okay=False))
def validate(config_file):
    """Validate a configuration file."""
    try:
        console.print(f"[blue]Validating configuration:[/blue] {config_file}")

        config = ConfigLoader.load_from_yaml(config_file)
        console.print("[green]✓[/green] Configuration is valid")

        _display_config_summary(config)

    except Exception as e:
        console.print(f"[red]✗[/red] Configuration is invalid: {e}")
        sys.exit(1)


@cli.command()
@click.option('--name', help='Scraper name')
@click.option('--url', help='Start URL')
@click.option('--fetcher', type=click.Choice(['static', 'browser', 'api', 'interactive']),
              default='browser', help='Fetcher type')
@click.option('--bookmaker', help='Bookmaker name')
@click.option('--category', default='General', help='Event category')
@click.option('--output', '-o', required=True, help='Output config file')
def create(name, url, fetcher, bookmaker, category, output):
    """Create a new configuration file template."""
    if not name:
        name = click.prompt('Scraper name')
    if not url:
        url = click.prompt('Start URL')
    if not bookmaker:
        bookmaker = click.prompt('Bookmaker name')

    # Create basic configuration template
    config_template = {
        'meta': {
            'name': name,
            'description': f'Scraper for {bookmaker}',
            'start_url': url,
            'allowed_domains': [_extract_domain(url)]
        },
        'fetcher': {
            'type': fetcher,
            'headless': True,
            'timeout_ms': 30000
        },
        'database': {
            'url': 'postgresql://postgres:password@localhost:5432/arbitrage_bot',
            'bookmaker_name': bookmaker,
            'category_name': category
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
                'name': 'events',
                'container_selector': 'body',
                'item_selector': '.event-item',
                'fields': {
                    'name': {
                        'selector': '.event-name',
                        'attribute': 'text',
                        'processors': ['trim']
                    },
                    'odds': {
                        'selector': '.odds-value',
                        'attribute': 'text',
                        'processors': ['trim', 'odds']
                    }
                }
            }
        ]
    }

    # Save template
    import yaml
    with open(output, 'w') as f:
        yaml.dump(config_template, f, default_flow_style=False, indent=2)

    console.print(f"[green]✓[/green] Configuration template created: {output}")
    console.print("[yellow]Note:[/yellow] Please edit the selectors and fields to match the target website")


@cli.command()
def list_processors():
    """List all available field processors."""
    processors = processor_registry.list_processors()

    table = Table(title="Available Field Processors")
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="white")

    processor_descriptions = {
        'trim': 'Remove leading/trailing whitespace',
        'uppercase': 'Convert to uppercase',
        'lowercase': 'Convert to lowercase',
        'regex': 'Apply regex transformation',
        'replace': 'Replace text',
        'strip_html': 'Remove HTML tags',
        'absolute_url': 'Convert relative URLs to absolute',
        'number': 'Extract and format numbers',
        'date': 'Parse and format dates',
        'clean_text': 'Clean and normalize text',
        'split': 'Split text and extract parts',
        'odds': 'Process betting odds',
        'bookmaker_name': 'Normalize bookmaker names'
    }

    for processor in sorted(processors):
        description = processor_descriptions.get(processor, 'Custom processor')
        table.add_row(processor, description)

    console.print(table)


@cli.command()
def list_fetchers():
    """List all available fetcher types."""
    fetchers = FetcherFactory.get_supported_types()

    table = Table(title="Available Fetcher Types")
    table.add_column("Type", style="cyan")
    table.add_column("Description", style="white")
    table.add_column("Use Case", style="green")

    fetcher_info = {
        'static': ('Static HTTP requests', 'Simple HTML pages without JavaScript'),
        'browser': ('Browser automation', 'Pages with JavaScript that need rendering'),
        'api': ('API requests', 'RESTful APIs with JSON responses'),
        'interactive': ('Interactive browser', 'Complex user interactions and multi-step flows')
    }

    for fetcher in fetchers:
        info = fetcher_info.get(fetcher.value, ('Unknown', 'Unknown'))
        table.add_row(fetcher.value, info[0], info[1])

    console.print(table)


@cli.command()
@click.argument('directory', type=click.Path(exists=True, file_okay=False), default='.')
def discover(directory):
    """Discover configuration files in a directory."""
    config_dir = Path(directory)
    config_files = list(config_dir.glob('**/*.yml')) + list(config_dir.glob('**/*.yaml'))

    if not config_files:
        console.print(f"[yellow]No configuration files found in {directory}[/yellow]")
        return

    table = Table(title=f"Configuration Files in {directory}")
    table.add_column("File", style="cyan")
    table.add_column("Scraper Name", style="white")
    table.add_column("Fetcher Type", style="green")
    table.add_column("Status", style="blue")

    for config_file in config_files:
        try:
            config = ConfigLoader.load_from_yaml(str(config_file))
            status = "[green]✓ Valid[/green]"
            name = config.meta.name
            fetcher_type = config.fetcher.type.value
        except Exception as e:
            status = f"[red]✗ Invalid[/red]"
            name = "Unknown"
            fetcher_type = "Unknown"

        table.add_row(
            str(config_file.relative_to(config_dir)),
            name,
            fetcher_type,
            status
        )

    console.print(table)


@cli.command()
@click.option('--config-dir', default='configs', help='Directory containing config files')
@click.option('--parallel', '-p', type=int, default=1, help='Number of parallel scrapers')
@click.option('--output-dir', default='results', help='Output directory for results')
def batch(config_dir, parallel, output_dir):
    """Run multiple scrapers in batch mode."""
    config_path = Path(config_dir)
    output_path = Path(output_dir)

    if not config_path.exists():
        console.print(f"[red]Configuration directory not found:[/red] {config_dir}")
        sys.exit(1)

    # Create output directory
    output_path.mkdir(exist_ok=True)

    # Find all config files
    config_files = list(config_path.glob('*.yml')) + list(config_path.glob('*.yaml'))

    if not config_files:
        console.print(f"[yellow]No configuration files found in {config_dir}[/yellow]")
        return

    console.print(f"[blue]Found {len(config_files)} configuration files[/blue]")

    # Run scrapers
    with Progress(console=console) as progress:
        task = progress.add_task("Running batch scrapers...", total=len(config_files))

        # For now, run sequentially (parallel execution would need asyncio coordination)
        for config_file in config_files:
            try:
                progress.update(task, description=f"Running {config_file.name}...")

                # Load config
                config = ConfigLoader.load_from_yaml(str(config_file))

                # Run scraper
                runner = ScraperRunner()
                result = runner.run_scraper_sync(config)

                # Save results
                result_file = output_path / f"{config_file.stem}_result.json"
                _save_results(result, str(result_file))

                console.print(f"[green]✓[/green] {config_file.name} completed")

            except Exception as e:
                console.print(f"[red]✗[/red] {config_file.name} failed: {e}")

            progress.advance(task)

    console.print(f"[blue]Batch processing complete. Results saved to {output_dir}[/blue]")


def _display_config_summary(config: ScraperConfig):
    """Display a summary of the configuration."""
    panel_content = f"""
[bold]Scraper:[/bold] {config.meta.name}
[bold]URL:[/bold] {config.meta.start_url}
[bold]Fetcher:[/bold] {config.fetcher.type.value}
[bold]Bookmaker:[/bold] {config.database.bookmaker_name}
[bold]Category:[/bold] {config.database.category_name}
[bold]Instructions:[/bold] {len(config.instructions)}
[bold]Collections:[/bold] {len(config.collections)}
"""

    console.print(Panel(panel_content, title="Configuration Summary"))


def _display_results(result: ScrapingResult):
    """Display scraping results in a nice format."""
    # Summary panel
    duration = result.metadata.get('duration_seconds', 0)

    summary_content = f"""
[bold]Events:[/bold] {len(result.events)}
[bold]Markets:[/bold] {len(result.markets)}
[bold]Selections:[/bold] {len(result.selections)}
[bold]Errors:[/bold] {len(result.errors)}
[bold]Duration:[/bold] {duration:.2f}s
"""

    console.print(Panel(summary_content, title="Scraping Results"))

    # Error details if any
    if result.errors:
        console.print("\n[bold red]Errors:[/bold red]")
        for error in result.errors:
            console.print(f"  • {error}")

    # Sample data if available
    if result.events:
        console.print("\n[bold]Sample Events:[/bold]")
        table = Table()

        # Get columns from first event
        sample_event = result.events[0]
        for key in sample_event.keys():
            table.add_column(key.title(), style="cyan")

        # Add first few events
        for event in result.events[:5]:
            row = [str(event.get(key, '')) for key in sample_event.keys()]
            table.add_row(*row)

        console.print(table)

        if len(result.events) > 5:
            console.print(f"... and {len(result.events) - 5} more events")


def _save_results(result: ScrapingResult, output_file: str):
    """Save results to a JSON file."""
    output_data = {
        'metadata': result.metadata,
        'events': result.events,
        'markets': result.markets,
        'selections': result.selections,
        'errors': result.errors,
        'start_time': result.start_time.isoformat(),
        'end_time': result.end_time.isoformat() if result.end_time else None
    }

    with open(output_file, 'w') as f:
        json.dump(output_data, f, indent=2, default=str)


def _extract_domain(url: str) -> str:
    """Extract domain from URL."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return parsed.netloc


if __name__ == '__main__':
    cli()