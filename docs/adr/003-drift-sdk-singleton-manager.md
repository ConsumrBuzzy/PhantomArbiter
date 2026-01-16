# ADR 003: Drift SDK Singleton Manager

**Status**: Proposed  
**Date**: 2026-01-16  
**Deciders**: Development Team  
**Technical Story**: Fix RPC rate limiting and KeyError issues with Drift Protocol integration

## Context

### Problem Statement

The current Drift Protocol integration creates multiple `DriftClient` instances across different engines and feeds, causing several critical issues:

1. **RPC Rate Limiting (HTTP 429)**
   - Each engine (Funding, LST, Scalp, Arb) creates its own DriftClient
   - Each DriftClient subscribes to all market data via WebSocket
   - Multiple simultaneous subscriptions trigger rate limits
   - Logs show: `Error in subscription perpMarketMap: server rejected WebSocket connection: HTTP 429`

2. **KeyError Exceptions**
   - When DriftClient fails to subscribe due to rate limits, market data isn't available
   - Code attempts to access `perp_market_subscribers[market_index]` which doesn't exist
   - Error: `KeyError: 0` when trying to fetch SOL-PERP data

3. **Resource Inefficiency**
   - 4+ DriftClient instances = ~200MB memory usage
   - ~40 RPC calls/second across all engines
   - Redundant subscriptions to the same market data

4. **Unreliable Data Access**
   - Dashboard shows "Loading markets..." indefinitely
   - Engines fail to fetch funding rates
   - Subscription failures cascade across components

### Current Architecture

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│   Funding   │  │     LST     │  │    Scalp    │  │     Arb     │
│   Engine    │  │   Engine    │  │   Engine    │  │   Engine    │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │                │
       ▼                ▼                ▼                ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│DriftAdapter │  │DriftAdapter │  │DriftAdapter │  │DriftAdapter │
│  Instance 1 │  │  Instance 2 │  │  Instance 3 │  │  Instance 4 │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │                │
       ▼                ▼                ▼                ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│DriftClient  │  │DriftClient  │  │DriftClient  │  │DriftClient  │
│  Instance 1 │  │  Instance 2 │  │  Instance 3 │  │  Instance 4 │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │                │
       └────────────────┴────────────────┴────────────────┘
                                │
                                ▼
                        ┌───────────────┐
                        │  Solana RPC   │
                        │  (Rate Limited)│
                        └───────────────┘
```

**Issues**:
- 4 separate DriftClient instances
- 4 separate WebSocket subscriptions
- 4x RPC call volume
- Rate limits triggered frequently

## Decision

We will implement a **Singleton DriftClient Manager** with the following characteristics:

### 1. Singleton Pattern with Reference Counting

Create a `DriftClientManager` class that:
- Maintains a single shared `DriftClient` instance
- Uses reference counting to manage lifecycle
- Initializes lazily on first request
- Cleans up when last reference is released

### 2. Cache Layer

Implement a caching layer to reduce RPC calls:
- **Funding rates**: 30 second TTL (updates hourly)
- **Mark prices**: 10 second TTL (updates frequently)
- **Market data**: 60 second TTL (changes slowly)

### 3. Graceful Degradation

Handle failures without crashing:
- Return `None` when data unavailable
- Log errors but continue operation
- Retry with exponential backoff
- Check subscription status before access

### 4. Backward Compatibility

Maintain existing API:
- `DriftAdapter` continues to work unchanged
- `DriftFundingFeed` requires no modifications
- Internal routing through singleton manager
- Optional flag for gradual migration

## Proposed Architecture

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│   Funding   │  │     LST     │  │    Scalp    │  │     Arb     │
│   Engine    │  │   Engine    │  │   Engine    │  │   Engine    │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │                │
       └────────────────┴────────────────┴────────────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │  DriftClientManager   │
                    │     (Singleton)       │
                    │                       │
                    │  - _drift_client      │
                    │  - _ref_count: 4      │
                    │  - _cache             │
                    └───────────┬───────────┘
                                │
                                ▼
                        ┌───────────────┐
                        │  DriftClient  │
                        │  (Single)     │
                        └───────┬───────┘
                                │
                                ▼
                        ┌───────────────┐
                        │  Solana RPC   │
                        │  (No Limits)  │
                        └───────────────┘
```

**Benefits**:
- 1 DriftClient instance (vs 4)
- 1 WebSocket subscription (vs 4)
- 97.5% reduction in RPC calls (caching)
- 75% reduction in memory usage

## Implementation Details

### Component 1: Cache Manager

