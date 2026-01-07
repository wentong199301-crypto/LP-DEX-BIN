"""
Meteora DLMM Instruction Builders

Builds instructions for LP operations.
"""

import struct
from typing import List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from solders.instruction import Instruction
    from solders.keypair import Keypair

from .constants import (
    DLMM_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
    TOKEN_2022_PROGRAM_ID,
    ASSOCIATED_TOKEN_PROGRAM_ID,
    SYSTEM_PROGRAM_ID,
    RENT_SYSVAR_ID,
    EVENT_AUTHORITY_SEED,
    DISCRIMINATORS,
    StrategyType,
)
from .math import get_bin_array_index


# Wrapped SOL mint address
WRAPPED_SOL_MINT = "So11111111111111111111111111111111111111112"


def detect_token_program_for_mint(rpc, mint) -> "Pubkey":
    """
    Detect which token program owns a mint (Tokenkeg or Token-2022).

    Args:
        rpc: RPC client
        mint: Mint address (string or Pubkey)

    Returns:
        Token program ID (either Tokenkeg or Token-2022)
    """
    from solders.pubkey import Pubkey

    mint_str = str(mint)

    # WSOL always uses Tokenkeg
    if mint_str == WRAPPED_SOL_MINT:
        return Pubkey.from_string(TOKEN_PROGRAM_ID)

    try:
        account_info = rpc.get_account_info(mint_str, encoding="base64")
        if account_info:
            owner = account_info.get("owner")
            if owner == TOKEN_2022_PROGRAM_ID:
                return Pubkey.from_string(TOKEN_2022_PROGRAM_ID)
    except Exception:
        pass

    # Default to Tokenkeg
    return Pubkey.from_string(TOKEN_PROGRAM_ID)


def get_associated_token_address_with_program(
    owner: "Pubkey",
    mint: "Pubkey",
    token_program: "Pubkey",
) -> "Pubkey":
    """
    Get associated token account address with explicit token program.

    Args:
        owner: Wallet owner
        mint: Token mint
        token_program: Token program (Tokenkeg or Token-2022)

    Returns:
        ATA address
    """
    from solders.pubkey import Pubkey

    ata_program = Pubkey.from_string(ASSOCIATED_TOKEN_PROGRAM_ID)

    seeds = [
        bytes(owner),
        bytes(token_program),
        bytes(mint),
    ]

    address, _ = Pubkey.find_program_address(seeds, ata_program)
    return address


def build_initialize_position_instructions(
    lb_pair: str,
    owner: str,
    lower_bin_id: int,
    width: int,
    use_v2: bool = False,
) -> Tuple[List["Instruction"], "Keypair"]:
    """
    Build instructions to initialize a new position

    Args:
        lb_pair: LbPair (pool) address
        owner: Owner wallet
        lower_bin_id: Lower bin ID
        width: Number of bins

    Returns:
        Tuple of (instructions, position_keypair)
    """
    from solders.pubkey import Pubkey
    from solders.instruction import Instruction, AccountMeta
    from solders.keypair import Keypair

    instructions = []
    program_id = Pubkey.from_string(DLMM_PROGRAM_ID)
    owner_pubkey = Pubkey.from_string(owner)
    lb_pair_pubkey = Pubkey.from_string(lb_pair)

    # Generate position keypair
    position_kp = Keypair()
    position_pubkey = position_kp.pubkey()

    # Derive event authority
    event_authority, _ = Pubkey.find_program_address(
        [EVENT_AUTHORITY_SEED],
        program_id,
    )

    # Build instruction data
    discriminator = DISCRIMINATORS["initialize_position2"] if use_v2 else DISCRIMINATORS["initialize_position"]
    data = bytearray(discriminator)
    data.extend(struct.pack("<i", lower_bin_id))
    data.extend(struct.pack("<i", width))

    accounts = [
        AccountMeta(owner_pubkey, is_signer=True, is_writable=True),  # payer
        AccountMeta(position_pubkey, is_signer=True, is_writable=True),  # position
        AccountMeta(lb_pair_pubkey, is_signer=False, is_writable=False),  # lb_pair
        AccountMeta(owner_pubkey, is_signer=False, is_writable=False),  # owner
        AccountMeta(Pubkey.from_string(SYSTEM_PROGRAM_ID), is_signer=False, is_writable=False),
        AccountMeta(Pubkey.from_string(RENT_SYSVAR_ID), is_signer=False, is_writable=False),
        AccountMeta(event_authority, is_signer=False, is_writable=False),
        AccountMeta(program_id, is_signer=False, is_writable=False),
    ]

    instruction = Instruction(program_id, bytes(data), accounts)
    instructions.append(instruction)

    return instructions, position_kp


