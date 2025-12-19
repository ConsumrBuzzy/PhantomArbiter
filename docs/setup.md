# PhantomTrader Setup Guide

## Prerequisites
- Python 3.10+
- Solana Wallet (Private Key)
- RPC Endpoint (QuickNode, Helios or Helius recommended for speed)

## 🔧 Installation

1.  **Clone the Repository**
    ```bash
    git clone https://github.com/ConsumrBuzzy/PhantomTrader.git
    cd PhantomTrader
    ```

2.  **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Environment Setup**
    Create a `.env` file in the root directory:
    ```ini
    SOLANA_PRIVATE_KEY=your_base58_private_key_here
    JUPITER_API_KEY=optional_key_for_v6_api
    ```

## ⚙️ Configuration

### 1. `config/assets.json`
Define the tokens you want to trade or watch.
- **ACTIVE**: High-freuency trading (Max 3).
- **WATCH**: Price monitoring only.
- **SCOUT**: Low-frequency monitoring for alerts.

### 2. `config/settings.py`
Adjust risk parameters (Stop Loss, Take Profit, Slippage) by editing the implementation directly if needed (or via future CLI args).

## 🚀 Running the Bot

### Monitor Mode (Safe)
Runs the strategy without executing real trades.
```bash
python main.py --monitor
```

### Live Mode (Real Money)
Enables blockchain transactions.
```bash
python main.py --live
```

### Scout Tool (Token Discovery)
Scan your wallet for untracked tokens.
```bash
python -m src.tools.scout --scan-wallet
```
