# Skimmer Component Inventory

## Existing Scrapers & Extractors
List of identified scraping components in the codebase.

### 1. Web Scrapers
- **Legacy Scraper** (`src/scrapers/legacy_scraper.py`): Basic BeautifulSoup implementation for static pages.
- **Headless Browser** (`src/scrapers/headless.ts`): Puppeteer-based scraper for dynamic content.

### 2. ETL Pipelines
- **Raw Data Processor** (`src/etl/processor.py`): Cleans and normalizes raw scraped text.
- **Entity Extractor** (`src/etl/extractor.py`): Uses regex to identify phone numbers and emails.

## Infrastructure
- **Queue System**: Redis-based job queue for distributing scraping tasks.
- **Proxy Rotator**: Simple round-robin proxy management.
- **Storage**: PostgreSQL database for structured target data.

## Missing Components (To Be Built)
- `target_handler.py`: Centralized target management logic.
- `targets.db`: SQLite schema for local target caching.
- Advanced retry policies for rate-limited sites.
