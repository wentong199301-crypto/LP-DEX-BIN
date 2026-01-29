"""
Retry Logic Helper Module

Provides retry functionality for transaction operations across Solana and EVM chains.
Includes structured logging with correlation IDs for transaction tracing.
"""

import logging
import time
import uuid
import contextvars
from typing import Callable, Tuple, Optional, Union

from ..types import TxResult, TxStatus
from ..errors import ErrorCode
from ..config import config as global_config

logger = logging.getLogger(__name__)

# Context variable for correlation ID (thread-safe)
_correlation_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'correlation_id', default=None
)


def generate_correlation_id() -> str:
    """Generate a unique correlation ID for transaction tracing."""
    return uuid.uuid4().hex[:12]


def get_correlation_id() -> Optional[str]:
    """Get the current correlation ID from context."""
    return _correlation_id.get()


def set_correlation_id(correlation_id: Optional[str]) -> contextvars.Token:
    """Set the correlation ID in context. Returns token for reset."""
    return _correlation_id.set(correlation_id)


class CorrelationContext:
    """
    Context manager for correlation ID scoping.

    Usage:
        with CorrelationContext("swap_sol_usdc") as cid:
            logger.info(f"[{cid}] Starting operation")
            result = execute_with_retry(...)
    """

    def __init__(self, prefix: Optional[str] = None):
        """
        Initialize correlation context.

        Args:
            prefix: Optional prefix for the correlation ID (e.g., "swap", "lp")
        """
        self.correlation_id = generate_correlation_id()
        if prefix:
            self.correlation_id = f"{prefix}_{self.correlation_id}"
        self._token: Optional[contextvars.Token] = None

    def __enter__(self) -> str:
        self._token = set_correlation_id(self.correlation_id)
        return self.correlation_id

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._token is not None:
            _correlation_id.reset(self._token)


def _log_with_correlation(
    level: int,
    message: str,
    operation_name: str,
    attempt: Optional[int] = None,
    max_retries: Optional[int] = None,
    **extra
):
    """
    Log message with correlation ID and structured context.

    Args:
        level: Logging level (logging.INFO, logging.WARNING, etc.)
        message: Log message
        operation_name: Name of the operation being executed
        attempt: Current attempt number (1-indexed)
        max_retries: Maximum number of retries
        **extra: Additional context fields
    """
    cid = get_correlation_id()

    # Build structured log message
    parts = []
    if cid:
        parts.append(f"[{cid}]")
    parts.append(f"[{operation_name}]")
    if attempt is not None and max_retries is not None:
        parts.append(f"[{attempt}/{max_retries}]")
    parts.append(message)

    log_message = " ".join(parts)

    # Add extra context for structured logging systems
    extra_context = {
        "correlation_id": cid,
        "operation": operation_name,
        "attempt": attempt,
        "max_retries": max_retries,
        **extra
    }

    logger.log(level, log_message, extra=extra_context)

# Error keywords for classification
RECOVERABLE_KEYWORDS = [
    "timeout", "connection", "network", "rate limit",
    "blockhash", "too many requests", "503", "502", "504",
    "temporarily unavailable", "service unavailable",
    "econnreset", "enotfound", "etimedout",
    "socket hang up", "request failed",
]

SLIPPAGE_KEYWORDS = [
    "slippage", "price moved", "insufficient output",
    "price impact", "price change", "amount out less than minimum",
    "exceeds slippage", "price slippage",
]


def classify_error(error: Exception) -> Tuple[bool, bool, Optional[ErrorCode]]:
    """
    Classify an error to determine if it's recoverable or slippage-related.

    Args:
        error: The exception to classify

    Returns:
        Tuple of (is_recoverable, is_slippage, error_code)
    """
    error_str = str(error).lower()

    # Check for slippage errors first (more specific)
    is_slippage = any(keyword in error_str for keyword in SLIPPAGE_KEYWORDS)
    if is_slippage:
        return True, True, ErrorCode.SLIPPAGE_EXCEEDED

    # Check for recoverable network/timeout errors
    is_recoverable = any(keyword in error_str for keyword in RECOVERABLE_KEYWORDS)

    # Determine error code
    error_code = None
    if is_recoverable:
        if "timeout" in error_str:
            error_code = ErrorCode.RPC_TIMEOUT
        elif any(kw in error_str for kw in ["connection", "network", "socket"]):
            error_code = ErrorCode.RPC_CONNECTION_FAILED
        elif "rate limit" in error_str or "too many requests" in error_str:
            error_code = ErrorCode.RPC_RATE_LIMITED
        else:
            error_code = ErrorCode.RPC_INVALID_RESPONSE

    return is_recoverable, False, error_code


