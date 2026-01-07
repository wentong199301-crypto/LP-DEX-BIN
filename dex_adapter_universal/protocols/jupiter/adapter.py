"""
Jupiter Swap Adapter

Provides swap functionality (not LP - Jupiter is an aggregator).
"""

from decimal import Decimal
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from solders.instruction import Instruction

from ...types import Pool, Position, PriceRange, TxResult, TxStatus, QuoteResult
from ...types.solana_tokens import KNOWN_TOKEN_MINTS, KNOWN_TOKEN_DECIMALS, resolve_token_mint
from ...infra import RpcClient, TxBuilder, Signer
from ...errors import SignerError, ConfigurationError

from .api import JupiterAPI


class JupiterAdapter:
    """
    Jupiter Swap Adapter

    Jupiter is a swap aggregator, not a DEX with LP.
    This adapter provides swap functionality only.

    Usage:
        rpc = RpcClient("https://api.mainnet-beta.solana.com")
        signer = LocalSigner(keypair)
        adapter = JupiterAdapter(rpc, signer)

        quote = adapter.quote("SOL", "USDC", Decimal("1.0"))
        result = adapter.swap("SOL", "USDC", Decimal("1.0"))
    """

    name = "jupiter"

    # Use centralized token registry
    TOKEN_MINTS = KNOWN_TOKEN_MINTS

    def __init__(
        self,
        rpc: RpcClient,
        signer: Optional[Signer] = None,
        tx_builder: Optional[TxBuilder] = None,
    ):
        """
        Initialize Jupiter adapter

        Args:
            rpc: RPC client
            signer: Optional signer for executing swaps
            tx_builder: Optional transaction builder
        """
        self._rpc = rpc
        self._signer = signer
        self._tx_builder = tx_builder
        self._api = JupiterAPI()
        # Instance-level cache for token decimals to avoid class-level mutation
        self._mint_decimals = KNOWN_TOKEN_DECIMALS.copy()

    @property
    def pubkey(self) -> Optional[str]:
        """Signer public key if available"""
        return self._signer.pubkey if self._signer else None

    def quote(
        self,
        from_token: str,
        to_token: str,
        amount: Decimal,
        slippage_bps: int = 50,
    ) -> QuoteResult:
        """
        Get swap quote

        Args:
            from_token: Input token (symbol or mint)
            to_token: Output token (symbol or mint)
            amount: Amount in UI units (e.g., 1.5 SOL)
            slippage_bps: Slippage tolerance

        Returns:
            QuoteResult with swap details
        """
        # Resolve token mints
        from_mint = self._resolve_mint(from_token)
        to_mint = self._resolve_mint(to_token)

        # Get decimals (simplified - should fetch from chain)
        from_decimals = self._get_decimals(from_token)

        # Convert to raw amount
        raw_amount = int(amount * Decimal(10 ** from_decimals))

        return self._api.get_quote(
            input_mint=from_mint,
            output_mint=to_mint,
            amount=raw_amount,
            slippage_bps=slippage_bps,
        )

    def swap(
        self,
        from_token: str,
        to_token: str,
        amount: Decimal,
        slippage_bps: int = 50,
        wait_confirmation: bool = True,
    ) -> TxResult:
        """
        Execute swap

        Args:
            from_token: Input token (symbol or mint)
            to_token: Output token (symbol or mint)
            amount: Amount in UI units
            slippage_bps: Slippage tolerance
            wait_confirmation: Wait for transaction confirmation

        Returns:
            TxResult with transaction status
        """
        if not self._signer:
            raise SignerError.not_configured()

        # Get quote
        quote = self.quote(from_token, to_token, amount, slippage_bps)

        # Get swap transaction with priority fee from config
        from ...config import config as global_config
        tx_bytes = self._api.get_swap_transaction(
            quote=quote,
            user_pubkey=self.pubkey,
            compute_unit_price_micro_lamports=global_config.tx.compute_unit_price,
        )

        # Sign and send
        signed_tx, signature = self._signer.sign_transaction(tx_bytes)

        # Send via RPC with retries (like TypeScript reference)
        try:
            sig = self._rpc.send_transaction(
                signed_tx,
                skip_preflight=False,
                max_retries=3,
            )

            if wait_confirmation:
                confirmed = self._rpc.confirm_transaction(sig)
                if confirmed is True:
                    return TxResult.success(sig)
                elif confirmed is False:
                    return TxResult.failed("Transaction failed on-chain", sig)
                else:  # None = timeout
                    return TxResult.timeout(sig)
            else:
                return TxResult(
                    status=TxStatus.PENDING,
                    signature=sig,
                )

        except Exception as e:
            return TxResult.failed(str(e))

    def execute_quote(
        self,
        quote: QuoteResult,
        wait_confirmation: bool = True,
    ) -> TxResult:
        """
        Execute a previously obtained quote

        Args:
            quote: Quote from quote() method
            wait_confirmation: Wait for confirmation

        Returns:
            TxResult
        """
        if not self._signer:
            raise SignerError.not_configured()

        from ...config import config as global_config
        tx_bytes = self._api.get_swap_transaction(
            quote=quote,
            user_pubkey=self.pubkey,
            compute_unit_price_micro_lamports=global_config.tx.compute_unit_price,
        )

        signed_tx, signature = self._signer.sign_transaction(tx_bytes)

        try:
            sig = self._rpc.send_transaction(signed_tx, skip_preflight=False, max_retries=3)

            if wait_confirmation:
                confirmed = self._rpc.confirm_transaction(sig)
                if confirmed is True:
                    return TxResult.success(sig)
                elif confirmed is False:
                    return TxResult.failed("Transaction failed on-chain", sig)
                else:  # None = timeout
                    return TxResult.timeout(sig)
            else:
                return TxResult(status=TxStatus.PENDING, signature=sig)

        except Exception as e:
            return TxResult.failed(str(e))

    def _resolve_mint(self, token: str) -> str:
        """Resolve token symbol or mint to mint address"""
        # Check if it's already a mint address (base58, ~44 chars)
        if len(token) > 30:
            return token

        # Look up common symbols using centralized registry
        upper = token.upper()
        if upper in KNOWN_TOKEN_MINTS:
            return KNOWN_TOKEN_MINTS[upper]

        raise ConfigurationError.invalid(
            "token",
            f"Unknown token symbol: {token}. Provide mint address or add to KNOWN_TOKEN_MINTS."
        )

    def _get_decimals(self, token: str) -> int:
        """
        Get token decimals

        For known symbols, resolves to mint and looks up decimals.
        For mint addresses, looks up in MINT_DECIMALS or fetches from chain.
        """
        # Check if it's a symbol (short string)
        if len(token) < 30:
            # Resolve symbol to mint address first
            mint = self._resolve_mint(token)
            return self._get_decimals_for_mint(mint)

        # It's a mint address
        return self._get_decimals_for_mint(token)

    def _get_decimals_for_mint(self, mint: str) -> int:
        """
        Get decimals for a mint address

        Note: This duplicates similar caching in MeteoraAdapter. A shared
        utility could consolidate this, but would require mixing types
        layer with infrastructure dependencies.
        """
        # Check instance cache first
        if mint in self._mint_decimals:
            return self._mint_decimals[mint]

        # Fetch from chain
        try:
            account = self._rpc.get_account_info(mint, encoding="jsonParsed")
            if account:
                data = account.get("data", {})
                # Support both spl-token and spl-token-2022 (Token-2022) programs
                if isinstance(data, dict) and data.get("program") in ("spl-token", "spl-token-2022"):
                    parsed = data.get("parsed", {}).get("info", {})
                    decimals = parsed.get("decimals")
                    if decimals is not None:
                        # Cache in instance for future use
                        self._mint_decimals[mint] = decimals
                        return decimals
        except Exception:
            pass

        # Fallback to 9 (SOL-like) with warning
        import logging
        logging.getLogger(__name__).warning(
            f"Could not determine decimals for mint {mint}, defaulting to 9"
        )
        return 9

    def close(self):
        """Close API client"""
        self._api.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
