# Design Document: Database Hydration System

## Overview

The Database Hydration System is a JSON-based persistence layer that enables portable database migration across development stations. It solves the problem of large SQLite files in Git by providing automatic export/import functionality with corruption detection and repair.

## Architecture

### Component Structure

```
DBHydrationManager (Core)
├── Dehydration Pipeline (DB → JSON)
│   ├── Database Scanner
│   ├── Schema Extractor
│   ├── Data Exporter
│   └── Manifest Generator
├── Hydration Pipeline (JSON → DB)
│   ├── Archive Loader
│   ├── Database Creator
│   ├── Schema Applier
│   └── Data Importer
└── Utilities
    ├── Corruption Detector
    ├── Statistics Generator
    └── CLI Interface
```

### Integration Points

1. **DatabaseCore**: Integrates hydration check during initialization (`_check_and_hydrate()`)
2. **Application Startup**: Auto-hydrates missing/corrupted databases in `run_dashboard.py`
3. **Application Shutdown**: Auto-dehydrates databases on graceful exit
4. **CLI**: Standalone module for manual operations

## Components and Interfaces

### DBHydrationManager

**Responsibilities:**
- Manage JSON archive lifecycle (create, read, validate)
- Coordinate dehydration and hydration operations
- Detect and repair corrupted databases
- Generate statistics and manifests

**Public Interface:**
```python
class DBHydrationManager:
    def dehydrate_all() -> Dict[str, Any]
    def hydrate_all(force: bool = False) -> Dict[str, Any]
    def fix_corrupted_dbs() -> Dict[str, Any]
    def get_archive_stats() -> Dict[str, Any]
    
    # Private methods
    def _dehydrate_database(db_path: Path) -> Dict[str, Any]
    def _hydrate_database(db_path: Path, archive_path: Path, force: bool) -> Dict[str, Any]
    def _is_db_valid(db_path: Path) -> bool
```

### Archive Format

**JSON Structure:**
```json
{
  "database": "trading_journal",
  "exported_at": "2025-01-16T12:00:00",
  "tables": {
    "trades": {
      "schema": "CREATE TABLE trades (...)",
      "row_count": 150,
      "rows": [
        {"id": 1, "symbol": "SOL", ...},
        ...
      ]
    }
  }
}
```

### Manifest Format

**JSON Structure:**
```json
{
  "timestamp": "2025-01-16T12:00:00",
  "databases": {
    "trading_journal.db": {
      "archive_path": "data/json_archives/trading_journal.json",
      "tables_exported": 8,
      "total_rows": 150
    }
  },
  "total_tables": 16,
  "total_rows": 162,
  "errors": []
}
```

## Data Models

### Configuration

```python
DATA_DIR = Path("data")
ARCHIVE_DIR = DATA_DIR / "json_archives"
DB_FILES = [
    "trading_journal.db",
    "arbiter.db",
    "market_data.db"
]
```

### Result Types

```python
DehydrationResult = {
    "timestamp": str,
    "databases": Dict[str, DatabaseResult],
    "total_tables": int,
    "total_rows": int,
    "errors": List[str]
}

DatabaseResult = {
    "archive_path": str,
    "tables_exported": int,
    "total_rows": int
}

HydrationResult = {
    "timestamp": str,
    "databases": Dict[str, DatabaseResult],
    "total_tables": int,
    "total_rows": int,
    "errors": List[str]
}

FixResult = {
    "checked": List[str],
    "corrupted": List[str],
    "fixed": List[str],
    "errors": List[str]
}
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Round-trip Consistency

*For any* valid database with tables and data, dehydrating then hydrating should produce a database with equivalent schema and data.

**Validates: Requirements 1.2, 2.3, 10.5**

### Property 2: Idempotent Dehydration

*For any* database, dehydrating it multiple times without modifications should produce identical JSON archives (excluding timestamps).

**Validates: Requirements 1.1, 1.4**

### Property 3: Idempotent Hydration

*For any* JSON archive, hydrating it multiple times with force flag should produce identical database files.

**Validates: Requirements 2.1, 2.4**

### Property 4: Corruption Detection Accuracy

*For any* database file, the `_is_db_valid()` method should return False if and only if the file cannot be opened as a valid SQLite database.

**Validates: Requirements 3.1, 3.2**

### Property 5: Partial Failure Isolation

*For any* set of databases where some are corrupted, dehydration should successfully export all valid databases and report errors only for corrupted ones.

**Validates: Requirements 9.1, 9.2**

### Property 6: Archive Completeness

*For any* successfully dehydrated database, the JSON archive should contain all tables and all rows that existed in the original database.

**Validates: Requirements 1.2, 10.1**

### Property 7: Schema Preservation

*For any* table in a database, the schema in the JSON archive should be executable SQL that creates an identical table structure.

**Validates: Requirements 1.2, 10.3**

### Property 8: Data Type Preservation

*For any* row in a database, all column values should be preserved during dehydration and hydration (with string conversion for non-JSON-serializable types).

**Validates: Requirements 10.1, 10.2**

### Property 9: Backup Safety

*For any* existing database file, hydration with force flag should create a timestamped backup before replacement.

**Validates: Requirements 2.4**

### Property 10: Error Collection Completeness

*For any* operation that encounters multiple errors, all errors should be collected and included in the result dictionary.

**Validates: Requirements 9.5**

## Error Handling

### Error Categories

1. **File System Errors**
   - Database file locked by another process → Log warning, skip file
   - Permission denied → Log error, add to errors list
   - Disk full → Log error, abort operation

2. **Database Errors**
   - Corrupted database → Attempt hydration from archive
   - Invalid SQL schema → Log error, skip table
   - Constraint violations → Log error, skip row

3. **JSON Errors**
   - Malformed JSON → Log error, skip archive
   - Missing required fields → Log error, skip archive
   - Invalid data types → Log warning, use string conversion

4. **Application Errors**
   - Circular dependency during import → Use lazy imports
   - Missing archive directory → Create automatically
   - No archives found → Log debug message, continue

### Error Recovery Strategies

1. **Graceful Degradation**: Continue processing remaining items when one fails
2. **Automatic Retry**: Not implemented (operations are idempotent, user can retry)
3. **Fallback Behavior**: Create fresh database if no archive exists
4. **User Notification**: Log all errors with appropriate severity levels

## Testing Strategy

### Unit Tests

**Focus Areas:**
- Database validation logic (`_is_db_valid`)
- JSON serialization/deserialization
- Path handling and directory creation
- Error message formatting
- CLI argument parsing

**Example Tests:**
```python
def test_is_db_valid_with_corrupted_file():
    """Test that corrupted files are detected"""
    
