"""
Type definitions for DEX Adapter
"""

from .common import Token
from .pool import Pool
from .position import Position
from .price import PriceRange, RangeMode
from .result import TxResult, TxStatus, QuoteResult

# EVM token types
from .evm_tokens import (
    EVMChain,
    EVMToken,
    NATIVE_TOKEN_ADDRESS,
    ETH_TOKEN_ADDRESSES,
    BSC_TOKEN_ADDRESSES,
    get_token_address as get_evm_token_address,
    get_token_decimals as get_evm_token_decimals,
    resolve_token_address as resolve_evm_token_address,
    is_native_token,
    get_native_symbol,
)

__all__ = [
    # Solana types
    "Token",
    "Pool",
    "Position",
    "PriceRange",
    "RangeMode",
    "TxResult",
    "TxStatus",
    "QuoteResult",
    # EVM types
    "EVMChain",
    "EVMToken",
    "NATIVE_TOKEN_ADDRESS",
    "ETH_TOKEN_ADDRESSES",
    "BSC_TOKEN_ADDRESSES",
    "get_evm_token_address",
    "get_evm_token_decimals",
    "resolve_evm_token_address",
    "is_native_token",
    "get_native_symbol",
]
