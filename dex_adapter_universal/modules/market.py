"""
Market Module

Provides pool and price queries.
"""

import logging
from decimal import Decimal
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..client import DexClient

from ..types import Pool
from ..types.solana_tokens import KNOWN_TOKEN_MINTS, resolve_token_mint
from ..protocols import ProtocolRegistry
from ..errors import PoolUnavailable, ConfigurationError

logger = logging.getLogger(__name__)

# Well-known pool addresses for common pairs
KNOWN_POOLS = {
    # Raydium CLMM pools
    "raydium": {
        "SOL/USDC": "2QdhepnKRTLjjSqPL1PtKNwqrUkoLee5Gqs8bvZhRdMv",
        "SOL/USDT": "3nMFwZXwY1s1M5s8vYAuP1TXqPNGbWkkSGttTbmjKVxV",
    },
    # Meteora DLMM pools
    "meteora": {
        "SOL/USDC": "BVRbyLjjfSBcoyiYFuxbgKYnWuiFaF9CSXEa5vdSZ4oN",
    },
}


class MarketModule:
    """
    Market data module

    Provides:
    - Pool queries
    - Price information

    Usage:
        client = DexClient(rpc_url, keypair)

        # Get pool by address
        pool = client.market.pool("pool_address...")

        # Get pool by symbol (requires protocol)
        pool = client.market.pool_by_symbol("SOL/USDC", dex="raydium")

        # Get current price
        price = client.market.price("SOL/USDC", dex="raydium")
    """

    def __init__(self, client: "DexClient"):
        """
        Initialize market module

        Args:
            client: DexClient instance
        """
        self._client = client
        self._rpc = client.rpc
        self._pool_cache: dict[str, Pool] = {}

    def pool(
        self,
        pool_address: str,
        dex: Optional[str] = None,
        refresh: bool = False,
    ) -> Pool:
        """
        Get pool by address

        Args:
            pool_address: Pool address
            dex: Protocol name (auto-detected if not provided)
            refresh: Force refresh from chain

        Returns:
            Pool information
        """
        # Check cache
        if not refresh and pool_address in self._pool_cache:
            return self._pool_cache[pool_address]

        # Auto-detect protocol if not specified
        if dex is None:
            dex = self._detect_protocol(pool_address)

        adapter = ProtocolRegistry.get(dex, self._rpc)
        pool = adapter.get_pool(pool_address)

        # Cache result
        self._pool_cache[pool_address] = pool
        return pool

    def pool_by_symbol(
        self,
        symbol: str,
        dex: str = "raydium",
    ) -> Optional[Pool]:
        """
        Get pool by trading pair symbol

        Args:
            symbol: Trading pair (e.g., "SOL/USDC")
            dex: Protocol name

        Returns:
            Pool if found, None otherwise
        """
        # Normalize symbol
        symbol = symbol.upper().replace("-", "/")

        # Check known pools first
        if dex in KNOWN_POOLS:
            if symbol in KNOWN_POOLS[dex]:
                pool_address = KNOWN_POOLS[dex][symbol]
                return self.pool(pool_address, dex)
            # Try reversed symbol
            parts = symbol.split("/")
            if len(parts) == 2:
                reversed_symbol = f"{parts[1]}/{parts[0]}"
                if reversed_symbol in KNOWN_POOLS[dex]:
                    pool_address = KNOWN_POOLS[dex][reversed_symbol]
                    return self.pool(pool_address, dex)

        # Parse symbol and resolve to mints
        parts = symbol.split("/")
        if len(parts) != 2:
            raise ConfigurationError.invalid("symbol", f"Invalid symbol format: {symbol}. Expected format: TOKEN0/TOKEN1")

        token0_symbol, token1_symbol = parts

        # Resolve symbols to mint addresses using centralized registry
        token0_mint = resolve_token_mint(token0_symbol)
        token1_mint = resolve_token_mint(token1_symbol)

        # Try adapter lookup with mints
        adapter = ProtocolRegistry.get(dex, self._rpc)
        pool = adapter.get_pool_by_tokens(token0_mint, token1_mint)

        if pool is None:
            # Try reversed order
            pool = adapter.get_pool_by_tokens(token1_mint, token0_mint)

        return pool

    def resolve_token_mint(self, token: str) -> str:
        """
        Resolve token symbol to mint address

        Args:
            token: Token symbol or mint address

        Returns:
            Mint address
        """
        return resolve_token_mint(token)

    def pools(
        self,
        dex: Optional[str] = None,
        token: Optional[str] = None,
    ) -> List[Pool]:
        """
        List pools

        Args:
            dex: Optional protocol filter
            token: Optional token filter (symbol like "SOL" or mint address)

        Returns:
            List of pools
        """
        pools: List[Pool] = []

        protocols = [dex] if dex else ProtocolRegistry.list()

        # Resolve token symbol to mint address if provided
        token_mint = self.resolve_token_mint(token) if token else None

        for protocol in protocols:
            try:
                adapter = ProtocolRegistry.get(protocol, self._rpc)
                if token_mint:
                    protocol_pools = adapter.get_pools_by_token(token_mint)
                else:
                    protocol_pools = []  # Would need indexer
                pools.extend(protocol_pools)
            except Exception as e:
                logger.debug(f"Failed to query pools from {protocol}: {e}", exc_info=True)
                continue

        return pools

    def price(
        self,
        pool_or_symbol: str,
        dex: str = "raydium",
    ) -> Decimal:
        """
        Get current price

        Args:
            pool_or_symbol: Pool address or trading pair symbol
            dex: Protocol name (used if symbol provided)

        Returns:
            Current price
        """
        # Check if it's a pool address (base58, ~44 chars)
        if len(pool_or_symbol) > 30:
            pool = self.pool(pool_or_symbol)
        else:
            pool = self.pool_by_symbol(pool_or_symbol, dex)
            if not pool:
                raise PoolUnavailable.not_found(pool_or_symbol)

        return pool.price

    def price_usd(
        self,
        token: str,
        dex: str = "raydium",
    ) -> Optional[Decimal]:
        """
        Get token price in USD

        Args:
            token: Token symbol or mint
            dex: Protocol name

        Returns:
            USD price or None
        """
        # Try to find a stablecoin pool
        stables = ["USDC", "USDT"]

        for stable in stables:
            try:
                pool = self.pool_by_symbol(f"{token}/{stable}", dex)
                if pool:
                    return pool.price
            except Exception as e:
                logger.debug(f"Failed to get price for {token}/{stable}: {e}", exc_info=True)
                continue

        return None

    def _detect_protocol(self, pool_address: str) -> str:
        """
        Auto-detect protocol for a pool address

        Tries each registered protocol until one succeeds.

        Raises:
            PoolUnavailable: If no protocol can parse the pool
        """
        errors = []
        for protocol in ProtocolRegistry.list():
            try:
                adapter = ProtocolRegistry.get(protocol, self._rpc)
                adapter.get_pool(pool_address)
                return protocol
            except Exception as e:
                errors.append(f"{protocol}: {e}")
                logger.debug(f"Protocol {protocol} failed for pool {pool_address}: {e}")
                continue

        # Raise error instead of silently defaulting to raydium
        raise PoolUnavailable(
            f"Could not detect protocol for pool {pool_address}. Tried: {', '.join(errors)}",
            pool_address=pool_address,
        )

    def refresh_pool(self, pool_address: str) -> Pool:
        """Force refresh pool from chain"""
        # Preserve dex from cached pool if available
        dex = None
        if pool_address in self._pool_cache:
            dex = self._pool_cache[pool_address].dex
            del self._pool_cache[pool_address]
        return self.pool(pool_address, dex=dex, refresh=True)

    def clear_cache(self):
        """Clear pool cache"""
        self._pool_cache.clear()
