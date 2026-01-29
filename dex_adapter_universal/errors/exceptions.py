"""
Exception definitions for DEX Adapter
"""

from enum import Enum
from typing import Optional
from decimal import Decimal


class ErrorCode(Enum):
    """
    Unified error codes for DEX operations

    1xxx - RPC errors
    2xxx - Transaction errors
    3xxx - Slippage/Price errors
    4xxx - Pool errors
    5xxx - Position errors
    6xxx - Signer errors
    7xxx - Operation errors
    9xxx - Configuration errors
    """
    # RPC errors (recoverable)
    RPC_CONNECTION_FAILED = "1001"
    RPC_TIMEOUT = "1002"
    RPC_RATE_LIMITED = "1003"
    RPC_INVALID_RESPONSE = "1004"

    # Transaction errors
    TX_SIMULATION_FAILED = "2001"
    TX_SEND_FAILED = "2002"
    TX_CONFIRMATION_FAILED = "2003"
    TX_INSUFFICIENT_FUNDS = "2004"
    TX_INVALID_BLOCKHASH = "2005"

    # Slippage/Price errors (recoverable)
    SLIPPAGE_EXCEEDED = "3001"
    PRICE_MOVED = "3002"
    LIQUIDITY_INSUFFICIENT = "3003"

    # Pool errors
    POOL_NOT_FOUND = "4001"
    POOL_UNAVAILABLE = "4002"
    POOL_INVALID_STATE = "4003"

    # Position errors
    POSITION_NOT_FOUND = "5001"
    POSITION_OUT_OF_RANGE = "5002"
    POSITION_ALREADY_CLOSED = "5003"

    # Signer errors
    SIGNER_NOT_CONFIGURED = "6001"
    SIGNER_FAILED = "6002"
    SIGNER_TIMEOUT = "6003"

    # Operation errors
    OPERATION_NOT_SUPPORTED = "7001"
    OPERATION_FAILED = "7002"

    # Configuration errors
    CONFIG_INVALID = "9001"
    CONFIG_MISSING = "9002"


class DexAdapterError(Exception):
    """
    Base exception for all DEX adapter errors

    Attributes:
        message: Human-readable error message
        code: Error code for programmatic handling
        recoverable: Whether the error might succeed on retry
        original_error: The underlying exception if any
        details: Additional error context
    """

    def __init__(
        self,
        message: str,
        code: ErrorCode,
        recoverable: bool = False,
        original_error: Optional[Exception] = None,
        details: Optional[dict] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.recoverable = recoverable
        self.original_error = original_error
        self.details = details or {}

    def __str__(self) -> str:
        return f"[{self.code.value}] {self.message}"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(code={self.code.value}, message={self.message!r})"

    @property
    def should_retry(self) -> bool:
        """Indicate if the operation should be retried"""
        return self.recoverable


class RpcError(DexAdapterError):
    """
    RPC-related errors - typically recoverable

    Raised when:
    - Connection to RPC endpoint fails
    - Request times out
    - Rate limit is hit
    - Invalid response received
    """

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.RPC_CONNECTION_FAILED,
        original_error: Optional[Exception] = None,
        endpoint: Optional[str] = None,
    ):
        super().__init__(
            message,
            code,
            recoverable=True,
            original_error=original_error,
            details={"endpoint": endpoint} if endpoint else None,
        )
        self.endpoint = endpoint

    @classmethod
    def connection_failed(cls, endpoint: str, error: Exception = None) -> "RpcError":
        return cls(
            f"Failed to connect to RPC endpoint: {endpoint}",
            ErrorCode.RPC_CONNECTION_FAILED,
            original_error=error,
            endpoint=endpoint,
        )

    @classmethod
    def timeout(cls, endpoint: str, timeout_seconds: float) -> "RpcError":
        return cls(
            f"RPC request timed out after {timeout_seconds}s",
            ErrorCode.RPC_TIMEOUT,
            endpoint=endpoint,
        )

    @classmethod
    def rate_limited(cls, endpoint: str) -> "RpcError":
        return cls(
            "RPC rate limit exceeded",
            ErrorCode.RPC_RATE_LIMITED,
            endpoint=endpoint,
        )


