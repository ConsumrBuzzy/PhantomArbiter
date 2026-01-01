"""
TokenDiscoveryService - The Scout
==================================
Layer A: Market Monitor - Token metadata and discovery.

Responsibilities:
- Token identification (mint -> symbol)
- Metadata fetching (decimals, liquidity, volume)
- Token validation (rug checks, freeze authority)
- New token discovery events

Integrates with:
- TokenRegistry (existing)
- Scout agents for new pool detection
- Nomad Archive for persistence
"""

import time
from typing import Dict, Optional, Callable, List
from dataclasses import dataclass

from src.shared.system.logging import Logger
from src.shared.system.signal_bus import signal_bus, Signal, SignalType


@dataclass
class TokenMetadata:
    """Comprehensive token metadata."""
    mint: str
    symbol: str
    name: str
    decimals: int
    
    # Market data (volatile)
    liquidity_usd: float = 0.0
    volume_24h: float = 0.0
    price_usd: float = 0.0
    
    # Risk data (semi-persistent)
    is_verified: bool = False
    is_frozen: bool = False
    has_mint_authority: bool = False
    rug_risk_score: float = 0.0
    
    # Confidence
    confidence: float = 0.0
    source: str = "unknown"
    last_updated: float = 0.0


@dataclass
class ValidationResult:
    """Token safety validation result."""
    mint: str
    is_safe: bool
    reason: str = ""
    liquidity_usd: float = 0.0
    checks_passed: List[str] = None
    checks_failed: List[str] = None


