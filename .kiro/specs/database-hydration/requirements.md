# Requirements Document: Database Hydration System

## Introduction

The Database Hydration System provides portable JSON-based persistence for SQLite databases, solving the problem of large/corrupted database files in Git by enabling seamless migration between development stations through JSON archives.

## Glossary

- **Hydration**: The process of importing database data from JSON archives into SQLite database files
- **Dehydration**: The process of exporting database data from SQLite files into JSON archives
- **Archive**: A JSON file containing the complete schema and data for a database
- **Station**: A development machine or environment where the project is deployed
- **DBHydrationManager**: The core system component that manages hydration/dehydration operations
- **Manifest**: A JSON file containing metadata about all archived databases

## Requirements

### Requirement 1: JSON Archive Export (Dehydration)

**User Story:** As a developer, I want to export all database data to JSON archives, so that I can commit portable database snapshots to Git.

#### Acceptance Criteria

1. WHEN a developer runs the dehydrate command, THE System SHALL export all configured databases to JSON files
2. WHEN exporting a database, THE System SHALL capture both table schemas and row data
3. WHEN a table export fails, THE System SHALL log the error and continue with remaining tables
4. WHEN dehydration completes, THE System SHALL create a manifest file with export metadata
5. THE System SHALL store JSON archives in the `data/json_archives/` directory

### Requirement 2: JSON Archive Import (Hydration)

**User Story:** As a developer, I want to import database data from JSON archives, so that I can restore databases at a new station or after corruption.

#### Acceptance Criteria

1. WHEN a developer runs the hydrate command, THE System SHALL import all available JSON archives to database files
2. WHEN a database already exists and is valid, THE System SHALL skip hydration unless force flag is set
3. WHEN a database is corrupted, THE System SHALL automatically recreate it from JSON archive
4. WHEN hydrating a database, THE System SHALL backup the existing file before replacement
5. WHEN no JSON archive exists for a database, THE System SHALL skip it and log a debug message

### Requirement 3: Corrupted Database Detection and Repair

**User Story:** As a developer, I want the system to automatically detect and fix corrupted databases, so that I don't encounter "file is not a database" errors.

#### Acceptance Criteria

1. WHEN the system starts, THE DatabaseCore SHALL check if the database file is valid
2. IF a database is corrupted, THEN THE System SHALL attempt to restore it from JSON archive
3. IF no JSON archive exists for a corrupted database, THEN THE System SHALL remove the corrupted file and allow fresh creation
4. WHEN running the fix command, THE System SHALL scan all configured databases for corruption
5. WHEN a database is successfully repaired, THE System SHALL log a success message

### Requirement 4: Automatic Startup Hydration

**User Story:** As a developer, I want databases to be automatically hydrated on application startup, so that I don't need to manually run hydration commands.

#### Acceptance Criteria

1. WHEN the application starts, THE System SHALL check for missing or corrupted databases
2. WHEN a database is missing, THE System SHALL hydrate it from JSON archive if available
3. WHEN hydration fails, THE System SHALL log a warning and continue with normal initialization
4. THE System SHALL complete hydration before initializing database connections
5. THE System SHALL log hydration status (skipped/imported/failed) for each database

### Requirement 5: Automatic Shutdown Dehydration

**User Story:** As a developer, I want databases to be automatically dehydrated on graceful shutdown, so that JSON archives are always up-to-date.

#### Acceptance Criteria

1. WHEN the application shuts down gracefully, THE System SHALL dehydrate all databases to JSON
2. WHEN dehydration fails, THE System SHALL log a warning but not prevent shutdown
3. THE System SHALL complete dehydration before closing database connections
4. THE System SHALL update the manifest file with dehydration timestamp and statistics
5. WHEN a database file doesn't exist, THE System SHALL skip it and log a debug message

### Requirement 6: CLI Interface

**User Story:** As a developer, I want command-line tools for manual hydration/dehydration, so that I can manage archives independently of the application.

#### Acceptance Criteria

1. WHEN running `python -m src.shared.system.db_hydration dehydrate`, THE System SHALL export all databases
2. WHEN running `python -m src.shared.system.db_hydration hydrate`, THE System SHALL import all archives
3. WHEN running `python -m src.shared.system.db_hydration fix`, THE System SHALL repair corrupted databases
4. WHEN running `python -m src.shared.system.db_hydration stats`, THE System SHALL display archive statistics
5. WHEN an invalid command is provided, THE System SHALL display usage instructions

### Requirement 7: Archive Statistics and Monitoring

**User Story:** As a developer, I want to view statistics about JSON archives, so that I can monitor archive size and data volume.

#### Acceptance Criteria

1. WHEN requesting archive statistics, THE System SHALL display database name, table count, and row count
2. WHEN displaying statistics, THE System SHALL show file size in megabytes
3. WHEN displaying statistics, THE System SHALL show the export timestamp
4. WHEN an archive doesn't exist, THE System SHALL skip it in the statistics output
5. THE System SHALL format statistics in a human-readable table format

### Requirement 8: Git Integration

**User Story:** As a developer, I want JSON archives tracked in Git while database files are ignored, so that I can share database state across stations without large binary files.

#### Acceptance Criteria

1. THE .gitignore file SHALL exclude all `*.db` files from version control
2. THE .gitignore file SHALL exclude all `*.db-journal`, `*.db-shm`, and `*.db-wal` files
3. THE .gitignore file SHALL exclude all `*.db.backup_*` files
4. THE .gitignore file SHALL include `data/json_archives/*.json` files in version control
5. THE System SHALL maintain a `.keep` file in the `data/json_archives/` directory

### Requirement 9: Error Handling and Resilience

**User Story:** As a developer, I want the hydration system to handle errors gracefully, so that one failure doesn't prevent other operations from completing.

#### Acceptance Criteria

1. WHEN a table export fails, THE System SHALL continue exporting remaining tables
2. WHEN a database hydration fails, THE System SHALL continue with remaining databases
3. WHEN a JSON file is malformed, THE System SHALL log an error and skip that archive
4. WHEN a database is locked by another process, THE System SHALL log a warning and skip it
5. THE System SHALL collect all errors and include them in operation results

### Requirement 10: Data Integrity and Validation

**User Story:** As a developer, I want to ensure data integrity during hydration/dehydration, so that no data is lost or corrupted during the process.

#### Acceptance Criteria

1. WHEN exporting data, THE System SHALL use JSON serialization with default string conversion for non-serializable types
2. WHEN importing data, THE System SHALL validate that all columns from JSON match the table schema
3. WHEN creating tables, THE System SHALL execute the exact schema SQL from the archive
4. WHEN inserting rows, THE System SHALL use parameterized queries to prevent SQL injection
5. WHEN hydration completes, THE System SHALL commit all changes atomically per database
