# PhantomTrader Architecture (V61.0)

## Overview
PhantomTrader is an **Intelligent High-Frequency Trading (HFT) Suite**.
It combines low-latency execution with an adaptive Machine Learning "Brain."

## 🏛️ Logical Layers

The system operates in a "Tight Loop": **Ingest → Analyze → Decide → Execute**.

### Layer 1: The Sensory Layer (Data Ingestion)
*Vision*. Translates raw blockchain noise into structured data.

*   **RPC Balancer**: Redundant connection manager (Helius + Alchemy) handling failover and rate limits.
*   **WebSocket Streamers**: Real-time listeners for Pump.fun logs and Raydium pool initializations.
*   **External Adapters**:
    *   `DexScreenerProvider`: Volume & Liquidity health.
    *   `RegimeDetector`: Market "Weather" (Volatility/Trend).
    *   `DiscoveryEngine`: "The Scout" finding Alpha Wallets.

### Layer 2: The Cognitive Layer (Intelligence & ML)
*The Brain*. Where the ML model and Ensemble strategies live.

*   **Data Broker**: The Librarian. Organizes incoming data (Prices, Regime, Wallet State) and feeds it to models.
*   **SharedPriceCache**: The Synapse. Ultra-fast shared memory for inter-process communication.
*   **Merchant Ensemble**: The Committee.
    *   `Scalper`: Momentum.
    *   `VWAP`: Trend Following.
    *   `Keltner`: Mean Reversion.
    *   **Logic**: Votes on entries. Confidences boosted by `Regime` and `DiscoveryEngine`.
*   **XGBoost Trainer**: The Memory. Learns from past trade outcomes to predict "Success Probability."

### Layer 3: The Risk & Strategy Layer (The Landlord)
*Safety Valve*. Ensures account preservation.

*   **Capital Manager**: The Treasurer. Handles position sizing (Kelly Criterion), bankruptcy checks, and gas sweeps.
*   **Token Validator**: The Security Guard. Checks for rug-pull risks (Mint Authority, Liquidity Locks).
*   **Landlord Core**: Specialized Delta-Neutral engine (if enabled).

### Layer 4: The Execution Layer (The Muscles)
*Action*. Interacts with the blockchain.

*   **Jito Adapter**: The Priority Lane. Bundles transactions with tips for guaranteed inclusion.
*   **Trade Executor**: The Translator. Speaks "Jupiter" or "Orca" SDK to build transactions.
*   **PumpPortal Adapter**: Direct bonding curve trading.
*   **Orca/Meteora Adapters**: Concentrated Liquidity management.

## 🧱 Component Map

| Component | Classification | Role |
| :--- | :--- | :--- |
| **Merchant Engine** | Orchestrator | Coordinates all layers into a single heartbeat. |
| **Discovery Engine** | Social Intelligence | Automatically identifies and tracks "Alpha Wallets." |
| **Regime Detector** | Market Analysis | Detects Volatility/Trend (The "Weather"). |
| **Whirlpool Manager** | Liquidity Provision | Manages Orca CLMM ranges. |
| **RPC Balancer** | Infrastructure | Handles API failover. |

## 🚀 Key Design Principles
1.  **Separation of Concerns**: Intelligence (Layer 2) is decoupled from Execution (Layer 4). You can swap the "Brain" without breaking the "Muscles."
2.  **Asynchronous Data, Synchronous Decide**: Data flows in async (WSS), but decisions are made in strict synchronous ticks to ensure state consistency.
3.  **Fail-Fast Safety**: Risk Layer (Layer 3) can veto any decision from Layer 2 before it reaches Layer 4.
