"""
Type definitions for DEX Adapter
"""

from .common import Token, STABLECOINS
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

# Pool registry
from .pool import (
    KNOWN_POOLS,
    RAYDIUM_POOLS,
    METEORA_POOLS,
    UNISWAP_POOLS,
    PANCAKESWAP_POOLS,
    get_pool_address,
    list_pools,
    list_dexes,
)

__all__ = [
    # Common types
    "Token",
    "STABLECOINS",
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
    # Pool registry
    "KNOWN_POOLS",
    "RAYDIUM_POOLS",
    "METEORA_POOLS",
    "UNISWAP_POOLS",
    "PANCAKESWAP_POOLS",
    "get_pool_address",
    "list_pools",
    "list_dexes",
]
