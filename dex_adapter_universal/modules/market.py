"""
Market Module

Provides pool and price queries across multiple chains:
- Solana: Raydium CLMM, Meteora DLMM
- Ethereum: Uniswap V3
- BSC: PancakeSwap V3
"""

import logging
from decimal import Decimal
from typing import List, Optional, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from ..client import DexClient
    from ..protocols.uniswap import UniswapAdapter
    from ..protocols.pancakeswap import PancakeSwapAdapter

from ..types import Pool
from ..types.solana_tokens import SOLANA_TOKEN_MINTS, resolve_token_mint
from ..types.evm_tokens import resolve_token_address
from ..types.pool import KNOWN_POOLS
from ..protocols import ProtocolRegistry
from ..errors import PoolUnavailable, ConfigurationError, OperationNotSupported
from ..config import config
from .wallet import Chain

logger = logging.getLogger(__name__)

# Default DEX for each chain
DEFAULT_DEX_BY_CHAIN = {
    Chain.SOLANA: "raydium",
    Chain.ETH: "uniswap",
    Chain.BSC: "pancakeswap",
}

# Valid DEX protocols per chain
VALID_DEX_BY_CHAIN = {
    Chain.SOLANA: {"raydium", "meteora"},
    Chain.ETH: {"uniswap"},
    Chain.BSC: {"pancakeswap"},
}