class SlippageExceeded(DexAdapterError):
    """
    Slippage tolerance exceeded - recoverable with retry

    Raised when:
    - Actual price differs from expected by more than slippage tolerance
    - Market moved during transaction execution
    """

    def __init__(
        self,
        message: str,
        expected: Optional[Decimal] = None,
        actual: Optional[Decimal] = None,
        slippage_bps: Optional[int] = None,
    ):
        super().__init__(
            message,
            ErrorCode.SLIPPAGE_EXCEEDED,
            recoverable=True,
            details={
                "expected": str(expected) if expected else None,
                "actual": str(actual) if actual else None,
                "slippage_bps": slippage_bps,
            },
        )
        self.expected = expected
        self.actual = actual
        self.slippage_bps = slippage_bps

    @classmethod
    def price_moved(cls, expected: Decimal, actual: Decimal, slippage_bps: int) -> "SlippageExceeded":
        if expected == 0:
            diff_bps = float('inf') if actual != 0 else 0
        else:
            diff_bps = abs(float((actual - expected) / expected * 10000))
        return cls(
            f"Price moved beyond slippage tolerance: expected {expected}, got {actual} (diff: {diff_bps:.0f} bps, limit: {slippage_bps} bps)",
            expected=expected,
            actual=actual,
            slippage_bps=slippage_bps,
        )


class PoolUnavailable(DexAdapterError):
    """
    Pool not available - not recoverable

    Raised when:
    - Pool address not found on chain
    - Pool is paused or disabled
    - Pool has invalid state
    """

    def __init__(
        self,
        message: str,
        pool_address: Optional[str] = None,
        code: ErrorCode = ErrorCode.POOL_UNAVAILABLE,
    ):
        super().__init__(
            message,
            code,
            recoverable=False,
            details={"pool_address": pool_address},
        )
        self.pool_address = pool_address

    @classmethod
    def not_found(cls, pool_address: str) -> "PoolUnavailable":
        return cls(
            f"Pool not found: {pool_address}",
            pool_address=pool_address,
            code=ErrorCode.POOL_NOT_FOUND,
        )

    @classmethod
    def invalid_state(cls, pool_address: str, reason: str) -> "PoolUnavailable":
        return cls(
            f"Pool has invalid state: {reason}",
            pool_address=pool_address,
            code=ErrorCode.POOL_INVALID_STATE,
        )


class InsufficientFunds(DexAdapterError):
    """
    Insufficient balance - not recoverable without deposit

    Raised when:
    - Wallet doesn't have enough tokens
    - SOL balance too low for fees
    """

    def __init__(
        self,
        message: str,
        token: Optional[str] = None,
        required: Optional[Decimal] = None,
        available: Optional[Decimal] = None,
    ):
        super().__init__(
            message,
            ErrorCode.TX_INSUFFICIENT_FUNDS,
            recoverable=False,
            details={
                "token": token,
                "required": str(required) if required else None,
                "available": str(available) if available else None,
            },
        )
        self.token = token
        self.required = required
        self.available = available

    @classmethod
    def token_balance(cls, token: str, required: Decimal, available: Decimal) -> "InsufficientFunds":
        return cls(
            f"Insufficient {token} balance: need {required}, have {available}",
            token=token,
            required=required,
            available=available,
        )

    @classmethod
    def sol_for_fees(cls, required_lamports: int, available_lamports: int) -> "InsufficientFunds":
        return cls(
            f"Insufficient SOL for fees: need {required_lamports/1e9:.6f} SOL, have {available_lamports/1e9:.6f} SOL",
            token="SOL",
            required=Decimal(required_lamports) / Decimal(1e9),
            available=Decimal(available_lamports) / Decimal(1e9),
        )


