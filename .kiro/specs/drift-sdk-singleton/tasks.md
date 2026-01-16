# Implementation Plan: Drift SDK Singleton Manager

## Overview

Implement a singleton pattern for DriftClient management to eliminate RPC rate limiting issues. The implementation will be done in phases to ensure backward compatibility and minimize risk.

## Tasks

- [ ] 1. Create Cache Manager
  - Create `src/shared/drift/cache_manager.py` with CacheEntry and CacheManager classes
  - Implement get(), set(), and is_expired() methods
  - Add thread-safe access with asyncio.Lock
  - _Requirements: 6.1, 6.2, 6.3_

- [ ]* 1.1 Write property test for cache expiration
  - **Property 6: Cache Expiration**
  - **Validates: Requirements 6.3**

- [ ] 2. Create DriftClientManager Singleton
  - Create `src/shared/drift/client_manager.py` with DriftClientManager class
  - Implement singleton pattern with _instance and _lock
  - Add _drift_client, _ref_count, _rpc_client, _wallet state
  - _Requirements: 1.1, 1.2, 3.1_

- [ ] 2.1 Implement get_client() method
  - Add async get_client(network: str) class method
  - Implement lazy initialization on first call
  - Add reference counting (increment _ref_count)
  - Add thread-safe access with _lock
  - _Requirements: 1.2, 1.3, 2.2, 3.2_

- [ ]* 2.2 Write property test for singleton guarantee
  - **Property 1: Singleton Guarantee**
  - **Validates: Requirements 1.1, 1.2**

- [ ] 2.3 Implement release_client() method
  - Add async release_client() class method
  - Decrement _ref_count
  - Cleanup when _ref_count reaches 0
  - Unsubscribe DriftClient and close connections
  - _Requirements: 1.4, 1.5, 2.4_

- [ ]* 2.4 Write property test for reference counting
  - **Property 2: Reference Counting Correctness**
  - **Validates: Requirements 1.5**

- [ ] 2.5 Implement _initialize_client() private method
  - Create RPC client connection
  - Initialize DriftClient with wallet
  - Subscribe to Drift program accounts
  - Implement retry logic with exponential backoff
  - _Requirements: 2.3, 4.3, 5.2_

- [ ] 2.6 Implement _cleanup_client() private method
  - Unsubscribe DriftClient
  - Close RPC connections
  - Reset _drift_client to None
  - Log cleanup actions
  - _Requirements: 1.4, 2.4, 5.3_

- [ ] 3. Implement Market Data Methods with Caching
  - [ ] 3.1 Implement get_funding_rate(market: str) method
    - Check cache first
    - Fetch from DriftClient if cache miss
    - Cache result with 30s TTL
    - Handle KeyError gracefully
    - _Requirements: 6.1, 6.2, 4.2_

- [ ]* 3.2 Write property test for cache consistency
  - **Property 5: Cache Consistency**
  - **Validates: Requirements 6.1, 6.2**

- [ ] 3.3 Implement get_all_perp_markets() method
  - Check cache first
  - Fetch all markets if cache miss
  - Cache result with 60s TTL
  - Return empty list on error
  - _Requirements: 6.1, 6.3_

- [ ] 3.4 Implement is_initialized() method
  - Return True if _drift_client is not None
  - Return False otherwise
  - _Requirements: 8.1_

- [ ] 3.5 Implement force_reconnect() method
  - Call _cleanup_client()
  - Wait 5 seconds
  - Call _initialize_client()
  - Return success status
  - _Requirements: 4.3, 5.2_

- [ ] 4. Update DriftAdapter to Use Singleton
  - [ ] 4.1 Add _using_singleton flag to __init__
    - Set _using_singleton = True by default
    - Keep old code paths for fallback
    - _Requirements: 7.1, 7.3_

- [ ] 4.2 Update connect() method
  - Check _using_singleton flag
  - If True, call DriftClientManager.get_client()
  - If False, use old initialization code
  - Set self.connected based on result
  - _Requirements: 7.1, 7.2_

- [ ] 4.3 Update disconnect() method
  - Check _using_singleton flag
  - If True, call DriftClientManager.release_client()
  - If False, use old cleanup code
  - _Requirements: 7.1, 7.2_

- [ ] 4.4 Update get_funding_rate() method
  - Check _using_singleton flag
  - If True, call DriftClientManager.get_funding_rate()
  - If False, use old implementation
  - _Requirements: 7.1, 7.3, 7.4_