def execute_with_retry(
    operation: Callable[[], TxResult],
    operation_name: str,
    max_retries: Optional[int] = None,
    retry_delay: Optional[float] = None,
    use_swap_config: bool = False,
) -> TxResult:
    """
    Execute an operation with automatic retry for recoverable errors.

    This function wraps transaction building and sending operations,
    providing linear backoff retry on transient failures (2s, 4s, 6s, 8s, 10s...).
    Slippage errors use a fixed delay without backoff.

    Args:
        operation: Callable that returns a TxResult
        operation_name: Name for logging purposes
        max_retries: Maximum retry attempts (defaults based on use_swap_config)
        retry_delay: Base delay between retries in seconds (defaults to config.tx.retry_delay)
        use_swap_config: If True, use swap_max_retries; otherwise use lp_max_retries

    Returns:
        TxResult from the operation

    Example:
        def build_and_send():
            instructions = adapter.build_open_position(...)
            return tx_builder.build_and_send(instructions)

        result = execute_with_retry(build_and_send, "open_position")
    """
    if max_retries is None:
        max_retries = (
            global_config.tx.swap_max_retries if use_swap_config
            else global_config.tx.lp_max_retries
        )
    retry_delay = retry_delay if retry_delay is not None else global_config.tx.retry_delay
    last_error: Optional[Exception] = None

    for attempt in range(max_retries):
        try:
            result = operation()

            # If successful, return immediately
            if result.is_success:
                if attempt > 0:
                    _log_with_correlation(
                        logging.INFO,
                        f"Succeeded after {attempt + 1} attempts",
                        operation_name,
                        attempt + 1,
                        max_retries,
                    )
                return result

            # Check if the result indicates a recoverable error
            if result.recoverable and attempt < max_retries - 1:
                _log_with_correlation(
                    logging.WARNING,
                    f"Recoverable error: {result.error}",
                    operation_name,
                    attempt + 1,
                    max_retries,
                    error=result.error,
                )
                time.sleep(retry_delay * (attempt + 1))  # Linear backoff: 2s, 4s, 6s...
                continue

            # Non-recoverable error or max retries reached
            return result

        except Exception as e:
            last_error = e
            is_recoverable, is_slippage, error_code = classify_error(e)

            # Slippage errors - retry with fresh quote/state
            if is_slippage:
                _log_with_correlation(
                    logging.WARNING,
                    f"Slippage error: {e}",
                    operation_name,
                    attempt + 1,
                    max_retries,
                    error_type="slippage",
                )
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)  # Fixed delay for slippage
                    continue
                return TxResult.failed(
                    f"Slippage exceeded after {max_retries} attempts: {e}",
                    recoverable=True,
                    error_code=error_code,
                )

            # Recoverable network/timeout errors
            if is_recoverable and attempt < max_retries - 1:
                _log_with_correlation(
                    logging.WARNING,
                    f"Recoverable error: {e}",
                    operation_name,
                    attempt + 1,
                    max_retries,
                    error_type="recoverable",
                )
                time.sleep(retry_delay * (attempt + 1))  # Linear backoff: 2s, 4s, 6s...
                continue

            # Non-recoverable error or max retries reached
            _log_with_correlation(
                logging.ERROR,
                f"Failed: {e}",
                operation_name,
                attempt + 1,
                max_retries,
                error_type="fatal",
            )
            return TxResult.failed(
                str(e),
                recoverable=is_recoverable,
                error_code=error_code,
            )

    # Max retries exceeded
    error_msg = f"Max retries ({max_retries}) exceeded"
    if last_error:
        error_msg += f". Last error: {last_error}"

    _log_with_correlation(
        logging.ERROR,
        error_msg,
        operation_name,
        max_retries,
        max_retries,
    )
    return TxResult.failed(error_msg, recoverable=True)