def build_add_liquidity_by_strategy_instructions(
    lb_pair: str,
    pool_state: dict,
    position: str,
    owner: str,
    amount_x: int,
    amount_y: int,
    active_id: int,
    min_bin_id: int,
    max_bin_id: int,
    max_active_bin_slippage: int = 3,
    strategy_type: int = StrategyType.SPOT_BALANCED,
    use_v2: bool = False,
    rpc=None,
) -> List["Instruction"]:
    """
    Build instructions to add liquidity using a strategy

    Args:
        lb_pair: LbPair address
        pool_state: Parsed pool state
        position: Position address
        owner: Owner wallet
        amount_x: Amount of token X (raw)
        amount_y: Amount of token Y (raw)
        active_id: Current active bin ID
        min_bin_id: Lower bin ID of position range
        max_bin_id: Upper bin ID of position range
        max_active_bin_slippage: Max slippage in bins
        strategy_type: Strategy type (default: SPOT_BALANCED)
        rpc: RPC client for token program detection (required for Token-2022 support)

    Returns:
        List of instructions
    """
    from solders.pubkey import Pubkey
    from solders.instruction import Instruction, AccountMeta

    instructions = []
    program_id = Pubkey.from_string(DLMM_PROGRAM_ID)
    owner_pubkey = Pubkey.from_string(owner)
    lb_pair_pubkey = Pubkey.from_string(lb_pair)
    position_pubkey = Pubkey.from_string(position)

    # Token accounts and vaults
    mint_x = Pubkey.from_string(pool_state["mint_x"])
    mint_y = Pubkey.from_string(pool_state["mint_y"])
    vault_x = Pubkey.from_string(pool_state["vault_x"])
    vault_y = Pubkey.from_string(pool_state["vault_y"])

    # Detect token programs for each mint (supports Token-2022)
    if rpc is not None:
        token_program_x = detect_token_program_for_mint(rpc, mint_x)
        token_program_y = detect_token_program_for_mint(rpc, mint_y)
    else:
        token_program_x = Pubkey.from_string(TOKEN_PROGRAM_ID)
        token_program_y = Pubkey.from_string(TOKEN_PROGRAM_ID)

    user_token_x = _get_associated_token_address(owner_pubkey, mint_x, token_program_x)
    user_token_y = _get_associated_token_address(owner_pubkey, mint_y, token_program_y)

    # Derive bin arrays for the position range
    bin_array_lower = _derive_bin_array_address(lb_pair_pubkey, min_bin_id)
    bin_array_upper = _derive_bin_array_address(lb_pair_pubkey, max_bin_id)

    # Derive bitmap extension PDA (may or may not exist on-chain)
    bitmap_extension = _derive_bitmap_extension_address(lb_pair_pubkey)

    # Derive event authority
    event_authority, _ = Pubkey.find_program_address(
        [EVENT_AUTHORITY_SEED],
        program_id,
    )

    # Create token accounts if needed (with correct token program for Token-2022 support)
    instructions.append(_build_create_ata_idempotent_instruction(owner_pubkey, owner_pubkey, mint_x, token_program_x))
    instructions.append(_build_create_ata_idempotent_instruction(owner_pubkey, owner_pubkey, mint_y, token_program_y))

    # Build wrap SOL instructions if needed
    if pool_state["mint_x"] == WRAPPED_SOL_MINT and amount_x > 0:
        instructions.extend(_build_wrap_sol_instructions(owner, amount_x + 10000))
    if pool_state["mint_y"] == WRAPPED_SOL_MINT and amount_y > 0:
        instructions.extend(_build_wrap_sol_instructions(owner, amount_y + 10000))

    # Build instruction data
    # LiquidityParameterByStrategy struct:
    #   amount_x: u64
    #   amount_y: u64
    #   active_id: i32
    #   max_active_bin_slippage: i32
    #   strategy_parameters: StrategyParameters
    #     min_bin_id: i32
    #     max_bin_id: i32
    #     strategy_type: u8 (enum)
    #     parameteres: [u8; 64]
    discriminator = DISCRIMINATORS["add_liquidity_by_strategy2"] if use_v2 else DISCRIMINATORS["add_liquidity_by_strategy"]
    data = bytearray(discriminator)
    data.extend(struct.pack("<Q", amount_x))  # amount_x: u64
    data.extend(struct.pack("<Q", amount_y))  # amount_y: u64
    data.extend(struct.pack("<i", active_id))  # active_id: i32
    data.extend(struct.pack("<i", max_active_bin_slippage))  # max_active_bin_slippage: i32
    # StrategyParameters nested struct
    data.extend(struct.pack("<i", min_bin_id))  # min_bin_id: i32
    data.extend(struct.pack("<i", max_bin_id))  # max_bin_id: i32
    data.extend(struct.pack("<B", strategy_type))  # strategy_type: u8
    data.extend(bytes(64))  # parameteres: [u8; 64] (zeros for default)

    # Accounts in correct order per IDL (16 accounts total):
    # 1. position, 2. lb_pair, 3. bin_array_bitmap_extension (optional),
    # 4. user_token_x, 5. user_token_y, 6. reserve_x, 7. reserve_y,
    # 8. token_x_mint, 9. token_y_mint, 10. bin_array_lower, 11. bin_array_upper,
    # 12. sender, 13. token_x_program, 14. token_y_program, 15. event_authority, 16. program
    #
    # For bin_array_bitmap_extension: Always pass the derived PDA.
    # If it doesn't exist on-chain, the account will have 0 lamports/data
    # and the program will handle it correctly.
    accounts = [
        AccountMeta(position_pubkey, is_signer=False, is_writable=True),       # 1. position
        AccountMeta(lb_pair_pubkey, is_signer=False, is_writable=True),        # 2. lb_pair
        AccountMeta(bitmap_extension, is_signer=False, is_writable=True),      # 3. bin_array_bitmap_extension (must be mutable)
        AccountMeta(user_token_x, is_signer=False, is_writable=True),          # 4. user_token_x
        AccountMeta(user_token_y, is_signer=False, is_writable=True),          # 5. user_token_y
        AccountMeta(vault_x, is_signer=False, is_writable=True),               # 6. reserve_x
        AccountMeta(vault_y, is_signer=False, is_writable=True),               # 7. reserve_y
        AccountMeta(mint_x, is_signer=False, is_writable=False),               # 8. token_x_mint
        AccountMeta(mint_y, is_signer=False, is_writable=False),               # 9. token_y_mint
        AccountMeta(bin_array_lower, is_signer=False, is_writable=True),       # 10. bin_array_lower
        AccountMeta(bin_array_upper, is_signer=False, is_writable=True),       # 11. bin_array_upper
        AccountMeta(owner_pubkey, is_signer=True, is_writable=False),          # 12. sender
        AccountMeta(token_program_x, is_signer=False, is_writable=False),      # 13. token_x_program
        AccountMeta(token_program_y, is_signer=False, is_writable=False),      # 14. token_y_program
        AccountMeta(event_authority, is_signer=False, is_writable=False),      # 15. event_authority
        AccountMeta(program_id, is_signer=False, is_writable=False),           # 16. program
    ]

    instruction = Instruction(program_id, bytes(data), accounts)
    instructions.append(instruction)

    return instructions