```python
# src/shared/drift/cache_manager.py

@dataclass
class CacheEntry:
    data: Any
    timestamp: float
    ttl: float
    
    def is_expired(self) -> bool:
        return time.time() - self.timestamp > self.ttl

class CacheManager:
    def __init__(self):
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()
        
    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            entry = self._cache.get(key)
            if entry and not entry.is_expired():
                return entry.data
            return None
            
    async def set(self, key: str, data: Any, ttl: float):
        async with self._lock:
            self._cache[key] = CacheEntry(data, time.time(), ttl)
```

### Component 2: DriftClientManager

```python
# src/shared/drift/client_manager.py

class DriftClientManager:
    """Singleton manager for shared DriftClient instance."""
    
    _instance = None
    _lock = asyncio.Lock()
    _drift_client: Optional[DriftClient] = None
    _ref_count: int = 0
    _cache: CacheManager = CacheManager()
    _rpc_client: Optional[AsyncClient] = None
    _wallet: Optional[Any] = None
    _network: str = "mainnet"
    
    @classmethod
    async def get_client(cls, network: str = "mainnet") -> Optional[DriftClient]:
        """Get or create the shared DriftClient instance."""
        async with cls._lock:
            if cls._drift_client is None:
                cls._drift_client = await cls._initialize_client(network)
            cls._ref_count += 1
            return cls._drift_client
    
    @classmethod
    async def release_client(cls) -> None:
        """Release reference to DriftClient, cleanup if last reference."""
        async with cls._lock:
            cls._ref_count -= 1
            if cls._ref_count == 0:
                await cls._cleanup_client()
    
    @classmethod
    async def get_funding_rate(cls, market: str) -> Optional[Dict]:
        """Get funding rate with caching."""
        # Check cache
        cache_key = f"funding_rate:{market}"
        cached = await cls._cache.get(cache_key)
        if cached:
            return cached
        
        # Fetch from DriftClient
        client = await cls.get_client()
        if not client:
            return None
        
        try:
            # ... fetch logic ...
            result = {...}
            
            # Cache result
            await cls._cache.set(cache_key, result, ttl=30.0)
            return result
        except KeyError:
            Logger.error(f"[DRIFT] Market {market} not subscribed")
            return None
        finally:
            await cls.release_client()
```

### Component 3: Updated DriftAdapter

```python
# src/engines/funding/drift_adapter.py

class DriftAdapter:
    def __init__(self, network: str = "mainnet"):
        self.network = network
        self._using_singleton = True  # Flag for singleton mode
        
    async def connect(self, wallet, sub_account: int = 0) -> bool:
        """Connect using singleton manager."""
        if self._using_singleton:
            client = await DriftClientManager.get_client(self.network)
            self.connected = (client is not None)
            return self.connected
        else:
            # Old code path for fallback
            ...
    
    async def disconnect(self):
        """Release singleton reference."""
        if self._using_singleton:
            await DriftClientManager.release_client()
            self.connected = False
        else:
            # Old code path
            ...
    
    async def get_funding_rate(self, market: str) -> Optional[Dict]:
        """Get funding rate via singleton manager."""
        if self._using_singleton:
            return await DriftClientManager.get_funding_rate(market)
        else:
            # Old code path
            ...
```

## Migration Path

### Phase 1: Add Singleton Manager (Non-Breaking)
1. Create `CacheManager` class
2. Create `DriftClientManager` class
3. Test in isolation
4. **No changes to existing code**

### Phase 2: Update DriftAdapter (Backward Compatible)
1. Add `_using_singleton` flag (default: True)
2. Route calls through manager when flag is True
3. Keep old code path for fallback
4. **Existing code continues to work**

### Phase 3: Update Feeds (Transparent)
1. `DriftFundingFeed` automatically uses new `DriftAdapter`
2. **No code changes needed in feeds**

### Phase 4: Cleanup (Optional)
1. Remove old code paths
2. Remove `_using_singleton` flag
3. Simplify `DriftAdapter`

## Consequences

### Positive

1. **Eliminates Rate Limiting**
   - Single DriftClient = single subscription
   - No more HTTP 429 errors
   - Reliable market data access

2. **Fixes KeyError Issues**
   - Proper subscription status checking
   - Graceful handling of missing data
   - No more crashes on data access

3. **Improves Performance**
   - 97.5% reduction in RPC calls (caching)
   - 75% reduction in memory usage
   - Faster data access (cache hits <1ms)

4. **Maintains Compatibility**
   - Existing code works unchanged
   - Gradual migration possible
   - Easy rollback if needed

5. **Better Resource Management**
   - Reference counting ensures cleanup
   - Lazy initialization saves resources
   - Shared connections reduce overhead

### Negative

1. **Increased Complexity**
   - Singleton pattern adds abstraction layer
   - Reference counting requires careful management
   - Cache invalidation logic needed