def test_is_db_valid_with_valid_file():
    """Test that valid databases pass validation"""
    
def test_archive_directory_creation():
    """Test that archive directory is created if missing"""
```

### Property-Based Tests

**Configuration:**
- Minimum 100 iterations per test
- Use `hypothesis` library for Python
- Tag format: `# Feature: database-hydration, Property N: <description>`

**Test Generators:**
```python
@st.composite
def database_with_tables(draw):
    """Generate a valid SQLite database with random tables and data"""
    num_tables = draw(st.integers(min_value=1, max_value=10))
    tables = []
    for _ in range(num_tables):
        table_name = draw(st.text(alphabet=st.characters(whitelist_categories=('Lu', 'Ll')), min_size=3, max_size=20))
        num_columns = draw(st.integers(min_value=1, max_value=10))
        num_rows = draw(st.integers(min_value=0, max_value=100))
        tables.append((table_name, num_columns, num_rows))
    return tables

@st.composite
def json_archive(draw):
    """Generate a valid JSON archive structure"""
    database_name = draw(st.text(min_size=3, max_size=20))
    num_tables = draw(st.integers(min_value=0, max_value=10))
    return {
        "database": database_name,
        "exported_at": datetime.now().isoformat(),
        "tables": {}
    }
```

**Property Test Examples:**
```python
@given(database_with_tables())
def test_property_round_trip_consistency(db_data):
    """
    Feature: database-hydration, Property 1: Round-trip Consistency
    For any valid database, dehydrate → hydrate should preserve all data
    """
    # Create database with test data
    # Dehydrate to JSON
    # Hydrate from JSON
    # Assert schemas and data match
    
@given(database_with_tables())
def test_property_idempotent_dehydration(db_data):
    """
    Feature: database-hydration, Property 2: Idempotent Dehydration
    For any database, multiple dehydrations should produce identical archives
    """
    # Create database
    # Dehydrate twice
    # Assert JSON files are identical (excluding timestamps)
```

### Integration Tests

**Scenarios:**
1. Full application startup with missing databases
2. Full application startup with corrupted databases
3. Graceful shutdown with dehydration
4. CLI commands in sequence (dehydrate → delete → hydrate)
5. Concurrent database access during hydration

### Edge Cases

1. **Empty Database**: Database with no tables
2. **Large Database**: Database with >10,000 rows
3. **Special Characters**: Table/column names with spaces, quotes, unicode
4. **NULL Values**: Rows with NULL values in various columns
5. **Binary Data**: BLOB columns (should be converted to base64 strings)
6. **Locked Files**: Database locked by another process
7. **Missing Archives**: Hydration when no JSON exists
8. **Partial Archives**: JSON with missing tables or incomplete data

## Implementation Notes

### Performance Considerations

1. **Batch Inserts**: Use executemany() for bulk row insertion
2. **Transaction Management**: Commit once per database, not per table
3. **Memory Usage**: Stream large tables instead of loading all rows into memory
4. **File I/O**: Use buffered writes for JSON files

### Security Considerations

1. **SQL Injection**: Use parameterized queries for all data insertion
2. **Path Traversal**: Validate all file paths are within expected directories
3. **File Permissions**: Ensure archive directory has appropriate permissions
4. **Sensitive Data**: JSON archives may contain sensitive data, handle accordingly

### Compatibility

1. **SQLite Version**: Compatible with SQLite 3.x
2. **Python Version**: Requires Python 3.8+ (for pathlib and type hints)
3. **JSON Format**: Standard JSON (RFC 8259)
4. **Cross-Platform**: Works on Windows, Linux, macOS

### Future Enhancements

1. **Compression**: Add gzip compression for large archives
2. **Encryption**: Add optional encryption for sensitive data
3. **Incremental Backups**: Only export changed tables
4. **Remote Storage**: Support S3/cloud storage for archives
5. **Schema Migrations**: Track and apply schema changes across versions
