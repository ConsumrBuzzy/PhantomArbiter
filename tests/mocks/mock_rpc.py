"""
Mock RPC Client
===============
Fake Solana RPC client for testing without network calls.
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import base64
import json


@dataclass
class MockAccountInfo:
    """Mock Solana account info."""
    pubkey: str
    lamports: int
    data: bytes
    owner: str = "11111111111111111111111111111111"
    executable: bool = False
    

class MockRpcClient:
    """
    Mock Solana RPC client.
    
    Returns preset responses for common RPC calls.
    
    Usage:
        client = MockRpcClient()
        client.set_account_info(pubkey, MockAccountInfo(...))
        info = await client.get_account_info(pubkey)
    """
    
    def __init__(self):
        self._accounts: Dict[str, MockAccountInfo] = {}
        self._slot = 100000
        self._blockhash = "MOCK_BLOCKHASH_" + "A" * 32
        self.call_count = 0
        
    def set_account_info(self, pubkey: str, info: MockAccountInfo):
        """Set mock account info for a pubkey."""
        self._accounts[pubkey] = info
        
    def set_slot(self, slot: int):
        """Set current slot."""
        self._slot = slot
        
    async def get_slot(self) -> int:
        """Get current slot."""
        self.call_count += 1
        return self._slot
        
    async def get_latest_blockhash(self) -> Dict[str, Any]:
        """Get latest blockhash."""
        self.call_count += 1
        return {
            "blockhash": self._blockhash,
            "lastValidBlockHeight": self._slot + 150,
        }
        
    async def get_account_info(self, pubkey: str) -> Optional[Dict[str, Any]]:
        """Get account info for a pubkey."""
        self.call_count += 1
        
        if pubkey not in self._accounts:
            return None
            
        info = self._accounts[pubkey]
        return {
            "value": {
                "lamports": info.lamports,
                "data": [base64.b64encode(info.data).decode(), "base64"],
                "owner": info.owner,
                "executable": info.executable,
            }
        }
        
    async def get_multiple_accounts(self, pubkeys: List[str]) -> List[Optional[Dict[str, Any]]]:
        """Get multiple accounts."""
        self.call_count += 1
        return [await self.get_account_info(pk) for pk in pubkeys]
        
    async def send_transaction(self, tx: Any, opts: Any = None) -> Dict[str, Any]:
        """Mock send transaction."""
        self.call_count += 1
        return {
            "result": "MOCK_TX_SIG_" + "X" * 64,
        }
        
    async def simulate_transaction(self, tx: Any) -> Dict[str, Any]:
        """Mock simulate transaction."""
        self.call_count += 1
        return {
            "value": {
                "err": None,
                "logs": ["Program log: Mock simulation success"],
                "unitsConsumed": 50000,
            }
        }
        
    async def get_token_accounts_by_owner(self, owner: str, mint: str = None) -> Dict[str, Any]:
        """Get token accounts for owner."""
        self.call_count += 1
        return {
            "value": []  # Empty by default
        }
        
    async def is_connected(self) -> bool:
        """Check connection status."""
        return True


class MockAsyncClient(MockRpcClient):
    """Alias for compatibility with AsyncClient type hints."""
    pass
