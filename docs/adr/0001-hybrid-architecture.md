# ADR-0001: Hybrid Architecture with Node.js Bridges

**Status**: Accepted  
**Date**: 2026-01-02  
**Context**: "High-Speed DEX Interaction vs Python Ecosystem"

## Context
PhantomArbiter requires:
1.  Nanosecond-level decision making (Python's data science stack/NetworkX/Pandas is superior here).
2.  Reliable interaction with Solana AMMs (Orca, Meteora, Raydium).

**The Problem**: The Python SDKs for many Solana protocols are often second-class citizens, outdated, or slower than their TypeScript/Node.js counterparts. The canonical SDKs are almost always TypeScript.

## Decision
We adopt a **Hybrid Architecture**:
1.  **Core Logic in Python**: Strategy, Graph Algorithms, Risk Management.
2.  **IO/Protocol Layer in Node.js**: "Bridges" that run as subprocesses.
3.  **Communication via Stdio**: Using JSON over standard input/output for sub-millisecond IPC latency (avoiding HTTP overhead for local calls).

Future evolution will move these Bridges into full gRPC Micro-Services (`apps/`), but for the current phase, Subprocess Bridges provide the best balance of simplicity and performance.

## Consequences
### Positive
*   **Reliability**: We use the official, maintained TS SDKs for AMMs.
*   **Performance**: Python focuses on math, Node focuses on I/O.
*   **Flexibility**: We can swap out a bridge without recompiling the core.

### Negative
*   **Complexity**: Requires managing two language runtimes.
*   **Orchestration**: `Director` must manage subprocess lifecycles (zombies, restarts).
*   **Deployment**: Docker images become larger (need Python + Node).
