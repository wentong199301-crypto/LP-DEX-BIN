"""
Jupiter Swap Adapter

Provides swap functionality (not LP - Jupiter is an aggregator).
"""

from decimal import Decimal
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from solders.instruction import Instruction

import logging
import time

from ...types import Pool, Position, PriceRange, TxResult, TxStatus, QuoteResult
from ...types.solana_tokens import KNOWN_TOKEN_MINTS, KNOWN_TOKEN_DECIMALS, resolve_token_mint
from ...infra import RpcClient, TxBuilder, Signer
from ...errors import SignerError, ConfigurationError, RpcError, TransactionError, SlippageExceeded
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

        max_retries = global_config.tx.max_retries
        retry_delay = global_config.tx.retry_delay
        last_error = None

        for attempt in range(max_retries):
            try:
                # Get quote (refresh on retry to get updated price)
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
                    max_retries=1,  # RPC level retry, we handle retries here
                )

                if wait_confirmation:
                    confirmed = self._rpc.confirm_transaction(
                        sig,
                        timeout_seconds=global_config.tx.confirmation_timeout,
                    )
                    if confirmed is True:
                        logger.info(f"Swap successful: {sig}")
                        return TxResult.success(sig)
                    elif confirmed is False:
                        # On-chain failure - check if it's slippage related
                        error_msg = "Transaction failed on-chain"
                        logger.warning(f"Swap failed on-chain: {sig}")
                        return TxResult.failed(error_msg, sig, recoverable=False)
                    else:  # None = timeout
                        logger.warning(f"Swap confirmation timeout: {sig} (attempt {attempt + 1}/{max_retries})")
                        last_error = TransactionError.confirmation_failed(sig, "Confirmation timeout")
                        if attempt < max_retries - 1:
                            time.sleep(retry_delay)
                            continue
                        return TxResult.timeout(sig)
                else:
                    return TxResult(status=TxStatus.PENDING, signature=sig)

            except RpcError as e:
                last_error = e
                logger.warning(f"RPC error (attempt {attempt + 1}/{max_retries}): {e}")
                if e.recoverable and attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                    continue
                return TxResult.failed(
                    f"RPC error: {e.message}",
                    recoverable=e.recoverable,
                    error_code=e.code.value,
                )

            except Exception as e:
                last_error = e
                error_str = str(e).lower()

                # Identify recoverable errors
                is_recoverable = any(keyword in error_str for keyword in [
                    "timeout", "connection", "network", "rate limit",
                    "blockhash", "too many requests", "503", "502", "504"
                ])

                # Identify slippage errors
                is_slippage = any(keyword in error_str for keyword in [
                    "slippage", "price moved", "insufficient output"
                ])

                if is_slippage:
                    logger.warning(f"Slippage error (attempt {attempt + 1}/{max_retries}): {e}")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        continue
                    return TxResult.failed(
                        f"Slippage exceeded: {e}",
                        recoverable=True,
                        error_code="3001",
                    )

                if is_recoverable and attempt < max_retries - 1:
                    logger.warning(f"Recoverable error (attempt {attempt + 1}/{max_retries}): {e}")
                    time.sleep(retry_delay * (attempt + 1))
                    continue

                logger.error(f"Swap failed: {e}")
                return TxResult.failed(
                    str(e),
                    recoverable=is_recoverable,
                )

        # Should not reach here, but just in case
        return TxResult.failed(
            f"Max retries ({max_retries}) exceeded. Last error: {last_error}",
            recoverable=True,
        )

    def execute_quote(
        self,
        quote: QuoteResult,
        wait_confirmation: bool = True,
    ) -> TxResult:
        """
        Execute a previously obtained quote with automatic retry

        Args:
            quote: Quote from quote() method
            wait_confirmation: Wait for confirmation

        Returns:
            TxResult
        """
        if not self._signer:
            raise SignerError.not_configured()

        max_retries = global_config.tx.max_retries
        retry_delay = global_config.tx.retry_delay
        last_error = None

        for attempt in range(max_retries):
            try:
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
                        logger.info(f"Execute quote successful: {sig}")
                        return TxResult.success(sig)
                    elif confirmed is False:
                        return TxResult.failed("Transaction failed on-chain", sig, recoverable=False)
                    else:  # None = timeout
                        logger.warning(f"Confirmation timeout: {sig} (attempt {attempt + 1}/{max_retries})")
                        last_error = "Confirmation timeout"
                        if attempt < max_retries - 1:
                            time.sleep(retry_delay)
                            continue
                        return TxResult.timeout(sig)
                else:
                    return TxResult(status=TxStatus.PENDING, signature=sig)

            except RpcError as e:
                last_error = e
                logger.warning(f"RPC error (attempt {attempt + 1}/{max_retries}): {e}")
                if e.recoverable and attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
                    continue
                return TxResult.failed(
                    f"RPC error: {e.message}",
                    recoverable=e.recoverable,
                    error_code=e.code.value,
                )

            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                is_recoverable = any(keyword in error_str for keyword in [
                    "timeout", "connection", "network", "rate limit",
                    "blockhash", "too many requests", "503", "502", "504"
                ])

                if is_recoverable and attempt < max_retries - 1:
                    logger.warning(f"Recoverable error (attempt {attempt + 1}/{max_retries}): {e}")
                    time.sleep(retry_delay * (attempt + 1))
                    continue

                logger.error(f"Execute quote failed: {e}")
                return TxResult.failed(str(e), recoverable=is_recoverable)

        return TxResult.failed(
            f"Max retries ({max_retries}) exceeded. Last error: {last_error}",
            recoverable=True,
        )

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
