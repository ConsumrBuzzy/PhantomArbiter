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

## 3. New Components (Delivered)
- `target_handler.py` (`src/etl/target_handler.py`): Centralized target management with SQLite.
- `targets.db`: Schema defined in handler, auto-initialized on first run.

## 4. Verification Scripts
- `verify_batch_01.py`: Dry-run validator for yield estimation logic (Mock Data).

