# Implementation Plan: Database Hydration System

## Overview

This plan implements a JSON-based database hydration/dehydration system for portable SQLite persistence across development stations. The system is already implemented; this task list focuses on testing, validation, and documentation.

## Tasks

- [x] 1. Core Hydration Manager Implementation
  - Core `DBHydrationManager` class created in `src/shared/system/db_hydration.py`
  - Dehydration pipeline (DB → JSON) implemented
  - Hydration pipeline (JSON → DB) implemented
  - Corruption detection and repair implemented
  - _Requirements: 1.1, 1.2, 2.1, 2.2, 3.1, 3.2_

- [x] 2. CLI Interface Implementation
  - Command-line interface with dehydrate/hydrate/fix/stats commands
  - Usage instructions and error handling
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 3. Application Integration
  - [x] 3.1 Integrate hydration check into DatabaseCore startup
    - Added `_check_and_hydrate()` method to `src/shared/system/database/core.py`
    - Automatic corruption detection and repair on startup
    - _Requirements: 3.1, 3.2, 3.3, 4.1, 4.2, 4.3, 4.4_
  
  - [x] 3.2 Add auto-hydration to application startup
    - Integrated into `run_dashboard.py` main() function
    - Logs hydration status on startup
    - _Requirements: 4.1, 4.2, 4.3, 4.5_
  
  - [x] 3.3 Add auto-dehydration to graceful shutdown
    - Integrated into `run_dashboard.py` finally block
    - Dehydrates all databases before exit
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 4. Git Configuration
  - [x] 4.1 Update .gitignore for database files
    - Exclude `*.db`, `*.db-journal`, `*.db-shm`, `*.db-wal`, `*.db.backup_*`
    - Include `data/json_archives/*.json` files
    - _Requirements: 8.1, 8.2, 8.3, 8.4_
  
  - [x] 4.2 Create .keep file for json_archives directory
    - Ensures directory is tracked in Git
    - _Requirements: 8.5_

- [ ] 5. Property-Based Testing
  - [x] 5.1 Write property test for round-trip consistency
    - **Property 1: Round-trip Consistency**
    - **Validates: Requirements 1.2, 2.3, 10.5**
    - Generate random databases, dehydrate, hydrate, verify data matches
  
  - [x] 5.2 Write property test for idempotent dehydration
    - **Property 2: Idempotent Dehydration**
    - **Validates: Requirements 1.1, 1.4**
    - Dehydrate same database twice, verify JSON is identical (excluding timestamps)
  
  - [x] 5.3 Write property test for idempotent hydration
    - **Property 3: Idempotent Hydration**
    - **Validates: Requirements 2.1, 2.4**
    - Hydrate same archive twice with force, verify databases are identical
  
  - [x] 5.4 Write property test for corruption detection
    - **Property 4: Corruption Detection Accuracy**
    - **Validates: Requirements 3.1, 3.2**
    - Generate valid and corrupted files, verify detection accuracy
  
  - [-] 5.5 Write property test for partial failure isolation
    - **Property 5: Partial Failure Isolation**
    - **Validates: Requirements 9.1, 9.2**
    - Mix valid and corrupted databases, verify valid ones are processed
  
  - [ ] 5.6 Write property test for archive completeness
    - **Property 6: Archive Completeness**
    - **Validates: Requirements 1.2, 10.1**
    - Verify all tables and rows are captured in JSON
  
  - [ ] 5.7 Write property test for schema preservation
    - **Property 7: Schema Preservation**
    - **Validates: Requirements 1.2, 10.3**
    - Verify schema SQL in archive creates identical table structure
  
  - [ ] 5.8 Write property test for data type preservation
    - **Property 8: Data Type Preservation**
    - **Validates: Requirements 10.1, 10.2**
    - Test various data types (int, float, string, NULL, binary)
  
  - [ ] 5.9 Write property test for backup safety
    - **Property 9: Backup Safety**
    - **Validates: Requirements 2.4**
    - Verify backup files are created before hydration with force flag
  
  - [ ] 5.10 Write property test for error collection
    - **Property 10: Error Collection Completeness**
    - **Validates: Requirements 9.5**
    - Generate multiple errors, verify all are collected in results

