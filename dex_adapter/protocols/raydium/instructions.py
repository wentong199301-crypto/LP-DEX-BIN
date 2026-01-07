"""
Raydium CLMM Instruction Builders

Based on raydium_trading reference implementation.

Key features:
- Token-2022 NFT support (open_position_with_token22_nft)
- Multi-variant close position (tries multiple instruction variants)
- Auto-detection of token programs
- Floor-based tick array alignment
- Proper reward handling with manual overrides
"""

import struct
import base64
from decimal import Decimal
from typing import List, Optional, Tuple, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from solders.instruction import Instruction
    from solders.keypair import Keypair
    from solders.pubkey import Pubkey

from .constants import (
    CLMM_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
    TOKEN_2022_PROGRAM_ID,
    ASSOCIATED_TOKEN_PROGRAM_ID,
    SYSTEM_PROGRAM_ID,
    RENT_SYSVAR_ID,
    METADATA_PROGRAM_ID,
    MEMO_PROGRAM_ID,
    WRAPPED_SOL_MINT,
    WSOL_WRAP_BUFFER_LAMPORTS,
    DISCRIMINATORS,
    PP_DISCRIMINATORS,
    TICK_ARRAY_SIZE,
    MANUAL_REWARD_OVERRIDES,
)
from .math import tick_to_sqrt_price_x64, get_tick_array_start_index


def detect_token_program_for_mint(rpc, mint: "Pubkey") -> "Pubkey":
    """
    Detect the token program for a given mint by checking its owner.

    This is critical for Token-2022 support - we need to use the correct
    token program for each mint.

    Args:
        rpc: RPC client
        mint: Mint address

    Returns:
        Token program ID (either Tokenkeg or Token-2022)
    """
    from solders.pubkey import Pubkey

    # WSOL always uses Tokenkeg
    if str(mint) == WRAPPED_SOL_MINT:
        return Pubkey.from_string(TOKEN_PROGRAM_ID)

    try:
        account_info = rpc.get_account_info(str(mint), encoding="base64")
        if account_info:
            owner = account_info.get("owner")
            if owner == TOKEN_2022_PROGRAM_ID:
                return Pubkey.from_string(TOKEN_2022_PROGRAM_ID)
    except Exception:
        pass

    # Default to Tokenkeg
    return Pubkey.from_string(TOKEN_PROGRAM_ID)