class TokenDiscoveryService:
    """
    The Scout - Token discovery and metadata service.
    
    Central interface for token identification and validation.
    Feeds the Cartographer/Nomad persistence layer.
    """
    
    def __init__(self):
        self._registry = None  # Lazy load
        self._validator = None  # Lazy load
        self._discovery_callbacks: List[Callable[[str], None]] = []
        
        Logger.info("🔍 TokenDiscoveryService initialized")
    
    @property
    def registry(self):
        """Lazy load TokenRegistry."""
        if not self._registry:
            from src.shared.infrastructure.token_registry import get_registry
            self._registry = get_registry()
        return self._registry
    
    @property
    def validator(self):
        """Lazy load Validator."""
        if not self._validator:
            from src.core.validator import TokenValidator
            self._validator = TokenValidator()
        return self._validator
    
    def get_symbol(self, mint: str) -> str:
        """Get symbol for a mint address."""
        return self.registry.get_symbol(mint)
    
    def get_metadata(self, mint: str) -> TokenMetadata:
        """
        Get comprehensive metadata for a token.
        
        Aggregates from multiple sources:
        - TokenRegistry (identity)
        - Validator (risk)
        - Market data (volatile)
        """
        try:
            full_meta = self.registry.get_full_metadata(mint)
            
            identity = full_meta.get("identity", {})
            risk = full_meta.get("risk", {})
            market = full_meta.get("market", {})
            
            return TokenMetadata(
                mint=mint,
                symbol=identity.get("symbol", mint[:8]),
                name=identity.get("name", "Unknown"),
                decimals=identity.get("decimals", 9),
                liquidity_usd=market.get("liquidity_usd", 0.0),
                volume_24h=market.get("volume_24h", 0.0),
                price_usd=market.get("price_usd", 0.0),
                is_verified=risk.get("is_verified", False),
                is_frozen=risk.get("is_frozen", False),
                has_mint_authority=risk.get("has_mint_authority", False),
                rug_risk_score=risk.get("rug_risk_score", 0.0),
                confidence=identity.get("confidence", 0.0),
                source=identity.get("source", "unknown"),
                last_updated=time.time(),
            )
        except Exception as e:
            Logger.error(f"Metadata fetch failed for {mint[:8]}: {e}")
            return TokenMetadata(
                mint=mint,
                symbol=mint[:8],
                name="Unknown",
                decimals=9,
            )
    
    def validate(self, mint: str, symbol: str = None) -> ValidationResult:
        """
        Validate token safety.
        
        Runs comprehensive checks:
        - Freeze authority
        - Mint authority
        - Liquidity depth
        - Holder concentration
        """
        try:
            result = self.validator.validate(mint, symbol or mint[:8])
            
            return ValidationResult(
                mint=mint,
                is_safe=result.is_safe,
                reason=result.reason if hasattr(result, 'reason') else "",
                liquidity_usd=result.liquidity if hasattr(result, 'liquidity') else 0.0,
            )
        except Exception as e:
            Logger.error(f"Validation failed for {mint[:8]}: {e}")
            return ValidationResult(
                mint=mint,
                is_safe=False,
                reason=f"Validation error: {e}",
            )
    
    def on_new_token(self, callback: Callable[[str], None]) -> None:
        """Register callback for new token discovery."""
        self._discovery_callbacks.append(callback)
        
        # Also subscribe to SignalBus
        signal_bus.subscribe(SignalType.NEW_TOKEN, lambda sig: callback(sig.data.get("mint")))
    
    def register_token(self, mint: str, symbol: str) -> None:
        """Manually register a token."""
        self.registry.register_token(mint, symbol)
    
    def is_known(self, mint: str) -> bool:
        """Check if token is known."""
        return self.registry.is_known(mint)
    
    # =========================================================================
    # SAURON DISCOVERY (The All-Seeing Eye)
    # =========================================================================
    
    _sauron = None
    
    @property
    def sauron(self):
        """Lazy load Sauron Discovery."""
        if self._sauron is None:
            try:
                from src.core.scout.discovery.sauron_discovery import SauronDiscovery
                self._sauron = SauronDiscovery()
            except Exception as e:
                Logger.error(f"Sauron import failed: {e}")
        return self._sauron
    
    def start_discovery(self) -> None:
        """
        Start the Sauron all-seeing eye.
        
        Monitors multiple launchpads for new token launches:
        - Pump.fun bonding curves
        - Raydium pool creation
        - Orca Whirlpool creation
        - Meteora DLMM creation
        """
        if self.sauron:
            self.sauron.set_sniper_callback(self._on_new_pool_detected)
            self.sauron.start()
            Logger.info("👁️ Sauron Discovery started (multi-launchpad monitoring)")
    
    def stop_discovery(self) -> None:
        """Stop Sauron discovery."""
        if self.sauron:
            self.sauron.stop()
    
    def check_graduated(self, mint: str) -> dict:
        """
        Check if a token has "graduated" to Jupiter.
        
        A token is graduated if Jupiter can route it (has DEX liquidity).
        Used in the Trigger → Fetch → Score discovery flow.
        
        Returns:
            {"graduated": bool, "price": float, "route_count": int}
        """
        if self.sauron:
            return self.sauron.check_jupiter_graduated(mint)
        return {"graduated": False, "price": 0.0, "route_count": 0}
    
    def _on_new_pool_detected(self, pool_data: dict) -> None:
        """
        Handle new pool detection from Sauron.
        
        Hydrates TokenRegistry and notifies subscribers.
        """
        mint = pool_data.get("mint")
        symbol = pool_data.get("symbol", mint[:8] if mint else "UNKNOWN")
        source = pool_data.get("source", "UNKNOWN")
        
        if not mint:
            return
        
        # Hydrate registry
        self.register_token(mint, symbol)
        
        # Emit to SignalBus
        signal_bus.publish(SignalType.NEW_TOKEN, {
            "mint": mint,
            "symbol": symbol,
            "source": source,
            "timestamp": time.time(),
        })
        
        # Notify direct callbacks
        for callback in self._discovery_callbacks:
            try:
                callback(mint)
            except Exception as e:
                Logger.error(f"Discovery callback failed: {e}")
        
        Logger.info(f"👁️ NEW: {symbol} ({source}) - {mint[:12]}...")