def build_remove_liquidity_instructions(
    lb_pair: str,
    pool_state: dict,
    position: str,
    owner: str,
    bin_ids: List[int],
    bps_to_remove: int,
    amount_x_min: int = 0,
    amount_y_min: int = 0,
    rpc=None,
) -> List["Instruction"]:
    """
    Build instructions to remove liquidity

    Args:
        lb_pair: LbPair address
        pool_state: Parsed pool state
        position: Position address
        owner: Owner wallet
        bin_ids: List of bin IDs to remove from
        bps_to_remove: Basis points to remove (10000 = 100%)
        amount_x_min: Min amount X to receive
        amount_y_min: Min amount Y to receive
        rpc: RPC client for token program detection (required for Token-2022 support)

    Returns:
        List of instructions
    """
    from solders.pubkey import Pubkey
    from solders.instruction import Instruction, AccountMeta

    program_id = Pubkey.from_string(DLMM_PROGRAM_ID)
    owner_pubkey = Pubkey.from_string(owner)
    lb_pair_pubkey = Pubkey.from_string(lb_pair)
    position_pubkey = Pubkey.from_string(position)

    mint_x = Pubkey.from_string(pool_state["mint_x"])
    mint_y = Pubkey.from_string(pool_state["mint_y"])
    vault_x = Pubkey.from_string(pool_state["vault_x"])
    vault_y = Pubkey.from_string(pool_state["vault_y"])

    # Detect token programs for each mint (supports Token-2022)
    if rpc is not None:
        token_program_x = detect_token_program_for_mint(rpc, mint_x)
        token_program_y = detect_token_program_for_mint(rpc, mint_y)
    else:
        token_program_x = Pubkey.from_string(TOKEN_PROGRAM_ID)
        token_program_y = Pubkey.from_string(TOKEN_PROGRAM_ID)

    user_token_x = _get_associated_token_address(owner_pubkey, mint_x, token_program_x)
    user_token_y = _get_associated_token_address(owner_pubkey, mint_y, token_program_y)

    # Derive bin arrays for lower and upper bounds
    min_bin = min(bin_ids)
    max_bin = max(bin_ids)
    bin_array_lower = _derive_bin_array_address(lb_pair_pubkey, min_bin)
    bin_array_upper = _derive_bin_array_address(lb_pair_pubkey, max_bin)

    # Derive bitmap extension PDA (optional but always passed)
    bitmap_extension = _derive_bitmap_extension_address(lb_pair_pubkey)

    # Derive event authority
    event_authority, _ = Pubkey.find_program_address(
        [EVENT_AUTHORITY_SEED],
        program_id,
    )

    # Build instruction data
    # BinLiquidityReduction struct per bin: { bin_id: i32, bps_to_remove: u16 }
    data = bytearray(DISCRIMINATORS["remove_liquidity"])
    data.extend(struct.pack("<I", len(bin_ids)))  # Vec length (u32)
    for bin_id in bin_ids:
        data.extend(struct.pack("<i", bin_id))      # bin_id: i32
        data.extend(struct.pack("<H", bps_to_remove))  # bps_to_remove: u16 (per bin)
    data.extend(struct.pack("<Q", amount_x_min))   # amount_x_min: u64
    data.extend(struct.pack("<Q", amount_y_min))   # amount_y_min: u64

    # Accounts per IDL (16 accounts):
    # 1. position, 2. lb_pair, 3. bin_array_bitmap_extension (optional),
    # 4. user_token_x, 5. user_token_y, 6. reserve_x, 7. reserve_y,
    # 8. token_x_mint, 9. token_y_mint, 10. bin_array_lower, 11. bin_array_upper,
    # 12. sender, 13. token_x_program, 14. token_y_program, 15. event_authority, 16. program
    accounts = [
        AccountMeta(position_pubkey, is_signer=False, is_writable=True),       # 1. position
        AccountMeta(lb_pair_pubkey, is_signer=False, is_writable=True),        # 2. lb_pair
        AccountMeta(bitmap_extension, is_signer=False, is_writable=True),      # 3. bin_array_bitmap_extension
        AccountMeta(user_token_x, is_signer=False, is_writable=True),          # 4. user_token_x
        AccountMeta(user_token_y, is_signer=False, is_writable=True),          # 5. user_token_y
        AccountMeta(vault_x, is_signer=False, is_writable=True),               # 6. reserve_x
        AccountMeta(vault_y, is_signer=False, is_writable=True),               # 7. reserve_y
        AccountMeta(mint_x, is_signer=False, is_writable=False),               # 8. token_x_mint
        AccountMeta(mint_y, is_signer=False, is_writable=False),               # 9. token_y_mint
        AccountMeta(bin_array_lower, is_signer=False, is_writable=True),       # 10. bin_array_lower
        AccountMeta(bin_array_upper, is_signer=False, is_writable=True),       # 11. bin_array_upper
        AccountMeta(owner_pubkey, is_signer=True, is_writable=False),          # 12. sender
        AccountMeta(token_program_x, is_signer=False, is_writable=False),      # 13. token_x_program
        AccountMeta(token_program_y, is_signer=False, is_writable=False),      # 14. token_y_program
        AccountMeta(event_authority, is_signer=False, is_writable=False),      # 15. event_authority
        AccountMeta(program_id, is_signer=False, is_writable=False),           # 16. program
    ]

    instruction = Instruction(program_id, bytes(data), accounts)
    return [instruction]