def execute_swap_with_retry(
    build_and_send: Callable[[int], TxResult],
    operation_name: str,
    max_retries: Optional[int] = None,
    retry_delay: Optional[float] = None,
) -> TxResult:
    """
    Execute a swap operation with automatic retry, refreshing quotes on each attempt.

    This is specifically designed for swap operations where:
    - Quotes should be refreshed on retry to get updated prices
    - The operation receives the attempt number to know when to refresh

    Args:
        build_and_send: Callable that takes attempt number (0-indexed) and returns TxResult.
                       Should refresh quote when attempt > 0.
        operation_name: Name for logging purposes
        max_retries: Maximum retry attempts (defaults to config.tx.swap_max_retries)
        retry_delay: Base delay between retries in seconds

    Returns:
        TxResult from the operation

    Example:
        def do_swap(attempt: int) -> TxResult:
            # Get fresh quote on retry
            quote = adapter.quote(from_token, to_token, amount, slippage_bps)
            tx_bytes = api.get_swap_transaction(quote, pubkey)
            signed_tx, _ = signer.sign_transaction(tx_bytes)
            sig = rpc.send_transaction(signed_tx)
            # ... confirmation logic ...
            return TxResult.success(sig)

        result = execute_swap_with_retry(do_swap, "swap(SOL->USDC)")
    """
    max_retries = max_retries if max_retries is not None else global_config.tx.swap_max_retries
    retry_delay = retry_delay if retry_delay is not None else global_config.tx.retry_delay
    last_error: Optional[Exception] = None
    last_signature: Optional[str] = None

    # Import RpcError here to avoid circular imports
    from ..errors import RpcError

    for attempt in range(max_retries):
        try:
            result = build_and_send(attempt)

            # Track signature for timeout reporting
            if result.signature:
                last_signature = result.signature

            # If successful, return immediately
            if result.is_success:
                if attempt > 0:
                    _log_with_correlation(
                        logging.INFO,
                        f"Succeeded after {attempt + 1} attempts",
                        operation_name,
                        attempt + 1,
                        max_retries,
                        signature=result.signature,
                    )
                return result

            # Handle timeout - may want to retry
            if result.is_timeout and attempt < max_retries - 1:
                _log_with_correlation(
                    logging.WARNING,
                    f"Confirmation timeout, will retry with fresh quote",
                    operation_name,
                    attempt + 1,
                    max_retries,
                    signature=result.signature,
                )
                time.sleep(retry_delay)
                continue

            # Check if the result indicates a recoverable error
            if result.recoverable and attempt < max_retries - 1:
                _log_with_correlation(
                    logging.WARNING,
                    f"Recoverable error: {result.error}",
                    operation_name,
                    attempt + 1,
                    max_retries,
                    error=result.error,
                )
                time.sleep(retry_delay * (attempt + 1))
                continue

            # Non-recoverable error or max retries reached
            return result

        except RpcError as e:
            last_error = e
            _log_with_correlation(
                logging.WARNING,
                f"RPC error: {e.message}",
                operation_name,
                attempt + 1,
                max_retries,
                error_type="rpc",
                rpc_code=e.code.value if e.code else None,
            )
            if e.recoverable and attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1))
                continue
            return TxResult.failed(
                f"RPC error: {e.message}",
                recoverable=e.recoverable,
                error_code=e.code,
            )

        except Exception as e:
            last_error = e
            is_recoverable, is_slippage, error_code = classify_error(e)

            # Slippage errors - retry with fresh quote
            if is_slippage:
                _log_with_correlation(
                    logging.WARNING,
                    f"Slippage error: {e}",
                    operation_name,
                    attempt + 1,
                    max_retries,
                    error_type="slippage",
                )
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                return TxResult.failed(
                    f"Slippage exceeded after {max_retries} attempts: {e}",
                    recoverable=True,
                    error_code=error_code,
                )

            # Recoverable network/timeout errors
            if is_recoverable and attempt < max_retries - 1:
                _log_with_correlation(
                    logging.WARNING,
                    f"Recoverable error: {e}",
                    operation_name,
                    attempt + 1,
                    max_retries,
                    error_type="recoverable",
                )
                time.sleep(retry_delay * (attempt + 1))
                continue

            # Non-recoverable error or max retries reached
            _log_with_correlation(
                logging.ERROR,
                f"Failed: {e}",
                operation_name,
                attempt + 1,
                max_retries,
                error_type="fatal",
            )
            return TxResult.failed(
                str(e),
                recoverable=is_recoverable,
                error_code=error_code,
            )

    # Max retries exceeded
    error_msg = f"Max retries ({max_retries}) exceeded"
    if last_error:
        error_msg += f". Last error: {last_error}"

    _log_with_correlation(
        logging.ERROR,
        error_msg,
        operation_name,
        max_retries,
        max_retries,
    )

    # Return timeout if we have a signature (transaction was sent but not confirmed)
    if last_signature:
        return TxResult.timeout(last_signature)
    return TxResult.failed(error_msg, recoverable=True)
