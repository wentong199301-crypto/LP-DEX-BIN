"""
Swap Module

Provides token swap operations across multiple chains:
- Solana: Uses Jupiter aggregator
- Ethereum: Uses 1inch aggregator
- BSC: Uses 1inch aggregator
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Optional, Union

if TYPE_CHECKING:
    from ..client import DexClient

from ..types import QuoteResult, TxResult
from ..protocols.jupiter import JupiterAdapter
from ..protocols.oneinch import OneInchAdapter
from ..infra.evm_signer import EVMSigner, create_web3
from ..errors import ConfigurationError, OperationNotSupported
from ..config import config


class Chain(Enum):
    """Supported blockchain networks"""
    SOLANA = "solana"
    ETH = "eth"
    BSC = "bsc"

    @classmethod
    def from_string(cls, value: str) -> "Chain":
        """Convert string to Chain enum (case-insensitive)"""
        value_lower = value.lower()
        if value_lower in ("solana", "sol"):
            return cls.SOLANA
        elif value_lower in ("eth", "ethereum", "1"):
            return cls.ETH
        elif value_lower in ("bsc", "bnb", "56"):
            return cls.BSC
        else:
            raise ConfigurationError.invalid("chain", f"Unknown chain: {value}. Supported: solana, eth, bsc")

    @property
    def chain_id(self) -> Optional[int]:
        """Get EVM chain ID (None for Solana)"""
        if self == Chain.ETH:
            return 1
        elif self == Chain.BSC:
            return 56
        return None

    @property
    def is_evm(self) -> bool:
        """Check if this is an EVM chain"""
        return self in (Chain.ETH, Chain.BSC)

    @property
    def native_token(self) -> str:
        """Get native token symbol"""
        if self == Chain.SOLANA:
            return "SOL"
        elif self == Chain.ETH:
            return "ETH"
        elif self == Chain.BSC:
            return "BNB"
        return "ETH"

    @property
    def aggregator(self) -> str:
        """Get aggregator name for this chain"""
        if self == Chain.SOLANA:
            return "Jupiter"
        return "1inch"


class SwapModule:
    """
    Multi-chain token swap module

    Supports swapping tokens on:
    - Solana (via Jupiter aggregator)
    - Ethereum (via 1inch aggregator)
    - BSC (via 1inch aggregator)

    Usage:
        # Solana swap (default)
        result = client.swap.swap("SOL", "USDC", Decimal("1.0"), chain="solana")

        # Ethereum swap
        result = client.swap.swap("ETH", "USDC", Decimal("1.0"), chain="eth")

        # BSC swap
        result = client.swap.swap("BNB", "USDT", Decimal("1.0"), chain="bsc")
    """

    def __init__(
        self,
        client: Optional["DexClient"] = None,
        evm_signer: Optional[EVMSigner] = None,
    ):
        """
        Initialize swap module

        Args:
            client: DexClient instance (required for Solana swaps)
            evm_signer: EVMSigner instance (required for EVM swaps)
        """
        self._client = client
        self._evm_signer = evm_signer

        # Lazy-initialized adapters
        self._jupiter_adapter: Optional[JupiterAdapter] = None
        self._oneinch_adapters: dict[int, OneInchAdapter] = {}

    def _get_jupiter_adapter(self) -> JupiterAdapter:
        """Get or create Jupiter adapter for Solana"""
        if self._jupiter_adapter is None:
            if self._client is None:
                raise ConfigurationError.missing(
                    "DexClient (required for Solana swaps - initialize SwapModule with client parameter)"
                )
            self._jupiter_adapter = JupiterAdapter(
                self._client.rpc,
                self._client.signer,
                self._client.tx_builder,
            )
        return self._jupiter_adapter

    def _get_oneinch_adapter(self, chain_id: int, require_signer: bool = False) -> OneInchAdapter:
        """Get or create 1inch adapter for EVM chain

        Args:
            chain_id: EVM chain ID (1 for ETH, 56 for BSC)
            require_signer: If True, raise error when signer is missing (for swaps)
        """
        if require_signer and self._evm_signer is None:
            chain_name = "Ethereum" if chain_id == 1 else "BSC"
            raise ConfigurationError.missing(
                "evm_signer",
                f"EVM signer required for {chain_name} swaps. "
                "Initialize SwapModule with evm_signer parameter or set EVM_PRIVATE_KEY environment variable."
            )

        if chain_id not in self._oneinch_adapters:
            self._oneinch_adapters[chain_id] = OneInchAdapter(
                chain_id=chain_id,
                signer=self._evm_signer,
            )
        return self._oneinch_adapters[chain_id]

    def _resolve_chain(self, chain: Union[str, Chain, None]) -> Chain:
        """Resolve chain parameter to Chain enum"""
        if chain is None:
            return Chain.SOLANA  # Default to Solana for backwards compatibility
        if isinstance(chain, Chain):
            return chain
        return Chain.from_string(chain)

    def quote(
        self,
        from_token: str,
        to_token: str,
        amount: Decimal,
        slippage_bps: Optional[int] = None,
        chain: Union[str, Chain] = Chain.SOLANA,
    ) -> QuoteResult:
        """
        Get swap quote

        Args:
            from_token: Input token (symbol or address)
            to_token: Output token (symbol or address)
            amount: Amount in UI units (e.g., 1.5 for 1.5 tokens)
            slippage_bps: Slippage tolerance in basis points (50 = 0.5%)
            chain: Blockchain to swap on ("solana", "eth", "bsc" or Chain enum)

        Returns:
            QuoteResult with swap details

        Examples:
            # Solana
            quote = swap.quote("SOL", "USDC", Decimal("1.0"), chain="solana")

            # Ethereum
            quote = swap.quote("ETH", "USDC", Decimal("0.5"), chain="eth")

            # BSC
            quote = swap.quote("BNB", "USDT", Decimal("1.0"), chain="bsc")
        """
        resolved_chain = self._resolve_chain(chain)
        actual_slippage = slippage_bps if slippage_bps is not None else config.trading.default_slippage_bps

        if resolved_chain == Chain.SOLANA:
            adapter = self._get_jupiter_adapter()
        else:
            adapter = self._get_oneinch_adapter(resolved_chain.chain_id)

        return adapter.quote(
            from_token=from_token,
            to_token=to_token,
            amount=amount,
            slippage_bps=actual_slippage,
        )

    def execute(
        self,
        quote: QuoteResult,
        wait_confirmation: bool = True,
        chain: Union[str, Chain] = Chain.SOLANA,
    ) -> TxResult:
        """
        Execute a swap quote

        Args:
            quote: Quote from quote() method
            wait_confirmation: Wait for transaction confirmation
            chain: Blockchain the quote was for ("solana", "eth", "bsc")

        Returns:
            TxResult with transaction status
        """
        resolved_chain = self._resolve_chain(chain)

        if resolved_chain == Chain.SOLANA:
            adapter = self._get_jupiter_adapter()
        else:
            adapter = self._get_oneinch_adapter(resolved_chain.chain_id, require_signer=True)

        return adapter.execute_quote(
            quote=quote,
            wait_confirmation=wait_confirmation,
        )

    def swap(
        self,
        from_token: str,
        to_token: str,
        amount: Decimal,
        slippage_bps: Optional[int] = None,
        wait_confirmation: bool = True,
        chain: Union[str, Chain] = Chain.SOLANA,
    ) -> TxResult:
        """
        Quote and execute swap in one call

        Args:
            from_token: Input token (symbol or address)
            to_token: Output token (symbol or address)
            amount: Amount in UI units
            slippage_bps: Slippage tolerance in basis points
            wait_confirmation: Wait for confirmation
            chain: Blockchain to swap on ("solana", "eth", "bsc")

        Returns:
            TxResult with transaction status

        Examples:
            # Swap on Solana (uses Jupiter)
            result = swap.swap("SOL", "USDC", Decimal("1.0"), chain="solana")

            # Swap on Ethereum (uses 1inch)
            result = swap.swap("ETH", "USDC", Decimal("0.5"), chain="eth")

            # Swap on BSC (uses 1inch)
            result = swap.swap("BNB", "USDT", Decimal("1.0"), chain="bsc")
        """
        resolved_chain = self._resolve_chain(chain)
        actual_slippage = slippage_bps if slippage_bps is not None else config.trading.default_slippage_bps

        if resolved_chain == Chain.SOLANA:
            adapter = self._get_jupiter_adapter()
        else:
            adapter = self._get_oneinch_adapter(resolved_chain.chain_id, require_signer=True)

        return adapter.swap(
            from_token=from_token,
            to_token=to_token,
            amount=amount,
            slippage_bps=actual_slippage,
            wait_confirmation=wait_confirmation,
        )

    def estimate_output(
        self,
        from_token: str,
        to_token: str,
        amount: Decimal,
        chain: Union[str, Chain] = Chain.SOLANA,
    ) -> Decimal:
        """
        Estimate output amount without slippage

        Args:
            from_token: Input token
            to_token: Output token
            amount: Input amount
            chain: Blockchain to swap on

        Returns:
            Estimated output amount in raw units
        """
        quote = self.quote(from_token, to_token, amount, slippage_bps=0, chain=chain)
        return Decimal(quote.to_amount)

    def price_impact(
        self,
        from_token: str,
        to_token: str,
        amount: Decimal,
        chain: Union[str, Chain] = Chain.SOLANA,
    ) -> float:
        """
        Get price impact for a swap

        Args:
            from_token: Input token
            to_token: Output token
            amount: Input amount
            chain: Blockchain to swap on

        Returns:
            Price impact as percentage
        """
        quote = self.quote(from_token, to_token, amount, chain=chain)
        return quote.price_impact_percent

    def get_supported_chains(self) -> list[Chain]:
        """Get list of supported chains"""
        return [Chain.SOLANA, Chain.ETH, Chain.BSC]

    def get_aggregator(self, chain: Union[str, Chain]) -> str:
        """
        Get aggregator name for a chain

        Args:
            chain: Blockchain

        Returns:
            Aggregator name ("Jupiter" or "1inch")
        """
        resolved_chain = self._resolve_chain(chain)
        return resolved_chain.aggregator

    def set_evm_signer(self, signer: EVMSigner) -> None:
        """
        Set EVM signer for ETH/BSC swaps

        Args:
            signer: EVMSigner instance
        """
        self._evm_signer = signer
        # Clear cached adapters so they use new signer
        self._oneinch_adapters.clear()

    def close(self):
        """Close all adapters and release resources"""
        for adapter in self._oneinch_adapters.values():
            adapter.close()
        self._oneinch_adapters.clear()

    def __enter__(self) -> "SwapModule":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