- [ ] 4.5 Update get_all_perp_markets() method
  - Check _using_singleton flag
  - If True, call DriftClientManager.get_all_perp_markets()
  - If False, use old implementation
  - _Requirements: 7.1, 7.3, 7.4_

- [ ]* 4.6 Write property test for backward compatibility
  - **Property 8: Backward Compatibility**
  - **Validates: Requirements 7.1, 7.2, 7.3, 7.4**

- [ ] 5. Add Error Handling and Recovery
  - [ ] 5.1 Implement _handle_rate_limit() method
    - Calculate exponential backoff with jitter
    - Cap maximum delay at 30 seconds
    - Log retry attempts
    - _Requirements: 4.3_

- [ ] 5.2 Implement _is_market_subscribed() helper
  - Check if market_index exists in DriftClient subscriptions
  - Return False if not subscribed
  - Prevent KeyError exceptions
  - _Requirements: 4.2_

- [ ] 5.3 Add try-except blocks to all market data methods
  - Catch KeyError and return None
  - Catch RPC errors and retry
  - Log all errors with context
  - _Requirements: 4.1, 4.2, 4.4_

- [ ]* 5.4 Write property test for graceful degradation
  - **Property 7: Graceful Degradation**
  - **Validates: Requirements 4.1, 4.2, 4.4**

- [ ] 6. Add Configuration and Monitoring
  - [ ] 6.1 Add configuration to config/settings.py
    - DRIFT_CACHE_TTL_FUNDING = 30
    - DRIFT_CACHE_TTL_PRICE = 10
    - DRIFT_CACHE_TTL_MARKETS = 60
    - DRIFT_MAX_RETRIES = 5
    - DRIFT_RETRY_BACKOFF = 2.0
    - _Requirements: 8.1_

- [ ] 6.2 Add logging to DriftClientManager
  - Log initialization and cleanup
  - Log reference count changes
  - Log cache hits and misses
  - Log RPC errors and retries
  - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [ ] 6.3 Add metrics tracking (optional)
  - Track drift_client_ref_count
  - Track drift_cache_hits and drift_cache_misses
  - Track drift_rpc_errors
  - Track drift_subscription_failures
  - _Requirements: 8.4_

- [ ] 7. Testing and Validation
  - [ ] 7.1 Create test_drift_singleton.py
    - Test singleton pattern
    - Test reference counting
    - Test cache expiration
    - Test thread safety
    - _Requirements: All_

- [ ]* 7.2 Run property-based tests
  - Run all property tests with 100+ iterations
  - Verify all properties pass
  - _Requirements: All_

- [ ] 7.3 Test with dashboard
  - Start dashboard
  - Navigate to Funding Engine page
  - Verify market data displays
  - Check logs for HTTP 429 errors (should be zero)
  - _Requirements: All_

- [ ] 7.4 Test with multiple engines
  - Start all engines simultaneously
  - Verify single DriftClient instance
  - Verify no rate limit errors
  - Verify all engines get data
  - _Requirements: 1.1, 1.2, 3.1_

- [ ] 8. Documentation and Cleanup
  - [ ] 8.1 Update DRIFT_SDK_MIGRATION_SUMMARY.md
    - Document singleton implementation
    - Add usage examples
    - Document configuration options
    - _Requirements: 8.1_

- [ ] 8.2 Update DRIFT_API_COVERAGE.md
  - Document caching behavior
  - Document error handling
  - Add troubleshooting section
  - _Requirements: 8.1_

- [ ] 8.3 Add inline documentation
  - Add docstrings to all methods
  - Add type hints
  - Add usage examples in comments
  - _Requirements: 8.1_

## Notes

- Tasks marked with `*` are optional property-based tests
- Each task references specific requirements for traceability
- Implementation should be done in order to maintain dependencies
- Test after each major component (Cache, Manager, Adapter)
- Checkpoint after task 5 to verify error handling works
- Final checkpoint after task 7 to verify all tests pass

## Success Criteria

✅ No HTTP 429 errors in logs  
✅ No KeyError exceptions  
✅ Dashboard displays market data consistently  
✅ All engines can access Drift data simultaneously  
✅ RPC calls reduced by >90%  
✅ Memory usage reduced by >75%  
✅ All property tests pass  
✅ Backward compatibility maintained
