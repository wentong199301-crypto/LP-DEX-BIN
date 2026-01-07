"""
Raydium CLMM Constants

Based on raydium_trading reference implementation.
"""

import hashlib
from typing import Dict, List, Tuple


def _anchor_discriminator(name: str) -> bytes:
    """Compute Anchor discriminator for instruction name"""
    return hashlib.sha256(f"global:{name}".encode("utf-8")).digest()[:8]


def _anchor_account_discriminator(name: str) -> bytes:
    """Compute Anchor discriminator for account name"""
    return hashlib.sha256(f"account:{name}".encode("utf-8")).digest()[:8]


# Raydium CLMM Program ID (mainnet)
CLMM_PROGRAM_ID = "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK"

# Token Programs
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM_ID = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"

# Associated Token Program
ASSOCIATED_TOKEN_PROGRAM_ID = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"

# System Program
SYSTEM_PROGRAM_ID = "11111111111111111111111111111111"

# Rent Sysvar
RENT_SYSVAR_ID = "SysvarRent111111111111111111111111111111111"

# Metadata Program (Metaplex)
METADATA_PROGRAM_ID = "metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s"

# Memo Program
MEMO_PROGRAM_ID = "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr"

# Wrapped SOL mint
WRAPPED_SOL_MINT = "So11111111111111111111111111111111111111112"

# WSOL wrap safety buffer (in lamports = 0.00001 SOL)
# This extra amount covers:
# - Rent-exempt minimum for the WSOL token account
# - Any rounding differences during token transfers
# Prevents "insufficient funds" errors at the margin
WSOL_WRAP_BUFFER_LAMPORTS = 10000

# Tick array size (Raydium CLMM uses 60 ticks per tick array)
TICK_ARRAY_SIZE = 60

# Tick array step calculation: TICK_ARRAY_SIZE * tick_spacing
# For tick_spacing=1: step=60, for tick_spacing=10: step=600, etc.

# Tick bounds
MIN_TICK = -443636
MAX_TICK = 443636

# Q64 constant for fixed-point math
Q64 = 2 ** 64

# Max u128
MAX_UINT128 = 2 ** 128 - 1

# Anchor discriminators for instructions
# Computed as sha256("global:<instruction_name>")[0:8]
DISCRIMINATORS = {
    # Legacy instructions
    "open_position": _anchor_discriminator("open_position"),
    "close_position": _anchor_discriminator("close_position"),
    "increase_liquidity": _anchor_discriminator("increase_liquidity"),
    "decrease_liquidity": _anchor_discriminator("decrease_liquidity"),
    # V2 instructions (with Token-2022 support)
    "open_position_v2": _anchor_discriminator("open_position_v2"),
    "close_position_v2": _anchor_discriminator("close_position_v2"),
    "increase_liquidity_v2": _anchor_discriminator("increase_liquidity_v2"),
    "decrease_liquidity_v2": _anchor_discriminator("decrease_liquidity_v2"),
    # Token-2022 NFT instruction (preferred for opening positions)
    "open_position_with_token22_nft": _anchor_discriminator("open_position_with_token22_nft"),
    # Other instructions
    "collect_remaining_rewards": _anchor_discriminator("collect_remaining_rewards"),
}

# Account discriminators for parsing
ACCOUNT_DISCRIMINATORS = {
    "TickArray": _anchor_account_discriminator("TickArray"),
    "TickArrayState": _anchor_account_discriminator("TickArrayState"),
    "PersonalPosition": _anchor_account_discriminator("PersonalPosition"),
    "PersonalPositionState": _anchor_account_discriminator("PersonalPositionState"),
}

# Set of valid personal position discriminators
PP_DISCRIMINATORS = {
    ACCOUNT_DISCRIMINATORS["PersonalPosition"],
    ACCOUNT_DISCRIMINATORS["PersonalPositionState"],
}

# Set of valid tick array discriminators
TA_DISCRIMINATORS = {
    ACCOUNT_DISCRIMINATORS["TickArray"],
    ACCOUNT_DISCRIMINATORS["TickArrayState"],
}

# Common AMM configs (fee tiers)
AMM_CONFIG_FEE_TIERS = {
    "0.01%": 100,    # 1 bps
    "0.05%": 500,    # 5 bps
    "0.25%": 2500,   # 25 bps
    "1%": 10000,     # 100 bps
}

# Manual reward overrides for pools with non-standard reward configurations
# Format: pool_address -> [(reward_mint, reward_vault), ...]
MANUAL_REWARD_OVERRIDES: Dict[str, List[Tuple[str, str]]] = {
    # Add pool-specific reward overrides here if needed
    # "pool_address": [("reward_mint", "reward_vault"), ...]
}
