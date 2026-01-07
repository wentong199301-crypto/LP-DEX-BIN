"""
Raydium CLMM Position Parser

Parses position account data from chain.

Based on raydium_trading reference implementation.
Supports both Tokenkeg and Token-2022 NFT positions.

Token Naming Convention:
    - token0 / mint_a: The first token in the pool (base token)
    - token1 / mint_b: The second token in the pool (quote token)
"""

import logging
import struct
import base64
from decimal import Decimal
from datetime import datetime
from typing import Dict, Any, List, Optional

from ...types import Position, Pool
from ...infra import RpcClient
from .constants import CLMM_PROGRAM_ID, TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID, PP_DISCRIMINATORS
from .math import tick_to_price, get_amounts_from_liquidity, tick_to_sqrt_price_x64

logger = logging.getLogger(__name__)


def parse_position_state(account_data: bytes) -> Dict[str, Any]:
    """
    Parse personal position account (PersonalPositionState)

    Layout:
    - blob(8): discriminator
    - u8: bump
    - publicKey(32): nftMint
    - publicKey(32): poolId
    - i32: tickLowerIndex
    - i32: tickUpperIndex
    - u128: liquidity
    - u128: feeGrowthInsideLastX64A
    - u128: feeGrowthInsideLastX64B
    - u64: tokenFeesOwedA
    - u64: tokenFeesOwedB
    - ... (reward info)

    Args:
        account_data: Raw account data bytes

    Returns:
        Parsed position state dict
    """
    offset = 0

    # Discriminator (8 bytes)
    discriminator = account_data[offset:offset + 8]
    offset += 8

    # bump (1 byte)
    bump = account_data[offset]
    offset += 1

    # nftMint (32 bytes)
    nft_mint = _pubkey_from_bytes(account_data[offset:offset + 32])
    offset += 32

    # poolId (32 bytes)
    pool_id = _pubkey_from_bytes(account_data[offset:offset + 32])
    offset += 32

    # tickLowerIndex (4 bytes, i32)
    tick_lower = struct.unpack_from("<i", account_data, offset)[0]
    offset += 4

    # tickUpperIndex (4 bytes, i32)
    tick_upper = struct.unpack_from("<i", account_data, offset)[0]
    offset += 4

    # liquidity (16 bytes, u128)
    liquidity = int.from_bytes(account_data[offset:offset + 16], "little")
    offset += 16

    # feeGrowthInsideLastX64A (16 bytes)
    fee_growth_inside_a = int.from_bytes(account_data[offset:offset + 16], "little")
    offset += 16

    # feeGrowthInsideLastX64B (16 bytes)
    fee_growth_inside_b = int.from_bytes(account_data[offset:offset + 16], "little")
    offset += 16

    # tokenFeesOwedA (8 bytes)
    fees_owed_a = struct.unpack_from("<Q", account_data, offset)[0]
    offset += 8

    # tokenFeesOwedB (8 bytes)
    fees_owed_b = struct.unpack_from("<Q", account_data, offset)[0]
    offset += 8

    return {
        "discriminator": discriminator.hex(),
        "bump": bump,
        "nft_mint": nft_mint,
        "pool_id": pool_id,
        "tick_lower": tick_lower,
        "tick_upper": tick_upper,
        "liquidity": liquidity,
        "fee_growth_inside_a": fee_growth_inside_a,
        "fee_growth_inside_b": fee_growth_inside_b,
        "fees_owed_a": fees_owed_a,
        "fees_owed_b": fees_owed_b,
    }


