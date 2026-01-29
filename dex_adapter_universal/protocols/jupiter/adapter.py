"""
Jupiter Swap Adapter

Provides swap functionality (not LP - Jupiter is an aggregator).
Uses consolidated retry logic from infra.retry for automatic retries.
"""

from decimal import Decimal
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from solders.instruction import Instruction

import logging

from ...types import TxResult, TxStatus, QuoteResult
from ...types.solana_tokens import SOLANA_TOKEN_MINTS, SOLANA_TOKEN_DECIMALS
from ...infra import RpcClient, TxBuilder, Signer
from ...infra.retry import execute_swap_with_retry, CorrelationContext
from ...errors import SignerError, ConfigurationError
from ...config import config as global_config

from .api import JupiterAPI

logger = logging.getLogger(__name__)


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
    TOKEN_MINTS = SOLANA_TOKEN_MINTS

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
        self._mint_decimals = SOLANA_TOKEN_DECIMALS.copy()

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
        Execute swap with automatic retry for recoverable errors

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

        operation_name = f"swap({from_token}->{to_token})"

        def do_swap(attempt: int) -> TxResult:
            # Get quote (refresh on each attempt to get updated price)
            quote = self.quote(from_token, to_token, amount, slippage_bps)

            # Get swap transaction with priority fee from config
            tx_bytes = self._api.get_swap_transaction(
                quote=quote,
                user_pubkey=self.pubkey,
                compute_unit_price_micro_lamports=global_config.tx.compute_unit_price,
            )

            # Sign and send
            signed_tx, signature = self._signer.sign_transaction(tx_bytes)

            sig = self._rpc.send_transaction(
                signed_tx,
                skip_preflight=global_config.tx.skip_preflight,
                max_retries=1,  # RPC level retry, we handle retries at higher level
            )

            if wait_confirmation:
                confirmed = self._rpc.confirm_transaction(
                    sig,
                    timeout_seconds=global_config.tx.confirmation_timeout,
                )
                if confirmed is True:
                    fee_lamports = 0
                    try:
                        tx_detail = self._rpc.get_transaction(sig)
                        if tx_detail and tx_detail.get("meta"):
                            fee_lamports = tx_detail["meta"].get("fee", 0)
                    except Exception:
                        pass
                    logger.info(f"Swap successful: {sig}, fee: {fee_lamports} lamports")
                    return TxResult.success(sig, fee_lamports=fee_lamports)
                elif confirmed is False:
                    # On-chain failure - not recoverable
                    return TxResult.failed(
                        "Transaction failed on-chain",
                        signature=sig,
                        recoverable=False,
                    )
                else:  # None = timeout
                    return TxResult.timeout(sig)
            else:
                return TxResult(status=TxStatus.PENDING, signature=sig)

        # Use correlation context for tracing
        with CorrelationContext("swap"):
            return execute_swap_with_retry(do_swap, operation_name)

    def execute_quote(
        self,
        quote: QuoteResult,
        wait_confirmation: bool = True,
    ) -> TxResult:
        """
        Execute a previously obtained quote with automatic retry

        Note: This method does NOT refresh the quote on retry. For swaps where
        you want fresh quotes on each retry, use swap() instead.

        Args:
            quote: Quote from quote() method
            wait_confirmation: Wait for confirmation

        Returns:
            TxResult
        """
        if not self._signer:
            raise SignerError.not_configured()

        operation_name = f"execute_quote({quote.from_token[:8]}...->{quote.to_token[:8]}...)"

        def do_execute(attempt: int) -> TxResult:
            tx_bytes = self._api.get_swap_transaction(
                quote=quote,
                user_pubkey=self.pubkey,
                compute_unit_price_micro_lamports=global_config.tx.compute_unit_price,
            )

            signed_tx, signature = self._signer.sign_transaction(tx_bytes)

            sig = self._rpc.send_transaction(
                signed_tx,
                skip_preflight=global_config.tx.skip_preflight,
                max_retries=1,
            )

            if wait_confirmation:
                confirmed = self._rpc.confirm_transaction(
                    sig,
                    timeout_seconds=global_config.tx.confirmation_timeout,
                )
                if confirmed is True:
                    fee_lamports = 0
                    try:
                        tx_detail = self._rpc.get_transaction(sig)
                        if tx_detail and tx_detail.get("meta"):
                            fee_lamports = tx_detail["meta"].get("fee", 0)
                    except Exception:
                        pass
                    logger.info(f"Execute quote successful: {sig}, fee: {fee_lamports} lamports")
                    return TxResult.success(sig, fee_lamports=fee_lamports)
                elif confirmed is False:
                    return TxResult.failed(
                        "Transaction failed on-chain",
                        signature=sig,
                        recoverable=False,
                    )
                else:  # None = timeout
                    return TxResult.timeout(sig)
            else:
                return TxResult(status=TxStatus.PENDING, signature=sig)

        # Use correlation context for tracing
        with CorrelationContext("execute_quote"):
            return execute_swap_with_retry(do_execute, operation_name)

    def _resolve_mint(self, token: str) -> str:
        """Resolve token symbol or mint to mint address"""
        # Check if it's already a mint address (base58, ~44 chars)
        if len(token) > 30:
            return token

        # Look up common symbols using centralized registry
        upper = token.upper()
        if upper in SOLANA_TOKEN_MINTS:
            return SOLANA_TOKEN_MINTS[upper]

        raise ConfigurationError.invalid(
            "token",
            f"Unknown token symbol: {token}. Provide mint address or add to SOLANA_TOKEN_MINTS."
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
