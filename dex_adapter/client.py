"""
DexClient - Unified entry point for DEX operations

Provides high-level interface to interact with Solana DEX protocols
through functional modules (wallet, market, swap, lp).
"""

from __future__ import annotations

from typing import Optional, Union, List, TYPE_CHECKING

if TYPE_CHECKING:
    from solders.keypair import Keypair

from .infra import RpcClient, RpcClientConfig, TxBuilder, TxBuilderConfig, create_signer, Signer
from .protocols import ProtocolRegistry
from .errors import ConfigurationError


class DexClient:
    """
    Unified DEX adapter client

    Provides access to DEX operations through functional modules:
    - wallet: Balance queries, token accounts
    - market: Pool information, prices
    - swap: Token swaps via Jupiter
    - lp: Liquidity operations (open, close, add, remove, claim)

    Usage:
        # Initialize with RPC URL and keypair
        from solders.keypair import Keypair

        keypair = Keypair()
        client = DexClient(
            rpc_url="https://api.mainnet-beta.solana.com",
            keypair=keypair,
        )

        # Or with keypair file path
        client = DexClient(
            rpc_url="https://api.mainnet-beta.solana.com",
            keypair_path="/path/to/keypair.json",
        )

        # Access modules
        balance = client.wallet.balance()
        pools = client.market.pools("raydium")
        position = client.lp.open(pool, price_range, amount_usd=1000)
    """

    def __init__(
        self,
        rpc_url: Union[str, List[str]],
        keypair: Optional["Keypair"] = None,
        keypair_path: Optional[str] = None,
        rpc_config: Optional[RpcClientConfig] = None,
        tx_config: Optional[TxBuilderConfig] = None,
    ):
        """
        Initialize DexClient

        Args:
            rpc_url: RPC endpoint URL or list of URLs for fallback
            keypair: Optional Keypair for local signing
            keypair_path: Optional path to keypair file
            rpc_config: Optional RPC configuration
            tx_config: Optional transaction configuration
        """
        # Initialize RPC client
        self._rpc = RpcClient(rpc_url, config=rpc_config)

        # Initialize signer
        self._signer = create_signer(
            keypair=keypair,
            keypair_path=keypair_path,
        )

        # Initialize transaction builder
        self._tx_builder = TxBuilder(self._rpc, self._signer, config=tx_config)

        # Lazy-loaded modules
        self._wallet: Optional["WalletModule"] = None
        self._market: Optional["MarketModule"] = None
        self._swap: Optional["SwapModule"] = None
        self._lp: Optional["LiquidityModule"] = None

    @property
    def rpc(self) -> RpcClient:
        """Access to RPC client"""
        return self._rpc

    @property
    def signer(self) -> Signer:
        """Access to signer"""
        return self._signer

    @property
    def tx_builder(self) -> TxBuilder:
        """Access to transaction builder"""
        return self._tx_builder

    @property
    def pubkey(self) -> str:
        """Owner's public key"""
        return self._signer.pubkey

    @property
    def wallet(self) -> "WalletModule":
        """
        Wallet module for balance queries

        Provides:
        - balance(token): Get token balance
        - balances(): Get all token balances
        - sol_balance(): Get SOL balance
        - token_accounts(): List token accounts
        """
        if self._wallet is None:
            from .modules.wallet import WalletModule
            self._wallet = WalletModule(self)
        return self._wallet

    @property
    def market(self) -> "MarketModule":
        """
        Market module for pool and price queries

        Provides:
        - pool(address): Get pool by address
        - pool_by_symbol(symbol, dex): Get pool by symbol
        - pools(dex): List pools
        - price(symbol): Get current price
        """
        if self._market is None:
            from .modules.market import MarketModule
            self._market = MarketModule(self)
        return self._market

    @property
    def swap(self) -> "SwapModule":
        """
        Swap module for token exchanges

        Provides:
        - quote(from_token, to_token, amount): Get swap quote
        - execute(quote): Execute swap
        - swap(from_token, to_token, amount): Quote and execute
        """
        if self._swap is None:
            from .modules.swap import SwapModule
            self._swap = SwapModule(self)
        return self._swap

    @property
    def lp(self) -> "LiquidityModule":
        """
        Liquidity module for LP operations

        Provides:
        - open(pool, price_range, ...): Open position
        - close(position): Close position
        - add(position, amount0, amount1): Add liquidity
        - remove(position, percent): Remove liquidity
        - claim(position): Claim fees/rewards
        - positions(owner): List positions
        - get_position(id): Get single position
        """
        if self._lp is None:
            from .modules.liquidity import LiquidityModule
            self._lp = LiquidityModule(self)
        return self._lp

    def get_adapter(self, protocol: str):
        """
        Get protocol adapter

        Args:
            protocol: Protocol name (e.g., "raydium", "meteora")

        Returns:
            ProtocolAdapter instance
        """
        return ProtocolRegistry.get(protocol, self._rpc)

    def close(self):
        """Close client connections and release resources"""
        # Close swap module (includes 1inch adapters for EVM chains)
        if self._swap is not None:
            self._swap.close()
        # Close RPC client
        self._rpc.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __repr__(self) -> str:
        return f"DexClient(endpoint={self._rpc.endpoint}, pubkey={self.pubkey[:8]}...)"


# Type hints for modules (resolved at runtime)
if TYPE_CHECKING:
    from .modules.wallet import WalletModule
    from .modules.market import MarketModule
    from .modules.swap import SwapModule
    from .modules.liquidity import LiquidityModule
