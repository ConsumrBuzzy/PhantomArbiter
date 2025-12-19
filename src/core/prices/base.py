from abc import ABC, abstractmethod

class PriceProvider(ABC):
    """Abstract base class for price data providers."""
    
    @abstractmethod
    def get_name(self) -> str:
        """Return provider name (e.g. 'Jupiter', 'DexScreener')."""
        pass
    
    @abstractmethod
    def fetch_prices(self, mints: list) -> dict:
        """
        Fetch prices for a list of mints.
        Returns: Dict {mint: price_usd}
        """
        pass
