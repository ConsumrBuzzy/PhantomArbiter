# Requirements Document: Drift SDK Singleton Manager

## Introduction

The current implementation creates multiple DriftClient instances across different engines and feeds, causing RPC rate limiting (HTTP 429 errors) and subscription failures. We need a singleton pattern to share a single DriftClient instance across the entire application.

## Glossary

- **DriftClient**: The official Drift Protocol SDK client that subscribes to on-chain market data
- **Singleton**: A design pattern ensuring only one instance of a class exists
- **RPC Rate Limit**: Solana RPC nodes limit the number of requests per second
- **Subscription**: WebSocket connection to Drift program accounts for real-time updates
- **DriftAdapter**: Current wrapper class for Drift Protocol integration
- **DriftFundingFeed**: Feed class that fetches funding rate data

## Requirements

### Requirement 1: Singleton DriftClient Manager

**User Story:** As a developer, I want a single shared DriftClient instance across all engines and feeds, so that we avoid RPC rate limiting and subscription conflicts.

#### Acceptance Criteria

1. THE System SHALL provide a singleton DriftClientManager class
2. WHEN any component requests a DriftClient, THE System SHALL return the same instance
3. WHEN the first component requests a DriftClient, THE System SHALL initialize and subscribe it
4. WHEN the last component releases the DriftClient, THE System SHALL unsubscribe and cleanup
5. THE System SHALL track reference counts to manage lifecycle

### Requirement 2: Lazy Initialization

**User Story:** As a system administrator, I want DriftClient to initialize only when needed, so that startup time is minimized and resources are conserved.

#### Acceptance Criteria

1. WHEN the application starts, THE System SHALL NOT initialize DriftClient automatically
2. WHEN the first component requests market data, THE System SHALL initialize DriftClient
3. WHEN DriftClient initialization fails, THE System SHALL retry with exponential backoff
4. WHEN all components stop using DriftClient, THE System SHALL cleanup resources

### Requirement 3: Thread-Safe Access

**User Story:** As a developer, I want thread-safe access to DriftClient, so that concurrent requests don't cause race conditions.

#### Acceptance Criteria

1. WHEN multiple components request DriftClient simultaneously, THE System SHALL handle requests safely
2. THE System SHALL use asyncio locks to prevent race conditions
3. WHEN one component is initializing DriftClient, THE System SHALL queue other requests
4. WHEN initialization completes, THE System SHALL notify all waiting components

### Requirement 4: Graceful Degradation

**User Story:** As a user, I want the system to continue functioning when Drift data is unavailable, so that other features remain operational.

#### Acceptance Criteria

1. WHEN DriftClient fails to initialize, THE System SHALL log the error and continue
2. WHEN market data requests fail, THE System SHALL return None or empty data
3. WHEN subscription fails due to rate limits, THE System SHALL retry with backoff
4. THE System SHALL NOT crash or block when Drift is unavailable

### Requirement 5: Connection Pooling

**User Story:** As a developer, I want efficient RPC connection management, so that we minimize network overhead and respect rate limits.

#### Acceptance Criteria

1. THE System SHALL reuse the same RPC connection for all Drift operations
2. WHEN RPC connection fails, THE System SHALL attempt reconnection
3. THE System SHALL implement connection health checks
4. WHEN connection is unhealthy, THE System SHALL recreate it

### Requirement 6: Market Data Caching

**User Story:** As a developer, I want market data to be cached, so that we reduce RPC calls and improve performance.

#### Acceptance Criteria

1. WHEN market data is fetched, THE System SHALL cache it for 30 seconds
2. WHEN cached data is requested within TTL, THE System SHALL return cached data
3. WHEN cached data expires, THE System SHALL fetch fresh data
4. THE System SHALL cache funding rates, prices, and open interest separately

### Requirement 7: Backward Compatibility

**User Story:** As a developer, I want existing code to work without changes, so that migration is seamless.

#### Acceptance Criteria

1. THE DriftAdapter SHALL continue to work with existing API
2. THE DriftFundingFeed SHALL continue to work without modifications
3. WHEN components use the old API, THE System SHALL internally use the singleton
4. THE System SHALL maintain the same return types and error handling

### Requirement 8: Monitoring and Metrics

**User Story:** As a system administrator, I want visibility into Drift SDK usage, so that I can diagnose issues and optimize performance.

#### Acceptance Criteria

1. THE System SHALL log DriftClient initialization and cleanup
2. THE System SHALL track the number of active references
3. THE System SHALL log RPC rate limit errors
4. THE System SHALL expose metrics for subscription health

## Implementation Notes

### Singleton Pattern

```python
class DriftClientManager:
    _instance = None
    _lock = asyncio.Lock()
    _drift_client = None
    _ref_count = 0
    
    @classmethod
    async def get_client(cls):
        async with cls._lock:
            if cls._drift_client is None:
                cls._drift_client = await cls._initialize()
            cls._ref_count += 1
            return cls._drift_client
    
    @classmethod
    async def release_client(cls):
        async with cls._lock:
            cls._ref_count -= 1
            if cls._ref_count == 0:
                await cls._cleanup()
```

### Caching Strategy

- **Funding Rates**: 30 second TTL (updates hourly)
- **Mark Prices**: 10 second TTL (updates frequently)
- **Open Interest**: 60 second TTL (changes slowly)

### Error Handling

- **Rate Limit (429)**: Exponential backoff, max 5 retries
- **Connection Failure**: Retry with new connection
- **Subscription Failure**: Fall back to polling mode
- **Data Unavailable**: Return None, log warning

## Success Criteria

1. ✅ No more "HTTP 429" errors in logs
2. ✅ No more "Too many requests" errors
3. ✅ No more KeyError when accessing market data
4. ✅ Dashboard displays market data consistently
5. ✅ All engines can access Drift data simultaneously
6. ✅ Startup time remains under 10 seconds
7. ✅ Memory usage doesn't increase significantly

## Out of Scope

- Historical data fetching (requires separate indexer)
- Order execution (already implemented in DriftAdapter)
- Position management UI (separate feature)
- Custom RPC endpoint configuration (uses existing settings)