def build_close_position_instructions(
    lb_pair: str,
    position: str,
    position_state: dict,
    owner: str,
) -> List["Instruction"]:
    """
    Build instructions to close position

    Args:
        lb_pair: LbPair address
        position: Position address
        position_state: Parsed position state (contains lower/upper bin IDs)
        owner: Owner wallet

    Returns:
        List of instructions
    """
    from solders.pubkey import Pubkey
    from solders.instruction import Instruction, AccountMeta

    program_id = Pubkey.from_string(DLMM_PROGRAM_ID)
    owner_pubkey = Pubkey.from_string(owner)
    lb_pair_pubkey = Pubkey.from_string(lb_pair)
    position_pubkey = Pubkey.from_string(position)

    # Derive bin arrays from position state
    lower_bin_id = position_state["lower_bin_id"]
    upper_bin_id = position_state["upper_bin_id"]
    bin_array_lower = _derive_bin_array_address(lb_pair_pubkey, lower_bin_id)
    bin_array_upper = _derive_bin_array_address(lb_pair_pubkey, upper_bin_id)

    # Derive event authority
    event_authority, _ = Pubkey.find_program_address(
        [EVENT_AUTHORITY_SEED],
        program_id,
    )

    # Build instruction data
    data = bytearray(DISCRIMINATORS["close_position"])

    # Accounts per IDL (8 accounts):
    # 1. position, 2. lb_pair, 3. bin_array_lower, 4. bin_array_upper,
    # 5. sender, 6. rent_receiver, 7. event_authority, 8. program
    accounts = [
        AccountMeta(position_pubkey, is_signer=False, is_writable=True),   # 1. position
        AccountMeta(lb_pair_pubkey, is_signer=False, is_writable=True),    # 2. lb_pair
        AccountMeta(bin_array_lower, is_signer=False, is_writable=True),   # 3. bin_array_lower
        AccountMeta(bin_array_upper, is_signer=False, is_writable=True),   # 4. bin_array_upper
        AccountMeta(owner_pubkey, is_signer=True, is_writable=False),      # 5. sender
        AccountMeta(owner_pubkey, is_signer=False, is_writable=True),      # 6. rent_receiver (same as sender)
        AccountMeta(event_authority, is_signer=False, is_writable=False),  # 7. event_authority
        AccountMeta(program_id, is_signer=False, is_writable=False),       # 8. program
    ]

    instruction = Instruction(program_id, bytes(data), accounts)
    return [instruction]


