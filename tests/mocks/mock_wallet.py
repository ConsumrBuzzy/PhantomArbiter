"""
Mock Wallet Manager
===================
Fake wallet for testing without Solana RPC calls.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass


@dataclass
class MockAssetInfo:
    """Mock asset balance info."""
    symbol: str
    amount: float
    usd_value: float
    mint: str = ""


class MockWalletManager:
    """
    Mock WalletManager returning preset balances.
    
    Usage:
        wallet = MockWalletManager({"SOL": 5.0, "USDC": 500.0})
        balance = wallet.get_current_live_usd_balance()
    """
    
    def __init__(self, balances: Dict[str, float] = None):
        self.balances = balances or {"SOL": 1.0, "USDC": 100.0}
        self._prices = {"SOL": 150.0, "USDC": 1.0, "JUP": 0.85}
        self.call_count = 0
        
    def set_balance(self, token: str, amount: float):
        """Set balance for a token."""
        self.balances[token] = amount
        
    def set_price(self, token: str, price: float):
        """Set price for USD calculation."""
        self._prices[token] = price
        
    def get_current_live_usd_balance(self) -> Dict[str, Any]:
        """Get current wallet balances in USD format."""
        self.call_count += 1
        
        assets = []
        total_usd = 0.0
        
        for symbol, amount in self.balances.items():
            price = self._prices.get(symbol, 0.0)
            usd_value = amount * price
            total_usd += usd_value
            
            assets.append({
                "symbol": symbol,
                "amount": amount,
                "usd_value": usd_value,
            })
            
        return {
            "assets": assets,
            "breakdown": dict(self.balances),
            "total_usd": total_usd,
        }
        
    def get_balance(self, token: str) -> float:
        """Get balance for a specific token."""
        self.call_count += 1
        return self.balances.get(token, 0.0)
        
    def get_sol_balance(self) -> float:
        """Get SOL balance."""
        return self.get_balance("SOL")
        
    def transfer(self, token: str, amount: float, to_address: str) -> Dict[str, Any]:
        """Mock transfer (no-op for testing)."""
        self.call_count += 1
        
        if self.balances.get(token, 0) < amount:
            return {"success": False, "error": "Insufficient balance"}
            
        self.balances[token] = self.balances.get(token, 0) - amount
        
        return {
            "success": True,
            "txid": "MOCK_TX_" + token + "_" + str(amount),
            "amount": amount,
        }
