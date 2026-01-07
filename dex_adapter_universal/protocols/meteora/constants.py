"""
Meteora DLMM Constants
"""

# Meteora DLMM Program ID (mainnet)
DLMM_PROGRAM_ID = "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo"

# Token Programs
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM_ID = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"

# Associated Token Program
ASSOCIATED_TOKEN_PROGRAM_ID = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"

# System Program
SYSTEM_PROGRAM_ID = "11111111111111111111111111111111"

# Rent Sysvar
RENT_SYSVAR_ID = "SysvarRent111111111111111111111111111111111"

# Event authority
EVENT_AUTHORITY_SEED = b"__event_authority"

# Bin array constants
BIN_ARRAY_BITMAP_SIZE = 512
MAX_BIN_PER_ARRAY = 70

# Bin ID bounds
MIN_BIN_ID = -443636
MAX_BIN_ID = 443636

# Common bin steps (basis points)
BIN_STEPS = {
    1: "0.01%",
    5: "0.05%",
    10: "0.10%",
    15: "0.15%",
    20: "0.20%",
    25: "0.25%",
    50: "0.50%",
    100: "1.00%",
}

# Strategy types for add liquidity
class StrategyType:
    SPOT_ONE_SIDE = 0
    CURVE_ONE_SIDE = 1
    BID_ASK_ONE_SIDE = 2
    SPOT_BALANCED = 3
    CURVE_BALANCED = 4
    BID_ASK_BALANCED = 5
    SPOT_IMBALANCED = 6
    CURVE_IMBALANCED = 7
    BID_ASK_IMBALANCED = 8

# Anchor discriminators (instructions)
# Computed as sha256("global:<function_name>")[0:8]
DISCRIMINATORS = {
    # V1 instructions
    "initialize_bin_array": bytes([0x23, 0x56, 0x13, 0xb9, 0x4e, 0xd4, 0x4b, 0xd3]),
    "initialize_bin_array_bitmap_extension": bytes([0x2f, 0x9d, 0xe2, 0xb4, 0x0c, 0xf0, 0x21, 0x47]),
    "initialize_position": bytes([0xdb, 0xc0, 0xea, 0x47, 0xbe, 0xbf, 0x66, 0x50]),
    "add_liquidity": bytes([0xb5, 0x9d, 0x59, 0x43, 0x8f, 0xb6, 0x34, 0x48]),
    "add_liquidity_by_strategy": bytes([0x07, 0x03, 0x96, 0x7f, 0x94, 0x28, 0x3d, 0xc8]),
    "remove_liquidity": bytes([0x50, 0x55, 0xd1, 0x48, 0x18, 0xce, 0xb1, 0x6c]),
    "remove_liquidity_by_range": bytes([0x1a, 0x52, 0x66, 0x98, 0xf0, 0x4a, 0x69, 0x1a]),
    "close_position": bytes([0x7b, 0x86, 0x51, 0x00, 0x31, 0x44, 0x62, 0x62]),
    "claim_fee": bytes([0xa9, 0x20, 0x4f, 0x89, 0x88, 0xe8, 0x46, 0x89]),
    "claim_reward": bytes([0x95, 0x7b, 0x06, 0xb5, 0x87, 0xa6, 0x64, 0x3a]),
    # V2 instructions (for newer pools/positions)
    "initialize_position2": bytes([0x8f, 0x13, 0xf2, 0x91, 0xd5, 0x0f, 0x68, 0x73]),
    "add_liquidity_by_strategy2": bytes([0x03, 0xdd, 0x95, 0xda, 0x6f, 0x8d, 0x76, 0xd5]),
    "remove_liquidity2": bytes([0xe6, 0xd7, 0x52, 0x7f, 0xf1, 0x65, 0xe3, 0x92]),
    "close_position2": bytes([0xae, 0x5a, 0x23, 0x73, 0xba, 0x28, 0x93, 0xe2]),
    "claim_fee2": bytes([0x70, 0xbf, 0x65, 0xab, 0x1c, 0x90, 0x7f, 0xbb]),
}

# Anchor account discriminators (sha256("account:<AccountName>")[0:8])
ACCOUNT_DISCRIMINATORS = {
    # Position account: sha256("account:Position")[0:8] - used by older positions
    "position": bytes([0xaa, 0xbc, 0x8f, 0xe4, 0x7a, 0x40, 0xf7, 0xd0]),
    # PositionV2 account: sha256("account:PositionV2")[0:8] - current version
    "position_v2": bytes([0x75, 0xb0, 0xd4, 0xc7, 0xf5, 0xb4, 0x85, 0xb6]),
    # LbPair account: sha256("account:LbPair")[0:8]
    "lb_pair": bytes([0x09, 0xf7, 0xab, 0x7f, 0xd2, 0xd2, 0x8d, 0xf1]),
}

# Position account structure offsets (PositionV2)
# Based on actual on-chain data analysis:
# - Discriminator: 8 bytes (offset 0)
# - lb_pair: Pubkey (32 bytes) at offset 8
# - owner: Pubkey (32 bytes) at offset 40
# - liquidity_shares: [u128; 490] = 7840 bytes at offset 72
#   (490 bins max, each share is u128 = 16 bytes)
# - lower_bin_id: i32 at offset 7912 (72 + 7840)
# - upper_bin_id: i32 at offset 7916
# - last_updated_at: i64 at offset 7920
# - Total claimed fee amounts and other fields follow
POSITION_LB_PAIR_OFFSET = 8
POSITION_OWNER_OFFSET = 40
POSITION_LIQUIDITY_SHARES_OFFSET = 72
# Each liquidity share is u128 (16 bytes), max 490 bins per position
MAX_POSITION_WIDTH = 490
POSITION_LOWER_BIN_ID_OFFSET = 7912
POSITION_UPPER_BIN_ID_OFFSET = 7916