def build_claim_fee_instructions(
    lb_pair: str,
    pool_state: dict,
    position: str,
    position_state: dict,
    owner: str,
    rpc=None,
) -> List["Instruction"]:
    """
    Build instructions to claim fees

    Uses claim_fee2 instruction when tokens have different token programs (Token-2022 support),
    otherwise uses the original claim_fee instruction for backward compatibility.

    Args:
        lb_pair: LbPair address
        pool_state: Parsed pool state
        position: Position address
        position_state: Parsed position state (contains lower/upper bin IDs)
        owner: Owner wallet
        rpc: RPC client for token program detection (required for Token-2022 support)

    Returns:
        List of instructions
    """
    from solders.pubkey import Pubkey
    from solders.instruction import Instruction, AccountMeta

    program_id = Pubkey.from_string(DLMM_PROGRAM_ID)
    owner_pubkey = Pubkey.from_string(owner)
    lb_pair_pubkey = Pubkey.from_string(lb_pair)
    position_pubkey = Pubkey.from_string(position)

    mint_x = Pubkey.from_string(pool_state["mint_x"])
    mint_y = Pubkey.from_string(pool_state["mint_y"])
    vault_x = Pubkey.from_string(pool_state["vault_x"])
    vault_y = Pubkey.from_string(pool_state["vault_y"])

    # Detect token programs for each mint (supports Token-2022)
    if rpc is not None:
        token_program_x = detect_token_program_for_mint(rpc, mint_x)
        token_program_y = detect_token_program_for_mint(rpc, mint_y)
    else:
        token_program_x = Pubkey.from_string(TOKEN_PROGRAM_ID)
        token_program_y = Pubkey.from_string(TOKEN_PROGRAM_ID)

    # Derive ATAs with correct token programs for Token-2022 support
    user_token_x = _get_associated_token_address(owner_pubkey, mint_x, token_program_x)
    user_token_y = _get_associated_token_address(owner_pubkey, mint_y, token_program_y)

    # Derive bin arrays from position state
    lower_bin_id = position_state["lower_bin_id"]
    upper_bin_id = position_state["upper_bin_id"]
    bin_array_lower = _derive_bin_array_address(lb_pair_pubkey, lower_bin_id)
    bin_array_upper = _derive_bin_array_address(lb_pair_pubkey, upper_bin_id)

    # Derive event authority
    event_authority, _ = Pubkey.find_program_address(
        [EVENT_AUTHORITY_SEED],
        program_id,
    )

    # Determine if we need V2 instruction (when token programs differ)
    use_v2 = str(token_program_x) != str(token_program_y)

    if use_v2:
        # Use claim_fee2 with separate token programs (15 accounts)
        data = bytearray(DISCRIMINATORS["claim_fee2"])
        accounts = [
            AccountMeta(lb_pair_pubkey, is_signer=False, is_writable=True),    # 1. lb_pair
            AccountMeta(position_pubkey, is_signer=False, is_writable=True),   # 2. position
            AccountMeta(bin_array_lower, is_signer=False, is_writable=True),   # 3. bin_array_lower
            AccountMeta(bin_array_upper, is_signer=False, is_writable=True),   # 4. bin_array_upper
            AccountMeta(owner_pubkey, is_signer=True, is_writable=False),      # 5. sender
            AccountMeta(vault_x, is_signer=False, is_writable=True),           # 6. reserve_x
            AccountMeta(vault_y, is_signer=False, is_writable=True),           # 7. reserve_y
            AccountMeta(user_token_x, is_signer=False, is_writable=True),      # 8. user_token_x
            AccountMeta(user_token_y, is_signer=False, is_writable=True),      # 9. user_token_y
            AccountMeta(mint_x, is_signer=False, is_writable=False),           # 10. token_x_mint
            AccountMeta(mint_y, is_signer=False, is_writable=False),           # 11. token_y_mint
            AccountMeta(token_program_x, is_signer=False, is_writable=False),  # 12. token_x_program
            AccountMeta(token_program_y, is_signer=False, is_writable=False),  # 13. token_y_program
            AccountMeta(event_authority, is_signer=False, is_writable=False),  # 14. event_authority
            AccountMeta(program_id, is_signer=False, is_writable=False),       # 15. program
        ]
    else:
        # Use original claim_fee with single token program (14 accounts)
        data = bytearray(DISCRIMINATORS["claim_fee"])
        accounts = [
            AccountMeta(lb_pair_pubkey, is_signer=False, is_writable=True),    # 1. lb_pair
            AccountMeta(position_pubkey, is_signer=False, is_writable=True),   # 2. position
            AccountMeta(bin_array_lower, is_signer=False, is_writable=True),   # 3. bin_array_lower
            AccountMeta(bin_array_upper, is_signer=False, is_writable=True),   # 4. bin_array_upper
            AccountMeta(owner_pubkey, is_signer=True, is_writable=False),      # 5. sender
            AccountMeta(vault_x, is_signer=False, is_writable=True),           # 6. reserve_x
            AccountMeta(vault_y, is_signer=False, is_writable=True),           # 7. reserve_y
            AccountMeta(user_token_x, is_signer=False, is_writable=True),      # 8. user_token_x
            AccountMeta(user_token_y, is_signer=False, is_writable=True),      # 9. user_token_y
            AccountMeta(mint_x, is_signer=False, is_writable=False),           # 10. token_x_mint
            AccountMeta(mint_y, is_signer=False, is_writable=False),           # 11. token_y_mint
            AccountMeta(token_program_x, is_signer=False, is_writable=False),  # 12. token_program (same for both)
            AccountMeta(event_authority, is_signer=False, is_writable=False),  # 13. event_authority
            AccountMeta(program_id, is_signer=False, is_writable=False),       # 14. program
        ]

    instruction = Instruction(program_id, bytes(data), accounts)
    return [instruction]


