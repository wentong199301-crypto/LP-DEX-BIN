"""
Error definitions for DEX Adapter
"""

from .exceptions import (
    ErrorCode,
    DexAdapterError,
    RpcError,
    SlippageExceeded,
    PoolUnavailable,
    InsufficientFunds,
    PositionNotFound,
    TransactionError,
    SignerError,
    ConfigurationError,
    OperationNotSupported,
)

__all__ = [
    "ErrorCode",
    "DexAdapterError",
    "RpcError",
    "SlippageExceeded",
    "PoolUnavailable",
    "InsufficientFunds",
    "PositionNotFound",
    "TransactionError",
    "SignerError",
    "ConfigurationError",
    "OperationNotSupported",
]
