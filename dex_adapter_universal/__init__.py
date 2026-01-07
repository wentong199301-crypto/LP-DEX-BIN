"""
DEX Adapter - Unified interface for Solana and EVM DEX protocols

Provides atomic operations for:
- Raydium CLMM (Solana)
- Meteora DLMM (Solana)
- Jupiter Swap (Solana)
- 1inch Swap (Ethereum/BSC)
- PancakeSwap (BSC/Ethereum)

Multi-chain swap support:
- Solana: Uses Jupiter aggregator
- Ethereum: Uses 1inch or PancakeSwap
- BSC: Uses 1inch or PancakeSwap
"""

from .client import DexClient
from .types import (
    Token,
    Pool,
    Position,
    PriceRange,
    RangeMode,
    TxResult,
    TxStatus,
    QuoteResult,
    # EVM types
    EVMChain,
    EVMToken,
    NATIVE_TOKEN_ADDRESS,
)
from .errors import (
    DexAdapterError,
    RpcError,
    SlippageExceeded,
    PoolUnavailable,
    InsufficientFunds,
    PositionNotFound,
    ErrorCode,
)

# Multi-chain swap
from .modules.swap import SwapModule, Chain

# EVM infrastructure
from .infra.evm_signer import EVMSigner, create_web3, create_evm_signer
from .protocols.oneinch import OneInchAdapter, OneInchAPI
from .protocols.pancakeswap import PancakeSwapAdapter
from .protocols.uniswap import UniswapAdapter

__all__ = [
    # Client
    "DexClient",
    # Types
    "Token",
    "Pool",
    "Position",
    "PriceRange",
    "RangeMode",
    "TxResult",
    "TxStatus",
    "QuoteResult",
    # EVM Types
    "EVMChain",
    "EVMToken",
    "NATIVE_TOKEN_ADDRESS",
    # Errors
    "DexAdapterError",
    "RpcError",
    "SlippageExceeded",
    "PoolUnavailable",
    "InsufficientFunds",
    "PositionNotFound",
    "ErrorCode",
    # Multi-chain swap
    "SwapModule",
    "Chain",
    # EVM infrastructure
    "EVMSigner",
    "create_web3",
    "create_evm_signer",
    "OneInchAdapter",
    "OneInchAPI",
    "PancakeSwapAdapter",
    "UniswapAdapter",
]

__version__ = "1.1.0"