def get_associated_token_address(
    owner: "Pubkey",
    mint: "Pubkey",
    token_program: Optional["Pubkey"] = None,
) -> "Pubkey":
    """
    Get associated token account address.

    Args:
        owner: Wallet owner
        mint: Token mint
        token_program: Token program (defaults to Tokenkeg)

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


def build_create_ata_idempotent_instruction(
    payer: "Pubkey",
    owner: "Pubkey",
    mint: "Pubkey",
    token_program: Optional["Pubkey"] = None,
) -> "Instruction":
    """
    Build create_associated_token_account_idempotent instruction.

    This creates the ATA if it doesn't exist, or does nothing if it does.

    Args:
        payer: Fee payer
        owner: Account owner
        mint: Token mint
        token_program: Token program (defaults to Tokenkeg)

    Returns:
        Instruction to create ATA
    """
    from solders.pubkey import Pubkey
    from solders.instruction import Instruction, AccountMeta

    ata_program = Pubkey.from_string(ASSOCIATED_TOKEN_PROGRAM_ID)
    system_program = Pubkey.from_string(SYSTEM_PROGRAM_ID)

    if token_program is None:
        token_program = Pubkey.from_string(TOKEN_PROGRAM_ID)

    ata_address = get_associated_token_address(owner, mint, token_program)

    accounts = [
        AccountMeta(payer, is_signer=True, is_writable=True),
        AccountMeta(ata_address, is_signer=False, is_writable=True),
        AccountMeta(owner, is_signer=False, is_writable=False),
        AccountMeta(mint, is_signer=False, is_writable=False),
        AccountMeta(system_program, is_signer=False, is_writable=False),
        AccountMeta(token_program, is_signer=False, is_writable=False),
    ]

    # Instruction data: single byte 1 for idempotent create
    return Instruction(ata_program, bytes([1]), accounts)


def derive_tick_array_address(
    pool: "Pubkey",
    tick: int,
    tick_spacing: int,
    program_id: Optional["Pubkey"] = None,
) -> "Pubkey":
    """
    Derive tick array PDA using floor-based alignment.

    Args:
        pool: Pool address
        tick: Tick index
        tick_spacing: Pool tick spacing
        program_id: Program ID (defaults to CLMM_PROGRAM_ID)

    Returns:
        Tick array address
    """
    from solders.pubkey import Pubkey

    if program_id is None:
        program_id = Pubkey.from_string(CLMM_PROGRAM_ID)

    start_index = get_tick_array_start_index(tick, tick_spacing)

    # Note: Raydium uses big-endian for the start index in PDA seeds
    seeds = [
        b"tick_array",
        bytes(pool),
        struct.pack(">i", start_index),
    ]

    address, _ = Pubkey.find_program_address(seeds, program_id)
    return address


def derive_protocol_position(
    pool: "Pubkey",
    tick_lower: int,
    tick_upper: int,
    program_id: Optional["Pubkey"] = None,
) -> "Pubkey":
    """
    Derive protocol position PDA.

    Args:
        pool: Pool address
        tick_lower: Lower tick
        tick_upper: Upper tick
        program_id: Program ID

    Returns:
        Protocol position address
    """
    from solders.pubkey import Pubkey

    if program_id is None:
        program_id = Pubkey.from_string(CLMM_PROGRAM_ID)

    # Note: Raydium uses little-endian for tick values in protocol position PDA
    seeds = [
        b"position",
        bytes(pool),
        struct.pack("<i", tick_lower),
        struct.pack("<i", tick_upper),
    ]

    address, _ = Pubkey.find_program_address(seeds, program_id)
    return address


def derive_personal_position(
    nft_mint: "Pubkey",
    program_id: Optional["Pubkey"] = None,
) -> "Pubkey":
    """
    Derive personal position PDA from NFT mint.

    Args:
        nft_mint: Position NFT mint
        program_id: Program ID

    Returns:
        Personal position address
    """
    from solders.pubkey import Pubkey

    if program_id is None:
        program_id = Pubkey.from_string(CLMM_PROGRAM_ID)

    seeds = [b"position", bytes(nft_mint)]
    address, _ = Pubkey.find_program_address(seeds, program_id)
    return address


def build_open_position_instructions(
    pool_address: str,
    pool_state: dict,
    owner: str,
    tick_lower: int,
    tick_upper: int,
    liquidity: int,
    amount_0_max: int,
    amount_1_max: int,
    with_metadata: bool = True,
    base_flag: Optional[bool] = None,
    rpc=None,
    program_id: Optional[str] = None,
) -> Tuple[List["Instruction"], "Keypair"]:
    """
    Build instructions to open a new position using open_position_with_token22_nft.

    This uses Token-2022 for the NFT mint, which is the preferred method for new positions.

    Args:
        pool_address: Pool address
        pool_state: Parsed pool state
        owner: Owner wallet
        tick_lower: Lower tick
        tick_upper: Upper tick
        liquidity: Liquidity to add
        amount_0_max: Max token 0 amount
        amount_1_max: Max token 1 amount
        with_metadata: Create NFT metadata (default True)
        base_flag: Optional base flag for amount calculation
        rpc: Optional RPC client for token program detection
        program_id: Optional program ID override

    Returns:
        Tuple of (instructions, nft_mint_keypair)
    """
    from solders.pubkey import Pubkey
    from solders.instruction import Instruction, AccountMeta
    from solders.keypair import Keypair

    instructions = []

    pid = Pubkey.from_string(program_id or CLMM_PROGRAM_ID)
    owner_pubkey = Pubkey.from_string(owner)
    pool_pubkey = Pubkey.from_string(pool_address)

    # Generate NFT mint keypair (must be signed by caller)
    # This will be a Token-2022 NFT
    nft_mint = Keypair()
    nft_mint_pubkey = nft_mint.pubkey()

    # Derive personal position PDA
    personal_position = derive_personal_position(nft_mint_pubkey, pid)

    # Derive NFT token account (ATA using Token-2022)
    token_2022 = Pubkey.from_string(TOKEN_2022_PROGRAM_ID)
    nft_account = get_associated_token_address(owner_pubkey, nft_mint_pubkey, token_2022)

    # Get tick spacing and compute tick array addresses
    tick_spacing = pool_state["tick_spacing"]

    # Floor-based alignment for tick arrays
    # For lower tick: direct floor alignment
    # For upper tick: floor of (upper - 1) to ensure edge containment
    step = TICK_ARRAY_SIZE * tick_spacing
    ta_lower_start = (tick_lower // step) * step
    ta_upper_start = ((tick_upper - 1) // step) * step

    tick_array_lower = derive_tick_array_address(pool_pubkey, tick_lower, tick_spacing, pid)
    tick_array_upper = derive_tick_array_address(pool_pubkey, tick_upper - 1, tick_spacing, pid)

    # Protocol position
    protocol_position = derive_protocol_position(pool_pubkey, tick_lower, tick_upper, pid)

    # Token vaults
    vault_a = Pubkey.from_string(pool_state["vault_a"])
    vault_b = Pubkey.from_string(pool_state["vault_b"])

    # Token mints
    mint_a = Pubkey.from_string(pool_state["mint_a"])
    mint_b = Pubkey.from_string(pool_state["mint_b"])

    # Detect token programs for mints
    if rpc:
        prog_a = detect_token_program_for_mint(rpc, mint_a)
        prog_b = detect_token_program_for_mint(rpc, mint_b)
    else:
        prog_a = Pubkey.from_string(TOKEN_PROGRAM_ID)
        prog_b = Pubkey.from_string(TOKEN_PROGRAM_ID)

    # Owner token accounts with correct token programs
    token_account_a = get_associated_token_address(owner_pubkey, mint_a, prog_a)
    token_account_b = get_associated_token_address(owner_pubkey, mint_b, prog_b)

    # Ensure ATAs exist
    instructions.append(build_create_ata_idempotent_instruction(owner_pubkey, owner_pubkey, mint_a, prog_a))
    instructions.append(build_create_ata_idempotent_instruction(owner_pubkey, owner_pubkey, mint_b, prog_b))

    # Build instruction data for open_position_with_token22_nft
    # Format: discriminator + tick_lower(i32) + tick_upper(i32) + tick_array_lower_start(i32)
    #         + tick_array_upper_start(i32) + liquidity(u128) + amount_0_max(u64) + amount_1_max(u64)
    #         + with_metadata(bool) + base_flag(Option<bool>)
    data = bytearray(DISCRIMINATORS["open_position_with_token22_nft"])
    data.extend(struct.pack("<i", tick_lower))
    data.extend(struct.pack("<i", tick_upper))
    data.extend(struct.pack("<i", ta_lower_start))
    data.extend(struct.pack("<i", ta_upper_start))
    data.extend(liquidity.to_bytes(16, "little"))
    data.extend(struct.pack("<Q", amount_0_max))
    data.extend(struct.pack("<Q", amount_1_max))
    data.extend(struct.pack("<?", with_metadata))

    # Optional base_flag
    if base_flag is None:
        data.extend(b"\x00")  # None
    else:
        data.extend(b"\x01" + (b"\x01" if base_flag else b"\x00"))

    # Account metas for open_position_with_token22_nft
    # Order matches Raydium program expectations
    accounts = [
        AccountMeta(owner_pubkey, is_signer=True, is_writable=True),      # 0: payer
        AccountMeta(owner_pubkey, is_signer=False, is_writable=False),    # 1: position_nft_owner
        AccountMeta(nft_mint_pubkey, is_signer=True, is_writable=True),   # 2: position_nft_mint
        AccountMeta(nft_account, is_signer=False, is_writable=True),      # 3: position_nft_account
        AccountMeta(pool_pubkey, is_signer=False, is_writable=True),      # 4: pool_state
        AccountMeta(protocol_position, is_signer=False, is_writable=True),# 5: protocol_position
        AccountMeta(tick_array_lower, is_signer=False, is_writable=True), # 6: tick_array_lower
        AccountMeta(tick_array_upper, is_signer=False, is_writable=True), # 7: tick_array_upper
        AccountMeta(personal_position, is_signer=False, is_writable=True),# 8: personal_position
        AccountMeta(token_account_a, is_signer=False, is_writable=True),  # 9: token_account_0
        AccountMeta(token_account_b, is_signer=False, is_writable=True),  # 10: token_account_1
        AccountMeta(vault_a, is_signer=False, is_writable=True),          # 11: token_vault_0
        AccountMeta(vault_b, is_signer=False, is_writable=True),          # 12: token_vault_1
        AccountMeta(Pubkey.from_string(RENT_SYSVAR_ID), is_signer=False, is_writable=False),    # 13: rent
        AccountMeta(Pubkey.from_string(SYSTEM_PROGRAM_ID), is_signer=False, is_writable=False), # 14: system_program
        AccountMeta(Pubkey.from_string(TOKEN_PROGRAM_ID), is_signer=False, is_writable=False),  # 15: token_program
        AccountMeta(Pubkey.from_string(ASSOCIATED_TOKEN_PROGRAM_ID), is_signer=False, is_writable=False), # 16: ata_program
        AccountMeta(token_2022, is_signer=False, is_writable=False),      # 17: token_program_2022
        AccountMeta(mint_a, is_signer=False, is_writable=False),          # 18: vault_0_mint
        AccountMeta(mint_b, is_signer=False, is_writable=False),          # 19: vault_1_mint
    ]

    instruction = Instruction(pid, bytes(data), accounts)
    instructions.append(instruction)

    return instructions, nft_mint


def build_close_position_candidates(
    position_state: dict,
    pool_state: dict,
    owner: str,
    nft_account: "Pubkey",
    token_program_nft: "Pubkey",
    program_id: Optional["Pubkey"] = None,
) -> List["Instruction"]:
    """
    Build candidate instructions for closing a position.

    Tries multiple variants (close_position_v2 and close_position) with
    different account orderings. The caller should simulate each and use
    the first one that succeeds.

    Args:
        position_state: Parsed position state
        pool_state: Parsed pool state
        owner: Owner wallet
        nft_account: NFT token account
        token_program_nft: Token program for the NFT
        program_id: Program ID

    Returns:
        List of candidate instructions to try
    """
    from solders.pubkey import Pubkey
    from solders.instruction import Instruction, AccountMeta

    pid = program_id or Pubkey.from_string(CLMM_PROGRAM_ID)
    owner_pubkey = Pubkey.from_string(owner)
    nft_mint = Pubkey.from_string(position_state["nft_mint"])

    # Personal position PDA
    personal_position = derive_personal_position(nft_mint, pid)

    # Build candidates with different discriminators and account orderings
    candidates = []

    # Discriminators to try
    disc_v2 = DISCRIMINATORS["close_position_v2"]
    disc_legacy = DISCRIMINATORS["close_position"]

    # Account orderings to try (different positions have different requirements)
    # Ordering 1: owner, mint, nft_acc, position, system, token_prog
    metas_1 = [
        AccountMeta(owner_pubkey, is_signer=True, is_writable=False),
        AccountMeta(nft_mint, is_signer=False, is_writable=True),
        AccountMeta(nft_account, is_signer=False, is_writable=True),
        AccountMeta(personal_position, is_signer=False, is_writable=True),
        AccountMeta(Pubkey.from_string(SYSTEM_PROGRAM_ID), is_signer=False, is_writable=False),
        AccountMeta(token_program_nft, is_signer=False, is_writable=False),
    ]

    # Ordering 2: owner, mint, nft_acc, position, token_prog, system
    metas_2 = [
        AccountMeta(owner_pubkey, is_signer=True, is_writable=False),
        AccountMeta(nft_mint, is_signer=False, is_writable=True),
        AccountMeta(nft_account, is_signer=False, is_writable=True),
        AccountMeta(personal_position, is_signer=False, is_writable=True),
        AccountMeta(token_program_nft, is_signer=False, is_writable=False),
        AccountMeta(Pubkey.from_string(SYSTEM_PROGRAM_ID), is_signer=False, is_writable=False),
    ]

    # Try close_position_v2 with both orderings
    candidates.append(Instruction(pid, disc_v2, metas_1))
    candidates.append(Instruction(pid, disc_v2, metas_2))

    # Try close_position (legacy) with both orderings
    candidates.append(Instruction(pid, disc_legacy, metas_1))
    candidates.append(Instruction(pid, disc_legacy, metas_2))

    return candidates


def build_close_position_instructions(
    position_state: dict,
    pool_state: dict,
    owner: str,
    rpc=None,
    program_id: Optional[str] = None,
) -> List["Instruction"]:
    """
    Build instruction to close a position.

    IMPORTANT: The position must have 0 liquidity before calling this.
    Use build_decrease_liquidity_instructions first to remove all liquidity.

    Args:
        position_state: Parsed position state
        pool_state: Parsed pool state
        owner: Owner wallet
        rpc: Optional RPC client for token program detection
        program_id: Optional program ID override

    Returns:
        List with single ClosePosition instruction
    """
    from solders.pubkey import Pubkey
    from solders.instruction import Instruction, AccountMeta

    pid = Pubkey.from_string(program_id or CLMM_PROGRAM_ID)
    owner_pubkey = Pubkey.from_string(owner)
    nft_mint = Pubkey.from_string(position_state["nft_mint"])

    # Detect NFT token program
    if rpc:
        token_program_nft = detect_token_program_for_mint(rpc, nft_mint)
    else:
        # Default to Token-2022 for newer positions
        token_program_nft = Pubkey.from_string(TOKEN_2022_PROGRAM_ID)

    # Get NFT token account with correct token program
    nft_account = get_associated_token_address(owner_pubkey, nft_mint, token_program_nft)

    # Personal position PDA
    personal_position = derive_personal_position(nft_mint, pid)

    # Build close position instruction
    # Try close_position (legacy) first since close_position_v2 may have different requirements
    # Note: Owner receives rent, so must be writable
    data = DISCRIMINATORS["close_position"]

    accounts = [
        AccountMeta(owner_pubkey, is_signer=True, is_writable=True),   # nft_owner - receives rent
        AccountMeta(nft_mint, is_signer=False, is_writable=True),       # position_nft_mint - burned
        AccountMeta(nft_account, is_signer=False, is_writable=True),    # position_nft_account - closed
        AccountMeta(personal_position, is_signer=False, is_writable=True),  # personal_position - closed
        AccountMeta(Pubkey.from_string(SYSTEM_PROGRAM_ID), is_signer=False, is_writable=False),
        AccountMeta(token_program_nft, is_signer=False, is_writable=False),
    ]

    instruction = Instruction(pid, bytes(data), accounts)
    return [instruction]


def build_decrease_liquidity_instructions(
    position_state: dict,
    pool_state: dict,
    owner: str,
    liquidity_delta: int,
    amount_0_min: int,
    amount_1_min: int,
    rpc=None,
    program_id: Optional[str] = None,
) -> List["Instruction"]:
    """
    Build instruction to decrease liquidity.

    Includes proper handling for:
    - Token program auto-detection per mint
    - Reward accounts (from pool state or manual overrides)
    - ATA creation for reward tokens

    Args:
        position_state: Parsed position state
        pool_state: Parsed pool state
        owner: Owner wallet
        liquidity_delta: Liquidity to remove
        amount_0_min: Min token 0 to receive
        amount_1_min: Min token 1 to receive
        rpc: Optional RPC client for token program detection
        program_id: Optional program ID override

    Returns:
        List of instructions
    """
    from solders.pubkey import Pubkey
    from solders.instruction import Instruction, AccountMeta

    instructions = []

    pid = Pubkey.from_string(program_id or CLMM_PROGRAM_ID)
    owner_pubkey = Pubkey.from_string(owner)
    nft_mint = Pubkey.from_string(position_state["nft_mint"])
    pool_pubkey = Pubkey.from_string(position_state["pool_id"])

    # Detect NFT token program
    if rpc:
        token_program_nft = detect_token_program_for_mint(rpc, nft_mint)
    else:
        token_program_nft = Pubkey.from_string(TOKEN_PROGRAM_ID)

    # Get NFT token account
    nft_account = get_associated_token_address(owner_pubkey, nft_mint, token_program_nft)

    # Personal position PDA
    personal_position = derive_personal_position(nft_mint, pid)

    # Protocol position
    tick_lower = position_state["tick_lower"]
    tick_upper = position_state["tick_upper"]
    protocol_position = derive_protocol_position(pool_pubkey, tick_lower, tick_upper, pid)

    # Token vaults and mints
    vault_a = Pubkey.from_string(pool_state["vault_a"])
    vault_b = Pubkey.from_string(pool_state["vault_b"])
    mint_a = Pubkey.from_string(pool_state["mint_a"])
    mint_b = Pubkey.from_string(pool_state["mint_b"])

    # Detect token programs
    if rpc:
        prog_a = detect_token_program_for_mint(rpc, mint_a)
        prog_b = detect_token_program_for_mint(rpc, mint_b)
    else:
        prog_a = Pubkey.from_string(TOKEN_PROGRAM_ID)
        prog_b = Pubkey.from_string(TOKEN_PROGRAM_ID)

    # Get token accounts
    token_account_a = get_associated_token_address(owner_pubkey, mint_a, prog_a)
    token_account_b = get_associated_token_address(owner_pubkey, mint_b, prog_b)

    # Ensure ATAs exist for receiving tokens
    instructions.append(build_create_ata_idempotent_instruction(owner_pubkey, owner_pubkey, mint_a, prog_a))
    instructions.append(build_create_ata_idempotent_instruction(owner_pubkey, owner_pubkey, mint_b, prog_b))

    # Tick arrays with floor-based alignment
    tick_spacing = pool_state["tick_spacing"]
    step = TICK_ARRAY_SIZE * tick_spacing

    # For decrease, we need tick arrays containing the position bounds
    ta_lower_start = (tick_lower // step) * step
    ta_upper_start = ((tick_upper - 1) // step) * step

    # Ensure correct ordering (lower first)
    if ta_lower_start > ta_upper_start:
        ta_lower_start, ta_upper_start = ta_upper_start, ta_lower_start

    tick_array_lower = derive_tick_array_address(pool_pubkey, tick_lower, tick_spacing, pid)
    tick_array_upper = derive_tick_array_address(pool_pubkey, tick_upper - 1, tick_spacing, pid)

    # Build data for decrease_liquidity_v2
    data = bytearray(DISCRIMINATORS["decrease_liquidity_v2"])
    data.extend(liquidity_delta.to_bytes(16, "little"))
    data.extend(struct.pack("<Q", amount_0_min))
    data.extend(struct.pack("<Q", amount_1_min))

    # Base accounts
    base_metas = [
        AccountMeta(owner_pubkey, is_signer=True, is_writable=True),
        AccountMeta(nft_account, is_signer=False, is_writable=True),
        AccountMeta(personal_position, is_signer=False, is_writable=True),
        AccountMeta(pool_pubkey, is_signer=False, is_writable=True),
        AccountMeta(protocol_position, is_signer=False, is_writable=False),
        AccountMeta(vault_a, is_signer=False, is_writable=True),
        AccountMeta(vault_b, is_signer=False, is_writable=True),
        AccountMeta(tick_array_lower, is_signer=False, is_writable=True),
        AccountMeta(tick_array_upper, is_signer=False, is_writable=True),
        AccountMeta(token_account_a, is_signer=False, is_writable=True),
        AccountMeta(token_account_b, is_signer=False, is_writable=True),
        AccountMeta(Pubkey.from_string(TOKEN_PROGRAM_ID), is_signer=False, is_writable=False),
        AccountMeta(Pubkey.from_string(TOKEN_2022_PROGRAM_ID), is_signer=False, is_writable=False),
        AccountMeta(Pubkey.from_string(MEMO_PROGRAM_ID), is_signer=False, is_writable=False),
        AccountMeta(mint_a, is_signer=False, is_writable=False),
        AccountMeta(mint_b, is_signer=False, is_writable=False),
    ]

    # Handle reward accounts
    reward_metas = []
    pool_address_str = str(pool_pubkey)

    # Invalid/uninitialized reward mints to skip
    # These are default values that indicate the reward slot is not actually configured
    INVALID_REWARD_MINTS = {
        SYSTEM_PROGRAM_ID,  # 11111111111111111111111111111111
        "11111111111111111111111111111111",
        "",
    }

    # Try pool state reward_infos first
    reward_infos = pool_state.get("reward_infos", [])
    for reward_info in reward_infos:
        # Check if reward is initialized (use reward_state or initialized field)
        # Raydium reward_state: 0=uninitialized, 1=initialized, 2=opening, 3=ended
        reward_state = reward_info.get("reward_state", 0)
        initialized = reward_info.get("initialized", reward_state in (1, 2, 3))

        if not initialized:
            continue

        reward_mint_str = reward_info.get("token_mint")
        reward_vault_str = reward_info.get("token_vault")

        if not reward_mint_str or not reward_vault_str:
            continue

        # Skip invalid/default reward mints (indicates uninitialized reward slot)
        if reward_mint_str in INVALID_REWARD_MINTS:
            continue

        reward_mint = Pubkey.from_string(reward_mint_str)
        reward_vault = Pubkey.from_string(reward_vault_str)

        # Detect token program for reward
        if rpc:
            prog_reward = detect_token_program_for_mint(rpc, reward_mint)
        else:
            prog_reward = Pubkey.from_string(TOKEN_PROGRAM_ID)

        reward_ata = get_associated_token_address(owner_pubkey, reward_mint, prog_reward)

        # Create reward ATA if needed
        instructions.append(build_create_ata_idempotent_instruction(
            owner_pubkey, owner_pubkey, reward_mint, prog_reward
        ))

        reward_metas.extend([
            AccountMeta(reward_vault, is_signer=False, is_writable=True),
            AccountMeta(reward_ata, is_signer=False, is_writable=True),
            AccountMeta(reward_mint, is_signer=False, is_writable=False),
        ])

    # If no rewards from pool state, check manual overrides
    if not reward_metas and pool_address_str in MANUAL_REWARD_OVERRIDES:
        for reward_mint_str, reward_vault_str in MANUAL_REWARD_OVERRIDES[pool_address_str]:
            reward_mint = Pubkey.from_string(reward_mint_str)
            reward_vault = Pubkey.from_string(reward_vault_str)

            if rpc:
                prog_reward = detect_token_program_for_mint(rpc, reward_mint)
            else:
                prog_reward = Pubkey.from_string(TOKEN_PROGRAM_ID)

            reward_ata = get_associated_token_address(owner_pubkey, reward_mint, prog_reward)

            instructions.append(build_create_ata_idempotent_instruction(
                owner_pubkey, owner_pubkey, reward_mint, prog_reward
            ))

            reward_metas.extend([
                AccountMeta(reward_vault, is_signer=False, is_writable=True),
                AccountMeta(reward_ata, is_signer=False, is_writable=True),
                AccountMeta(reward_mint, is_signer=False, is_writable=False),
            ])

    # Combine all accounts
    all_metas = base_metas + reward_metas

    instruction = Instruction(pid, bytes(data), all_metas)
    instructions.append(instruction)

    return instructions


def build_increase_liquidity_instructions(
    position_state: dict,
    pool_state: dict,
    owner: str,
    liquidity_delta: int,
    amount_0_max: int,
    amount_1_max: int,
    base_flag: Optional[bool] = None,
    rpc=None,
    program_id: Optional[str] = None,
) -> List["Instruction"]:
    """
    Build instruction to increase liquidity (add to existing position).

    Args:
        position_state: Parsed position state
        pool_state: Parsed pool state
        owner: Owner wallet
        liquidity_delta: Liquidity to add
        amount_0_max: Max token 0 to deposit
        amount_1_max: Max token 1 to deposit
        base_flag: Optional base flag
        rpc: Optional RPC client for token program detection
        program_id: Optional program ID override

    Returns:
        List of instructions
    """
    from solders.pubkey import Pubkey
    from solders.instruction import Instruction, AccountMeta

    instructions = []

    pid = Pubkey.from_string(program_id or CLMM_PROGRAM_ID)
    owner_pubkey = Pubkey.from_string(owner)
    nft_mint = Pubkey.from_string(position_state["nft_mint"])
    pool_pubkey = Pubkey.from_string(position_state["pool_id"])

    # Detect NFT token program
    if rpc:
        token_program_nft = detect_token_program_for_mint(rpc, nft_mint)
    else:
        token_program_nft = Pubkey.from_string(TOKEN_PROGRAM_ID)

    nft_account = get_associated_token_address(owner_pubkey, nft_mint, token_program_nft)
    personal_position = derive_personal_position(nft_mint, pid)

    tick_lower = position_state["tick_lower"]
    tick_upper = position_state["tick_upper"]
    protocol_position = derive_protocol_position(pool_pubkey, tick_lower, tick_upper, pid)

    vault_a = Pubkey.from_string(pool_state["vault_a"])
    vault_b = Pubkey.from_string(pool_state["vault_b"])
    mint_a = Pubkey.from_string(pool_state["mint_a"])
    mint_b = Pubkey.from_string(pool_state["mint_b"])

    # Detect token programs
    if rpc:
        prog_a = detect_token_program_for_mint(rpc, mint_a)
        prog_b = detect_token_program_for_mint(rpc, mint_b)
    else:
        prog_a = Pubkey.from_string(TOKEN_PROGRAM_ID)
        prog_b = Pubkey.from_string(TOKEN_PROGRAM_ID)

    token_account_a = get_associated_token_address(owner_pubkey, mint_a, prog_a)
    token_account_b = get_associated_token_address(owner_pubkey, mint_b, prog_b)

    tick_spacing = pool_state["tick_spacing"]
    tick_array_lower = derive_tick_array_address(pool_pubkey, tick_lower, tick_spacing, pid)
    tick_array_upper = derive_tick_array_address(pool_pubkey, tick_upper - 1, tick_spacing, pid)

    # Build wrap SOL instructions if needed (see WSOL_WRAP_BUFFER_LAMPORTS for buffer docs)
    if pool_state["mint_a"] == WRAPPED_SOL_MINT and amount_0_max > 0:
        wrap_amount = amount_0_max + WSOL_WRAP_BUFFER_LAMPORTS
        instructions.extend(build_wrap_sol_instructions(owner, wrap_amount))
    if pool_state["mint_b"] == WRAPPED_SOL_MINT and amount_1_max > 0:
        wrap_amount = amount_1_max + WSOL_WRAP_BUFFER_LAMPORTS
        instructions.extend(build_wrap_sol_instructions(owner, wrap_amount))

    # Build data for increase_liquidity_v2
    data = bytearray(DISCRIMINATORS["increase_liquidity_v2"])
    data.extend(liquidity_delta.to_bytes(16, "little"))
    data.extend(struct.pack("<Q", amount_0_max))
    data.extend(struct.pack("<Q", amount_1_max))

    # Optional base_flag
    if base_flag is None:
        data.extend(b"\x00")
    else:
        data.extend(b"\x01" + (b"\x01" if base_flag else b"\x00"))

    # Account order for IncreaseLiquidityV2
    accounts = [
        AccountMeta(owner_pubkey, is_signer=True, is_writable=False),
        AccountMeta(nft_account, is_signer=False, is_writable=False),
        AccountMeta(pool_pubkey, is_signer=False, is_writable=True),
        AccountMeta(protocol_position, is_signer=False, is_writable=True),
        AccountMeta(personal_position, is_signer=False, is_writable=True),
        AccountMeta(tick_array_lower, is_signer=False, is_writable=True),
        AccountMeta(tick_array_upper, is_signer=False, is_writable=True),
        AccountMeta(token_account_a, is_signer=False, is_writable=True),
        AccountMeta(token_account_b, is_signer=False, is_writable=True),
        AccountMeta(vault_a, is_signer=False, is_writable=True),
        AccountMeta(vault_b, is_signer=False, is_writable=True),
        AccountMeta(Pubkey.from_string(TOKEN_PROGRAM_ID), is_signer=False, is_writable=False),
        AccountMeta(Pubkey.from_string(TOKEN_2022_PROGRAM_ID), is_signer=False, is_writable=False),
        AccountMeta(mint_a, is_signer=False, is_writable=False),
        AccountMeta(mint_b, is_signer=False, is_writable=False),
    ]

    instruction = Instruction(pid, bytes(data), accounts)
    instructions.append(instruction)

    return instructions


def build_wrap_sol_instructions(
    owner: str,
    amount_lamports: int,
) -> List["Instruction"]:
    """
    Build instructions to wrap SOL to WSOL.

    Args:
        owner: Wallet owner
        amount_lamports: Amount of SOL to wrap

    Returns:
        List of instructions
    """
    from solders.pubkey import Pubkey
    from solders.instruction import Instruction, AccountMeta

    instructions = []
    owner_pubkey = Pubkey.from_string(owner)
    wsol_mint = Pubkey.from_string(WRAPPED_SOL_MINT)
    token_program = Pubkey.from_string(TOKEN_PROGRAM_ID)

    # WSOL always uses Tokenkeg
    wsol_ata = get_associated_token_address(owner_pubkey, wsol_mint, token_program)

    # 1. Create WSOL ATA if needed
    instructions.append(build_create_ata_idempotent_instruction(
        owner_pubkey, owner_pubkey, wsol_mint, token_program
    ))

    # 2. Transfer SOL to WSOL ATA
    system_program = Pubkey.from_string(SYSTEM_PROGRAM_ID)
    transfer_accounts = [
        AccountMeta(owner_pubkey, is_signer=True, is_writable=True),
        AccountMeta(wsol_ata, is_signer=False, is_writable=True),
    ]
    transfer_data = struct.pack("<I", 2) + struct.pack("<Q", amount_lamports)
    instructions.append(Instruction(system_program, transfer_data, transfer_accounts))

    # 3. Sync native balance
    sync_accounts = [
        AccountMeta(wsol_ata, is_signer=False, is_writable=True),
    ]
    instructions.append(Instruction(token_program, bytes([17]), sync_accounts))

    return instructions


def build_unwrap_wsol_instructions(
    owner: str,
    rpc=None,
) -> List["Instruction"]:
    """
    Build instructions to unwrap all WSOL back to SOL.

    This closes all WSOL token accounts owned by the user.

    Args:
        owner: Wallet owner
        rpc: Optional RPC client to find WSOL accounts

    Returns:
        List of close account instructions
    """
    from solders.pubkey import Pubkey
    from solders.instruction import Instruction, AccountMeta

    instructions = []
    owner_pubkey = Pubkey.from_string(owner)
    wsol_mint = Pubkey.from_string(WRAPPED_SOL_MINT)
    token_program = Pubkey.from_string(TOKEN_PROGRAM_ID)

    # Get WSOL ATA
    wsol_ata = get_associated_token_address(owner_pubkey, wsol_mint, token_program)

    # Build close account instruction (cmd=9)
    # This closes the token account and returns SOL to owner
    close_accounts = [
        AccountMeta(wsol_ata, is_signer=False, is_writable=True),
        AccountMeta(owner_pubkey, is_signer=False, is_writable=True),
        AccountMeta(owner_pubkey, is_signer=True, is_writable=False),
    ]

    instructions.append(Instruction(token_program, bytes([9]), close_accounts))

    return instructions