- [ ] 6. Unit Testing
  - [ ] 6.1 Write unit tests for database validation
    - Test `_is_db_valid()` with valid and corrupted files
    - Test with missing files, locked files, empty files
    - _Requirements: 3.1_
  
  - [ ] 6.2 Write unit tests for JSON serialization
    - Test handling of various data types
    - Test handling of NULL values
    - Test handling of special characters
    - _Requirements: 10.1_
  
  - [ ] 6.3 Write unit tests for path handling
    - Test archive directory creation
    - Test path validation
    - Test cross-platform compatibility
    - _Requirements: 1.5_
  
  - [ ] 6.4 Write unit tests for error handling
    - Test graceful degradation on failures
    - Test error message formatting
    - Test error collection
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_
  
  - [ ] 6.5 Write unit tests for CLI interface
    - Test command parsing
    - Test invalid command handling
    - Test output formatting
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [ ] 7. Integration Testing
  - [ ] 7.1 Write integration test for full startup cycle
    - Test application startup with missing databases
    - Test application startup with corrupted databases
    - Verify databases are hydrated correctly
    - _Requirements: 4.1, 4.2, 4.3, 4.4_
  
  - [ ] 7.2 Write integration test for full shutdown cycle
    - Test graceful shutdown with dehydration
    - Verify JSON archives are created
    - Verify manifest is updated
    - _Requirements: 5.1, 5.2, 5.3, 5.4_
  
  - [ ] 7.3 Write integration test for CLI workflow
    - Test dehydrate → delete → hydrate sequence
    - Verify data integrity after full cycle
    - _Requirements: 6.1, 6.2_
  
  - [ ] 7.4 Write integration test for concurrent access
    - Test hydration while database is in use
    - Verify proper error handling for locked files
    - _Requirements: 9.4_

- [ ] 8. Edge Case Testing
  - [ ] 8.1 Test empty database handling
    - Database with no tables
    - Database with tables but no rows
    - _Requirements: 1.2, 2.1_
  
  - [ ] 8.2 Test large database handling
    - Database with >10,000 rows
    - Verify performance is acceptable
    - _Requirements: 1.1, 2.1_
  
  - [ ] 8.3 Test special character handling
    - Table/column names with spaces, quotes, unicode
    - Data with special characters
    - _Requirements: 10.1, 10.2_
  
  - [ ] 8.4 Test NULL value handling
    - Rows with NULL values in various columns
    - Verify NULL preservation through round-trip
    - _Requirements: 10.1_
  
  - [ ] 8.5 Test binary data handling
    - BLOB columns with binary data
    - Verify base64 encoding/decoding
    - _Requirements: 10.1_

- [ ] 9. Documentation
  - [ ] 9.1 Create user guide for hydration system
    - Document CLI commands and usage
    - Document automatic startup/shutdown behavior
    - Document troubleshooting steps
  
  - [ ] 9.2 Create developer guide
    - Document architecture and design decisions
    - Document how to add new databases to the system
    - Document testing strategy
  
  - [ ] 9.3 Update README with hydration workflow
    - Add section on database portability
    - Document Git workflow for moving between stations
    - Add troubleshooting section

- [ ] 10. Validation and Cleanup
  - [ ] 10.1 Run full test suite
    - Execute all unit tests
    - Execute all property tests
    - Execute all integration tests
    - Verify 100% pass rate
  
  - [ ] 10.2 Verify Git configuration
    - Confirm database files are ignored
    - Confirm JSON archives are tracked
    - Test clone → hydrate workflow
  
  - [ ] 10.3 Performance validation
    - Measure dehydration time for typical databases
    - Measure hydration time for typical databases
    - Verify acceptable performance (<5 seconds for typical use)
  
  - [ ] 10.4 Code review and cleanup
    - Review all code for SOLID principles
    - Add missing docstrings
    - Remove debug logging
    - Verify error messages are user-friendly

## Notes

- Tasks 1-4 are already complete (marked with [x])
- Tasks 5-10 focus on comprehensive testing and validation
- Property tests should use `hypothesis` library with minimum 100 iterations
- All tests should include requirement traceability comments
- Integration tests may require test fixtures for database creation
- Edge case tests should cover all scenarios from design document
