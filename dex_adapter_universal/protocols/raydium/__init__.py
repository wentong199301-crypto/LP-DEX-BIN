"""
Raydium CLMM Protocol Adapter

Provides unified interface for Raydium Concentrated Liquidity Market Maker.

Based on raydium_trading reference implementation.

Key features:
- Token-2022 NFT support (open_position_with_token22_nft)
- Multi-variant close position strategy
- Auto-detection of token programs
- Floor-based tick array alignment
- Proper reward handling with manual overrides
"""

from .adapter import RaydiumAdapter
from .math import (
    tick_to_sqrt_price_x64,
    sqrt_price_x64_to_price,
    price_to_tick,
    tick_to_price,
    get_amounts_from_liquidity,
    get_liquidity_from_amounts,
    one_tick_range,
    get_tick_array_start_index,
)
from .constants import (
    CLMM_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
    TOKEN_2022_PROGRAM_ID,
    WRAPPED_SOL_MINT,
    TICK_ARRAY_SIZE,
    MIN_TICK,
    MAX_TICK,
    DISCRIMINATORS,
    MANUAL_REWARD_OVERRIDES,
)
from .instructions import (
    detect_token_program_for_mint,
    get_associated_token_address,
    build_create_ata_idempotent_instruction,
    derive_tick_array_address,
    derive_protocol_position,
    derive_personal_position,
)

__all__ = [
    # Adapter
    "RaydiumAdapter",
    # Math
    "tick_to_sqrt_price_x64",
    "sqrt_price_x64_to_price",
    "price_to_tick",
    "tick_to_price",
    "get_amounts_from_liquidity",
    "get_liquidity_from_amounts",
    "one_tick_range",
    "get_tick_array_start_index",
    # Constants
    "CLMM_PROGRAM_ID",
    "TOKEN_PROGRAM_ID",
    "TOKEN_2022_PROGRAM_ID",
    "WRAPPED_SOL_MINT",
    "TICK_ARRAY_SIZE",
    "MIN_TICK",
    "MAX_TICK",
    "DISCRIMINATORS",
    "MANUAL_REWARD_OVERRIDES",
    # Utility functions
    "detect_token_program_for_mint",
    "get_associated_token_address",
    "build_create_ata_idempotent_instruction",
    "derive_tick_array_address",
    "derive_protocol_position",
    "derive_personal_position",
]