class MarketModule:
    """
    Market data module for multi-chain pool and price queries

    Supports:
    - Solana: Raydium CLMM, Meteora DLMM
    - Ethereum: Uniswap V3
    - BSC: PancakeSwap V3

    Usage:
        client = DexClient(rpc_url, keypair)

        # Solana pool queries (default)
        pool = client.market.pool("pool_address...", dex="raydium")
        pool = client.market.pool_by_symbol("SOL/USDC", dex="raydium")
        price = client.market.price("SOL/USDC", dex="raydium")

        # Ethereum pool queries
        pool = client.market.pool_by_symbol("ETH/USDC", chain="eth")
        price = client.market.price("ETH/USDC", chain="eth")

        # BSC pool queries
        pool = client.market.pool_by_symbol("BNB/USDT", chain="bsc")
        price = client.market.price("BNB/USDT", chain="bsc")
    """

    def __init__(self, client: "DexClient"):
        """
        Initialize market module

        Args:
            client: DexClient instance
        """
        self._client = client
        self._rpc = client.rpc

        # Lazy-initialized EVM adapters
        self._uniswap_adapter: Optional["UniswapAdapter"] = None
        self._pancakeswap_adapter: Optional["PancakeSwapAdapter"] = None

    def pool(
        self,
        pool_address: str,
        dex: Optional[str] = None,
        chain: Union[str, Chain] = Chain.SOLANA,
    ) -> Pool:
        """
        Get pool by address

        Args:
            pool_address: Pool address
            dex: Protocol name (auto-detected if not provided for Solana)
            chain: Blockchain ("solana", "eth", "bsc" or Chain enum)

        Returns:
            Pool information
        """
        resolved_chain = self._resolve_chain(chain)

        # Set default dex if not provided
        if dex is None:
            dex = self._get_default_dex(resolved_chain)

        # Validate chain/dex combination
        self._validate_chain_dex(resolved_chain, dex)

        if resolved_chain == Chain.SOLANA:
            adapter = ProtocolRegistry.get(dex, self._rpc)
            pool = adapter.get_pool(pool_address)
        elif resolved_chain == Chain.ETH:
            adapter = self._get_uniswap_adapter()
            pool = adapter.get_pool_by_address(pool_address)
        elif resolved_chain == Chain.BSC:
            adapter = self._get_pancakeswap_adapter()
            pool = adapter.get_pool_by_address(pool_address)
        else:
            raise OperationNotSupported(f"Unsupported chain: {resolved_chain}")

        if pool is None:
            raise PoolUnavailable.not_found(pool_address)

        return pool

    def pool_by_symbol(
        self,
        symbol: str,
        dex: Optional[str] = None,
        chain: Union[str, Chain] = Chain.SOLANA,
        fee: Optional[int] = None,
    ) -> Optional[Pool]:
        """
        Get pool by trading pair symbol

        Args:
            symbol: Trading pair (e.g., "SOL/USDC", "ETH/USDC")
            dex: Protocol name (uses chain default if not provided)
            chain: Blockchain ("solana", "eth", "bsc" or Chain enum)
            fee: Fee tier for EVM pools (e.g., 500, 3000, 10000 for Uniswap)

        Returns:
            Pool if found, None otherwise
        """
        resolved_chain = self._resolve_chain(chain)

        # Set default dex if not provided
        if dex is None:
            dex = self._get_default_dex(resolved_chain)

        # Validate chain/dex combination
        self._validate_chain_dex(resolved_chain, dex)

        # Normalize symbol
        symbol = symbol.upper().replace("-", "/")

        # Check known pools first
        if dex in KNOWN_POOLS:
            if symbol in KNOWN_POOLS[dex]:
                pool_address = KNOWN_POOLS[dex][symbol]
                return self.pool(pool_address, dex, chain=resolved_chain)
            # Try reversed symbol
            parts = symbol.split("/")
            if len(parts) == 2:
                reversed_symbol = f"{parts[1]}/{parts[0]}"
                if reversed_symbol in KNOWN_POOLS[dex]:
                    pool_address = KNOWN_POOLS[dex][reversed_symbol]
                    return self.pool(pool_address, dex, chain=resolved_chain)

        # Parse symbol and resolve to tokens
        parts = symbol.split("/")
        if len(parts) != 2:
            raise ConfigurationError.invalid("symbol", f"Invalid symbol format: {symbol}. Expected format: TOKEN0/TOKEN1")

        token0_symbol, token1_symbol = parts

        if resolved_chain == Chain.SOLANA:
            # Resolve symbols to mint addresses using Solana registry
            token0_addr = resolve_token_mint(token0_symbol)
            token1_addr = resolve_token_mint(token1_symbol)

            # Try adapter lookup with mints
            adapter = ProtocolRegistry.get(dex, self._rpc)
            pool = adapter.get_pool_by_tokens(token0_addr, token1_addr)

            if pool is None:
                # Try reversed order
                pool = adapter.get_pool_by_tokens(token1_addr, token0_addr)

            return pool

        elif resolved_chain == Chain.ETH:
            adapter = self._get_uniswap_adapter()
            actual_fee = fee if fee is not None else 3000  # Default 0.3% for Uniswap
            pool = adapter.get_pool(token0_symbol, token1_symbol, fee=actual_fee)
            return pool

        elif resolved_chain == Chain.BSC:
            adapter = self._get_pancakeswap_adapter()
            actual_fee = fee if fee is not None else 2500  # Default 0.25% for PancakeSwap
            pool = adapter.get_pool(token0_symbol, token1_symbol, fee=actual_fee)
            return pool

        else:
            raise OperationNotSupported(f"Unsupported chain: {resolved_chain}")

    def resolve_token_mint(self, token: str, chain: Union[str, Chain] = Chain.SOLANA) -> str:
        """
        Resolve token symbol to address (legacy method, use resolve_token instead)

        Args:
            token: Token symbol or address
            chain: Blockchain ("solana", "eth", "bsc" or Chain enum)

        Returns:
            Token address
        """
        return self.resolve_token(token, chain)

    def resolve_token(self, token: str, chain: Union[str, Chain] = Chain.SOLANA) -> str:
        """
        Resolve token symbol to address for any chain

        Args:
            token: Token symbol or address
            chain: Blockchain ("solana", "eth", "bsc" or Chain enum)

        Returns:
            Token address

        Examples:
            sol_mint = market.resolve_token("SOL", chain="solana")
            weth_addr = market.resolve_token("WETH", chain="eth")
            wbnb_addr = market.resolve_token("WBNB", chain="bsc")
        """
        resolved_chain = self._resolve_chain(chain)

        if resolved_chain == Chain.SOLANA:
            return resolve_token_mint(token)
        else:
            return resolve_token_address(token, resolved_chain.chain_id)

    def pools(
        self,
        dex: Optional[str] = None,
        token: Optional[str] = None,
        chain: Union[str, Chain] = Chain.SOLANA,
    ) -> List[Pool]:
        """
        List pools (currently only supported for Solana)

        Args:
            dex: Optional protocol filter
            token: Optional token filter (symbol like "SOL" or mint address)
            chain: Blockchain ("solana", "eth", "bsc" or Chain enum)

        Returns:
            List of pools

        Note:
            EVM chains (eth, bsc) return empty list as pool enumeration
            requires external indexing services not implemented.
        """
        resolved_chain = self._resolve_chain(chain)

        # EVM chains don't support pool enumeration without indexer
        if resolved_chain != Chain.SOLANA:
            logger.warning(f"Pool enumeration not supported for {resolved_chain.value}. Use pool_by_symbol() instead.")
            return []

        pools: List[Pool] = []

        protocols = [dex] if dex else ProtocolRegistry.list()

        # Resolve token symbol to mint address if provided
        token_mint = self.resolve_token(token, chain=resolved_chain) if token else None

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
        dex: Optional[str] = None,
        chain: Union[str, Chain] = Chain.SOLANA,
        fee: Optional[int] = None,
    ) -> Decimal:
        """
        Get current price

        Args:
            pool_or_symbol: Pool address or trading pair symbol
            dex: Protocol name (uses chain default if not provided)
            chain: Blockchain ("solana", "eth", "bsc" or Chain enum)
            fee: Fee tier for EVM pools

        Returns:
            Current price
        """
        resolved_chain = self._resolve_chain(chain)

        # Set default dex if not provided
        if dex is None:
            dex = self._get_default_dex(resolved_chain)

        # Determine if it's a pool address or symbol
        # Solana: base58, ~44 chars; EVM: hex, 42 chars starting with 0x
        is_address = (
            (resolved_chain == Chain.SOLANA and len(pool_or_symbol) > 30)
            or (resolved_chain.is_evm and pool_or_symbol.startswith("0x"))
        )

        if is_address:
            pool = self.pool(pool_or_symbol, dex=dex, chain=resolved_chain)
        else:
            pool = self.pool_by_symbol(pool_or_symbol, dex=dex, chain=resolved_chain, fee=fee)
            if not pool:
                raise PoolUnavailable.not_found(pool_or_symbol)

        return pool.price

    def price_usd(
        self,
        token: str,
        dex: Optional[str] = None,
        chain: Union[str, Chain] = Chain.SOLANA,
    ) -> Optional[Decimal]:
        """
        Get token price in USD

        Args:
            token: Token symbol or mint/address
            dex: Protocol name (uses chain default if not provided)
            chain: Blockchain ("solana", "eth", "bsc" or Chain enum)

        Returns:
            USD price or None
        """
        resolved_chain = self._resolve_chain(chain)

        # Set default dex if not provided
        if dex is None:
            dex = self._get_default_dex(resolved_chain)

        # Try to find a stablecoin pool
        stables = ["USDC", "USDT"]

        for stable in stables:
            try:
                pool = self.pool_by_symbol(f"{token}/{stable}", dex=dex, chain=resolved_chain)
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

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _resolve_chain(self, chain: Union[str, Chain, None]) -> Chain:
        """Resolve chain parameter to Chain enum"""
        if chain is None:
            return Chain.SOLANA  # Default to Solana for backwards compatibility
        if isinstance(chain, Chain):
            return chain
        return Chain.from_string(chain)

    def _get_default_dex(self, chain: Chain) -> str:
        """Get default DEX for a chain"""
        return DEFAULT_DEX_BY_CHAIN.get(chain, "raydium")

    def _validate_chain_dex(self, chain: Chain, dex: str) -> None:
        """
        Validate chain/dex combination

        Raises:
            OperationNotSupported: If dex is not valid for the chain
        """
        valid_dexes = VALID_DEX_BY_CHAIN.get(chain, set())
        if dex not in valid_dexes:
            raise OperationNotSupported(
                f"DEX '{dex}' is not supported on {chain.value}. "
                f"Valid options: {', '.join(sorted(valid_dexes))}"
            )

    def _get_uniswap_adapter(self) -> "UniswapAdapter":
        """Get or create Uniswap adapter for Ethereum"""
        if self._uniswap_adapter is None:
            from ..protocols.uniswap import UniswapAdapter
            self._uniswap_adapter = UniswapAdapter(chain_id=1, signer=None)
        return self._uniswap_adapter

    def _get_pancakeswap_adapter(self) -> "PancakeSwapAdapter":
        """Get or create PancakeSwap adapter for BSC"""
        if self._pancakeswap_adapter is None:
            from ..protocols.pancakeswap import PancakeSwapAdapter
            self._pancakeswap_adapter = PancakeSwapAdapter(chain_id=56, signer=None)
        return self._pancakeswap_adapter

    def close(self):
        """Clean up EVM adapters"""
        if self._uniswap_adapter is not None:
            self._uniswap_adapter.close()
            self._uniswap_adapter = None
        if self._pancakeswap_adapter is not None:
            self._pancakeswap_adapter.close()
            self._pancakeswap_adapter = None

    def __enter__(self) -> "MarketModule":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