def _get_associated_token_address(
    owner: "Pubkey",
    mint: "Pubkey",
    token_program: "Pubkey" = None,
) -> "Pubkey":
    """Get associated token account address

    Args:
        owner: Wallet owner
        mint: Token mint
        token_program: Token program (defaults to Tokenkeg if None)

    Returns:
        ATA address
    """
    from solders.pubkey import Pubkey

    ata_program = Pubkey.from_string(ASSOCIATED_TOKEN_PROGRAM_ID)
    if token_program is None:
        token_program = Pubkey.from_string(TOKEN_PROGRAM_ID)

    seeds = [
        bytes(owner),
        bytes(token_program),
        bytes(mint),
    ]

    address, _ = Pubkey.find_program_address(seeds, ata_program)
    return address


def _derive_bin_array_address(lb_pair: "Pubkey", bin_id: int) -> "Pubkey":
    """Derive bin array PDA"""
    from solders.pubkey import Pubkey

    program_id = Pubkey.from_string(DLMM_PROGRAM_ID)
    bin_array_index = get_bin_array_index(bin_id)

    seeds = [
        b"bin_array",
        bytes(lb_pair),
        struct.pack("<q", bin_array_index),  # i64 little-endian
    ]

    address, _ = Pubkey.find_program_address(seeds, program_id)
    return address


