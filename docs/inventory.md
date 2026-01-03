# System Inventory

A detailed look at the new directory structure and key files.

## `/apps` - The Service Layer
| Path | Description |
|------|-------------|
| `datafeed/src/datafeed/market_data.proto` | gRPC definition for the future DataFeed service. |
| `datafeed/src/datafeed/server.py` | Entry point for the DataFeed server. |
| `execution/src/execution/orders.proto` | gRPC definition for the future Execution service. |
| `galaxy/src/galaxy/server.py` | **Entry point for the active Galaxy dashboard.** |
| `galaxy/src/galaxy/visual_transformer.py` | Converts core events into 3D visual objects. |

## `/bridges` - The Bridge Layer
| Path | Description |
|------|-------------|
| `orca_daemon.js` | Long-running Node.js process for Orca interactions. |
| `raydium_daemon.js` | Long-running Node.js process for Raydium interactions. |
| `meteora_bridge.js` | Long-running Node.js process for Meteora interactions. |
| `execution_engine.js` | Shared JS implementation for transaction building. |

## `/src` - The Core Layer
### Roots
| Path | Description |
|------|-------------|
| `main.py` | **The CLI entry point.** Handles args and spawns Director. |
| `director.py` | **The Lifecycle Manager.** Orchestrates Broker, Arbiter, and Galaxy. |

### `/src/core`
| Path | Description |
|------|-------------|
| `data_broker.py` | The central data hub. |
| `shared_cache.py` | High-speed memory cache for prices. |
| `engine_manager.py` | DI container for initializing sub-engines. |

### `/src/shared`
| Path | Description |
|------|-------------|
| `execution/orca_bridge.py` | Python wrapper for `orca_daemon.js`. |
| `infrastructure/event_bridge.py` | HTTP client for sending events to Galaxy. |
| `api_service.py` | Fallback detailed API if Galaxy fails to launch. |

---

## Key Dependency Flow

`main.py`  
  ⬇️  
`UnifiedDirector`  
  ⬇️  
`DataBroker` --(subprocess)--> `Bridges`  
  ⬇️  
`ArbiterEngine`  
  ⬇️  
`EventBridge` --(http)--> `Galaxy App`  