2. **Single Point of Failure**
   - If singleton fails, all engines affected
   - Requires robust error handling
   - Need fallback mechanisms

3. **Testing Complexity**
   - Singleton state persists across tests
   - Need to reset state between tests
   - Property-based testing more complex

4. **Migration Effort**
   - Requires careful phased rollout
   - Need comprehensive testing
   - Documentation updates needed

### Mitigations

1. **Robust Error Handling**
   - Graceful degradation on failures
   - Automatic retry with backoff
   - Fallback to old code path if needed

2. **Comprehensive Testing**
   - Unit tests for each component
   - Property-based tests for correctness
   - Integration tests with dashboard
   - Load testing for rate limits

3. **Monitoring and Metrics**
   - Track reference count
   - Monitor cache hit rates
   - Log RPC errors
   - Alert on subscription failures

4. **Documentation**
   - ADR for decision rationale
   - Implementation guide
   - Troubleshooting guide
   - Migration checklist

## Alternatives Considered

### Alternative 1: Connection Pooling

**Description**: Create a pool of DriftClient instances and distribute requests.

**Pros**:
- Load balancing across connections
- Fault tolerance (one fails, others continue)

**Cons**:
- Still creates multiple subscriptions
- Doesn't solve rate limiting
- More complex than singleton
- Higher memory usage

**Rejected**: Doesn't address root cause (too many subscriptions)

### Alternative 2: Polling Instead of Subscriptions

**Description**: Remove WebSocket subscriptions, poll RPC for data.

**Pros**:
- No subscription failures
- Simpler error handling

**Cons**:
- Higher latency (polling delay)
- More RPC calls (no real-time updates)
- Stale data between polls
- Defeats purpose of SDK

**Rejected**: Worse performance and data freshness

### Alternative 3: External Drift Data Service

**Description**: Run separate service that subscribes to Drift and exposes HTTP API.

**Pros**:
- Decouples from main application
- Can scale independently
- Centralized data management

**Cons**:
- Additional infrastructure
- Network latency
- More moving parts
- Operational complexity

**Rejected**: Over-engineered for current needs

### Alternative 4: Use Mock Data

**Description**: Use mock data instead of real Drift connection.

**Pros**:
- No rate limiting
- No subscription issues
- Fast and reliable

**Cons**:
- Not real data
- Can't trade with mock data
- Defeats purpose of integration

**Rejected**: User explicitly wants real Drift data

## Success Metrics

### Before Implementation
- ❌ HTTP 429 errors: ~10-20 per minute
- ❌ KeyError exceptions: ~5-10 per minute
- ❌ RPC calls: ~40 per second
- ❌ Memory usage: ~200MB (4 clients)
- ❌ Dashboard: Shows "Loading markets..." indefinitely

### After Implementation
- ✅ HTTP 429 errors: 0
- ✅ KeyError exceptions: 0
- ✅ RPC calls: ~1 per second (97.5% reduction)
- ✅ Memory usage: ~50MB (75% reduction)
- ✅ Dashboard: Displays market data within 2 seconds

### Monitoring

```python
# Metrics to track
drift_client_ref_count: Gauge          # Current reference count
drift_cache_hits: Counter              # Cache hit count
drift_cache_misses: Counter            # Cache miss count
drift_rpc_errors: Counter              # RPC error count
drift_subscription_failures: Counter   # Subscription failure count
drift_initialization_time: Histogram   # Time to initialize
```

## Implementation Status

**Current Status**: Specification Complete

**Specification Location**: `.kiro/specs/drift-sdk-singleton/`

**Files**:
- `requirements.md` - 8 requirements with acceptance criteria
- `design.md` - Complete architecture and design
- `tasks.md` - 30+ implementation tasks

**Next Steps**:
1. Review and approve this ADR
2. Begin implementation following tasks.md
3. Start with Task 1: Create Cache Manager
4. Test each component before proceeding
5. Deploy in phases for safe migration

**Estimated Effort**: 2-3 days for full implementation and testing

## References

- [Drift Protocol Documentation](https://docs.drift.trade/)
- [driftpy SDK](https://github.com/drift-labs/driftpy)
- Specification: `.kiro/specs/drift-sdk-singleton/`
- Related: `DRIFT_SDK_MIGRATION_SUMMARY.md`
- Related: `DRIFT_API_COVERAGE.md`

## Notes

- This ADR supersedes the previous ad-hoc Drift integration approach
- Implementation should follow the phased migration path
- All property-based tests must pass before production deployment
- Backward compatibility must be maintained throughout migration
- Consider this pattern for other SDK integrations (Jupiter, Pyth, etc.)

---

**Approved By**: _Pending_  
**Implementation Start**: _Pending_  
**Implementation Complete**: _Pending_  
**Deployed to Production**: _Pending_