def fetch_positions_by_owner(
    rpc: RpcClient,
    owner: str,
    pool_address: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Fetch all positions owned by address

    Uses getProgramAccounts with memcmp filter on owner.
    For Raydium, positions are identified by NFT ownership.

    Supports both Tokenkeg and Token-2022 NFT positions.

    Args:
        rpc: RPC client
        owner: Owner wallet address
        pool_address: Optional pool filter

    Returns:
        List of parsed position states
    """
    positions = []
    seen_mints = set()

    # Search both Tokenkeg and Token-2022 program accounts
    for program_id in [TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID]:
        try:
            token_accounts = rpc.get_token_accounts_by_owner(
                owner,
                program_id=program_id,
            )
        except Exception as e:
            logger.debug(f"Failed to fetch token accounts from {program_id}: {e}")
            continue

        if not token_accounts:
            continue

        for account in token_accounts:
            mint = None
            try:
                parsed = account.get("account", {}).get("data", {}).get("parsed", {})
                info = parsed.get("info", {})

                # Check if it's an NFT (amount = 1, decimals = 0)
                token_amount = info.get("tokenAmount", {})
                if token_amount.get("decimals") != 0:
                    continue
                if token_amount.get("amount") != "1":
                    continue

                mint = info.get("mint")
                if not mint:
                    continue

                # Skip if already processed
                if mint in seen_mints:
                    continue
                seen_mints.add(mint)

                # Try to derive position account from NFT mint
                position_address = derive_position_address(mint)
                if not position_address:
                    continue

                # Fetch position account
                position_account = rpc.get_account_info(position_address, encoding="base64")
                if not position_account:
                    continue

                data = position_account.get("data", [])
                if isinstance(data, list) and len(data) > 0:
                    raw_data = base64.b64decode(data[0])
                else:
                    continue

                # Check owner (program must be CLMM)
                if position_account.get("owner") != CLMM_PROGRAM_ID:
                    continue

                # Validate discriminator
                if len(raw_data) >= 8:
                    disc = raw_data[:8]
                    if disc not in PP_DISCRIMINATORS:
                        continue

                state = parse_position_state(raw_data)

                # Filter by pool if specified
                if pool_address and state["pool_id"] != pool_address:
                    continue

                state["position_address"] = position_address
                positions.append(state)

            except (ValueError, KeyError, struct.error) as e:
                # Expected parsing errors - skip silently
                logger.debug(f"Skipping invalid position data for mint {mint}: {e}")
                continue
            except Exception as e:
                # Unexpected errors - log warning
                logger.warning(f"Error processing position for mint {mint}: {e}", exc_info=True)
                continue

    return positions


def fetch_position_by_nft(
    rpc: RpcClient,
    nft_mint: str,
) -> Optional[Dict[str, Any]]:
    """
    Fetch position by NFT mint

    Args:
        rpc: RPC client
        nft_mint: Position NFT mint address

    Returns:
        Parsed position state or None
    """
    position_address = derive_position_address(nft_mint)
    if not position_address:
        return None

    account = rpc.get_account_info(position_address, encoding="base64")
    if not account:
        return None

    # Check owner (program must be CLMM)
    if account.get("owner") != CLMM_PROGRAM_ID:
        return None

    data = account.get("data", [])
    if isinstance(data, list) and len(data) > 0:
        raw_data = base64.b64decode(data[0])
    elif isinstance(data, str):
        raw_data = base64.b64decode(data)
    else:
        return None

    # Validate discriminator
    if len(raw_data) >= 8:
        disc = raw_data[:8]
        if disc not in PP_DISCRIMINATORS:
            return None

    state = parse_position_state(raw_data)
    state["position_address"] = position_address
    return state


def derive_position_address(nft_mint: str) -> Optional[str]:
    """
    Derive position account address from NFT mint

    PDA: [CLMM_PROGRAM_ID, "position", nft_mint]

    Args:
        nft_mint: Position NFT mint

    Returns:
        Position account address or None
    """
    try:
        from solders.pubkey import Pubkey

        program_id = Pubkey.from_string(CLMM_PROGRAM_ID)
        nft_mint_pubkey = Pubkey.from_string(nft_mint)

        seeds = [
            b"position",
            bytes(nft_mint_pubkey),
        ]

        position_pubkey, _ = Pubkey.find_program_address(seeds, program_id)
        return str(position_pubkey)
    except Exception:
        return None


def position_state_to_position(
    state: Dict[str, Any],
    pool: Pool,
    owner: str,
) -> Position:
    """
    Convert parsed position state to Position dataclass

    Args:
        state: Parsed position state dict
        pool: Pool information
        owner: Position owner address

    Returns:
        Position dataclass
    """
    tick_lower = state["tick_lower"]
    tick_upper = state["tick_upper"]
    liquidity = state["liquidity"]

    # Convert ticks to prices
    decimals_a = pool.token0.decimals
    decimals_b = pool.token1.decimals

    price_lower = tick_to_price(tick_lower, decimals_a, decimals_b)
    price_upper = tick_to_price(tick_upper, decimals_a, decimals_b)

    # Calculate token amounts
    sqrt_price_lower = tick_to_sqrt_price_x64(tick_lower)
    sqrt_price_upper = tick_to_sqrt_price_x64(tick_upper)
    sqrt_price_current = pool.sqrt_price_x64 or tick_to_sqrt_price_x64(pool.current_tick)

    amount_a, amount_b = get_amounts_from_liquidity(
        liquidity,
        sqrt_price_current,
        sqrt_price_lower,
        sqrt_price_upper,
    )

    # Convert to UI amounts
    ui_amount_a = Decimal(amount_a) / Decimal(10 ** decimals_a)
    ui_amount_b = Decimal(amount_b) / Decimal(10 ** decimals_b)

    # Check if in range
    is_in_range = tick_lower <= pool.current_tick < tick_upper

    # Unclaimed fees
    unclaimed_fees = {}
    if state["fees_owed_a"] > 0:
        unclaimed_fees[pool.token0.mint] = Decimal(state["fees_owed_a"]) / Decimal(10 ** decimals_a)
    if state["fees_owed_b"] > 0:
        unclaimed_fees[pool.token1.mint] = Decimal(state["fees_owed_b"]) / Decimal(10 ** decimals_b)

    return Position(
        id=state["nft_mint"],
        pool=pool,
        owner=owner,
        price_lower=price_lower,
        price_upper=price_upper,
        amount0=ui_amount_a,
        amount1=ui_amount_b,
        liquidity=liquidity,
        unclaimed_fees=unclaimed_fees,
        is_in_range=is_in_range,
        nft_mint=state["nft_mint"],
        tick_lower=tick_lower,
        tick_upper=tick_upper,
        position_address=state.get("position_address"),
        metadata={
            "pool_id": state["pool_id"],
        },
    )


def _pubkey_from_bytes(data: bytes) -> str:
    """Convert 32 bytes to base58 pubkey string"""
    import base58
    return base58.b58encode(data).decode("ascii")