class PositionNotFound(DexAdapterError):
    """
    Position not found - not recoverable

    Raised when:
    - Position ID/address doesn't exist
    - Position was already closed
    """

    def __init__(
        self,
        message: str,
        position_id: Optional[str] = None,
        code: ErrorCode = ErrorCode.POSITION_NOT_FOUND,
    ):
        super().__init__(
            message,
            code,
            recoverable=False,
            details={"position_id": position_id},
        )
        self.position_id = position_id

    @classmethod
    def not_found(cls, position_id: str) -> "PositionNotFound":
        return cls(
            f"Position not found: {position_id}",
            position_id=position_id,
        )

    @classmethod
    def already_closed(cls, position_id: str) -> "PositionNotFound":
        return cls(
            f"Position already closed: {position_id}",
            position_id=position_id,
            code=ErrorCode.POSITION_ALREADY_CLOSED,
        )


class TransactionError(DexAdapterError):
    """
    Transaction execution errors

    Raised when:
    - Transaction simulation fails
    - Transaction send fails
    - Confirmation fails
    """

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.TX_SEND_FAILED,
        signature: Optional[str] = None,
        logs: Optional[list] = None,
        recoverable: bool = False,
    ):
        super().__init__(
            message,
            code,
            recoverable=recoverable,
            details={"signature": signature, "logs": logs},
        )
        self.signature = signature
        self.logs = logs or []

    @classmethod
    def simulation_failed(cls, error: str, logs: list = None) -> "TransactionError":
        return cls(
            f"Transaction simulation failed: {error}",
            ErrorCode.TX_SIMULATION_FAILED,
            logs=logs,
            recoverable=False,
        )

    @classmethod
    def send_failed(cls, error: str) -> "TransactionError":
        # Some send failures are recoverable (network issues)
        recoverable = "timeout" in error.lower() or "connection" in error.lower()
        return cls(
            f"Failed to send transaction: {error}",
            ErrorCode.TX_SEND_FAILED,
            recoverable=recoverable,
        )

    @classmethod
    def confirmation_failed(cls, signature: str, error: str) -> "TransactionError":
        return cls(
            f"Transaction confirmation failed: {error}",
            ErrorCode.TX_CONFIRMATION_FAILED,
            signature=signature,
            recoverable=True,
        )


class SignerError(DexAdapterError):
    """
    Signing-related errors

    Raised when:
    - No signer configured
    - Signing operation fails
    - Remote signer unavailable
    """

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.SIGNER_FAILED,
        recoverable: bool = False,
    ):
        super().__init__(message, code, recoverable=recoverable)

    @classmethod
    def not_configured(cls) -> "SignerError":
        return cls(
            "No signer configured. Provide keypair or remote signer URL.",
            ErrorCode.SIGNER_NOT_CONFIGURED,
        )

    @classmethod
    def failed(cls, reason: str) -> "SignerError":
        return cls(f"Signing failed: {reason}", ErrorCode.SIGNER_FAILED)

    @classmethod
    def timeout(cls) -> "SignerError":
        return cls(
            "Remote signer timed out",
            ErrorCode.SIGNER_TIMEOUT,
            recoverable=True,
        )


class ConfigurationError(DexAdapterError):
    """
    Configuration-related errors

    Raised when:
    - Required configuration is missing
    - Configuration values are invalid
    """

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.CONFIG_INVALID,
    ):
        super().__init__(message, code, recoverable=False)

    @classmethod
    def missing(cls, param: str) -> "ConfigurationError":
        return cls(f"Missing required configuration: {param}", ErrorCode.CONFIG_MISSING)

    @classmethod
    def invalid(cls, param: str, reason: str) -> "ConfigurationError":
        return cls(f"Invalid configuration '{param}': {reason}", ErrorCode.CONFIG_INVALID)


class OperationNotSupported(DexAdapterError):
    """
    Operation not supported by the adapter

    Raised when:
    - A method is not implemented for a specific protocol
    - An operation is not available for the current pool type
    """

    def __init__(
        self,
        message: str,
        operation: Optional[str] = None,
        protocol: Optional[str] = None,
    ):
        super().__init__(
            message,
            ErrorCode.OPERATION_NOT_SUPPORTED,
            recoverable=False,
            details={"operation": operation, "protocol": protocol},
        )
        self.operation = operation
        self.protocol = protocol

    @classmethod
    def not_implemented(cls, operation: str, protocol: str) -> "OperationNotSupported":
        return cls(
            f"Operation '{operation}' is not supported by {protocol} adapter",
            operation=operation,
            protocol=protocol,
        )