def _derive_bitmap_extension_address(lb_pair: "Pubkey") -> "Pubkey":
    """Derive bin array bitmap extension PDA

    This PDA may or may not exist on-chain. For pools with narrow bin ranges,
    it typically doesn't exist. We always derive and pass it - the program
    will check if it's initialized.
    """
    from solders.pubkey import Pubkey

    program_id = Pubkey.from_string(DLMM_PROGRAM_ID)

    seeds = [
        b"bitmap",
        bytes(lb_pair),
    ]

    address, _ = Pubkey.find_program_address(seeds, program_id)
    return address


def _build_create_ata_idempotent_instruction(
    payer: "Pubkey",
    owner: "Pubkey",
    mint: "Pubkey",
    token_program: "Pubkey" = None,
) -> "Instruction":
    """Build create_associated_token_account_idempotent instruction

    Args:
        payer: Transaction fee payer
        owner: Token account owner
        mint: Token mint
        token_program: Token program (Tokenkeg or Token-2022)

    Returns:
        Instruction
    """
    from solders.pubkey import Pubkey
    from solders.instruction import Instruction, AccountMeta

    ata_program = Pubkey.from_string(ASSOCIATED_TOKEN_PROGRAM_ID)
    if token_program is None:
        token_program = Pubkey.from_string(TOKEN_PROGRAM_ID)
    system_program = Pubkey.from_string(SYSTEM_PROGRAM_ID)

    ata_address = _get_associated_token_address(owner, mint, token_program)

    accounts = [
        AccountMeta(payer, is_signer=True, is_writable=True),
        AccountMeta(ata_address, is_signer=False, is_writable=True),
        AccountMeta(owner, is_signer=False, is_writable=False),
        AccountMeta(mint, is_signer=False, is_writable=False),
        AccountMeta(system_program, is_signer=False, is_writable=False),
        AccountMeta(token_program, is_signer=False, is_writable=False),
    ]

    return Instruction(ata_program, bytes([1]), accounts)


def _build_wrap_sol_instructions(owner: str, amount_lamports: int) -> List["Instruction"]:
    """Build instructions to wrap SOL to WSOL"""
    from solders.pubkey import Pubkey
    from solders.instruction import Instruction, AccountMeta

    instructions = []
    owner_pubkey = Pubkey.from_string(owner)
    wsol_mint = Pubkey.from_string(WRAPPED_SOL_MINT)

    wsol_ata = _get_associated_token_address(owner_pubkey, wsol_mint)

    # Create WSOL ATA if needed
    instructions.append(_build_create_ata_idempotent_instruction(
        owner_pubkey, owner_pubkey, wsol_mint
    ))

    # Transfer SOL
    system_program = Pubkey.from_string(SYSTEM_PROGRAM_ID)
    transfer_accounts = [
        AccountMeta(owner_pubkey, is_signer=True, is_writable=True),
        AccountMeta(wsol_ata, is_signer=False, is_writable=True),
    ]
    transfer_data = struct.pack("<I", 2) + struct.pack("<Q", amount_lamports)
    instructions.append(Instruction(system_program, transfer_data, transfer_accounts))

    # Sync native
    token_program = Pubkey.from_string(TOKEN_PROGRAM_ID)
    sync_accounts = [AccountMeta(wsol_ata, is_signer=False, is_writable=True)]
    instructions.append(Instruction(token_program, bytes([17]), sync_accounts))

    return instructions


def build_initialize_bitmap_extension_instructions(
    lb_pair: str,
    funder: str,
) -> List["Instruction"]:
    """
    Build instruction to initialize bin array bitmap extension.

    The bitmap extension is needed for pools with positions spanning wide bin ranges.
    This PDA must exist before addLiquidityByStrategy can reference it.

    Args:
        lb_pair: LbPair address
        funder: The funder wallet who pays for creation

    Returns:
        List with single instruction
    """
    from solders.pubkey import Pubkey
    from solders.instruction import Instruction, AccountMeta

    program_id = Pubkey.from_string(DLMM_PROGRAM_ID)
    lb_pair_pubkey = Pubkey.from_string(lb_pair)
    funder_pubkey = Pubkey.from_string(funder)

    # Derive bitmap extension PDA
    bitmap_extension = _derive_bitmap_extension_address(lb_pair_pubkey)

    # Build instruction data (just the discriminator, no args)
    data = bytearray(DISCRIMINATORS["initialize_bin_array_bitmap_extension"])

    # Accounts per IDL:
    # 1. lb_pair
    # 2. bin_array_bitmap_extension (the PDA being created)
    # 3. funder (pays for rent)
    # 4. system_program
    # 5. rent
    accounts = [
        AccountMeta(lb_pair_pubkey, is_signer=False, is_writable=False),
        AccountMeta(bitmap_extension, is_signer=False, is_writable=True),
        AccountMeta(funder_pubkey, is_signer=True, is_writable=True),
        AccountMeta(Pubkey.from_string(SYSTEM_PROGRAM_ID), is_signer=False, is_writable=False),
        AccountMeta(Pubkey.from_string(RENT_SYSVAR_ID), is_signer=False, is_writable=False),
    ]

    instruction = Instruction(program_id, bytes(data), accounts)
    return [instruction]


def build_initialize_bin_array_instructions(
    lb_pair: str,
    bin_array_index: int,
    funder: str,
) -> List["Instruction"]:
    """
    Build instruction to initialize a bin array.

    Args:
        lb_pair: LbPair address
        bin_array_index: The bin array index (from get_bin_array_index)
        funder: The funder wallet who pays for creation

    Returns:
        List with single instruction
    """
    from solders.pubkey import Pubkey
    from solders.instruction import Instruction, AccountMeta

    program_id = Pubkey.from_string(DLMM_PROGRAM_ID)
    lb_pair_pubkey = Pubkey.from_string(lb_pair)
    funder_pubkey = Pubkey.from_string(funder)

    # Derive bin array PDA using the index directly
    bin_array, _ = Pubkey.find_program_address(
        [
            b"bin_array",
            bytes(lb_pair_pubkey),
            struct.pack("<q", bin_array_index),  # i64 little-endian
        ],
        program_id,
    )

    # Build instruction data
    data = bytearray(DISCRIMINATORS["initialize_bin_array"])
    data.extend(struct.pack("<q", bin_array_index))  # index: i64

    accounts = [
        AccountMeta(lb_pair_pubkey, is_signer=False, is_writable=False),
        AccountMeta(bin_array, is_signer=False, is_writable=True),
        AccountMeta(funder_pubkey, is_signer=True, is_writable=True),
        AccountMeta(Pubkey.from_string(SYSTEM_PROGRAM_ID), is_signer=False, is_writable=False),
    ]

    instruction = Instruction(program_id, bytes(data), accounts)
    return [instruction]
