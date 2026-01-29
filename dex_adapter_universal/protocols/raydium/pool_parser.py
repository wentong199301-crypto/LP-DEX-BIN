"""
Raydium CLMM Pool State Parser

Parses pool account data from chain.
"""

import struct
import base64
from decimal import Decimal
from typing import Dict, Any, Optional

from ...types import Pool, Token
from ...types.common import STABLECOINS
from ...types.solana_tokens import get_token_symbol
from ...infra import RpcClient
from .constants import CLMM_PROGRAM_ID
from .math import sqrt_price_x64_to_price


def parse_amm_config(account_data: bytes) -> Dict[str, Any]:
    """
    Parse AmmConfig account data.

    Layout (verified from on-chain data):
    - blob(8): discriminator
    - u8: bump (offset 8)
    - padding(2): alignment padding (offset 9-10)
    - u16: index (offset 11)
    - publicKey(32): owner (offset 13)
    - u16: tick_spacing (offset 45)
    - u32: trade_fee_rate (offset 47) - in 1e-6 units (e.g., 100 = 0.01%)
    - u16: protocol_fee_rate (offset 51) - percentage of trade fee
    - u64: create_pool_fee (offset 53)
    - publicKey(32): fund_owner (offset 61)
    - ...

    Args:
        account_data: Raw account data bytes

    Returns:
        Parsed config dict with fee rates as Decimals
    """
    # tick_spacing at offset 45
    tick_spacing = struct.unpack_from("<H", account_data, 45)[0]

    # trade_fee_rate at offset 47 (u32, in 1e-6 units)
    trade_fee_rate_raw = struct.unpack_from("<I", account_data, 47)[0]

    # protocol_fee_rate at offset 51 (u16, percentage of trade fee)
    protocol_fee_rate_raw = struct.unpack_from("<H", account_data, 51)[0]

    # Convert trade_fee_rate to decimal ratio (divide by 1e6)
    # e.g., 100 -> 0.0001 -> 0.01%
    trade_fee_rate = Decimal(trade_fee_rate_raw) / Decimal(1_000_000)

    # Protocol fee is a percentage of the trade fee (not used directly)
    protocol_fee_rate = Decimal(protocol_fee_rate_raw) / Decimal(100)

    return {
        "trade_fee_rate": trade_fee_rate,
        "protocol_fee_rate": protocol_fee_rate,
        "tick_spacing": tick_spacing,
    }


def fetch_amm_config(rpc: RpcClient, config_address: str) -> Optional[Dict[str, Any]]:
    """
    Fetch and parse AmmConfig account from RPC.

    Args:
        rpc: RPC client
        config_address: AmmConfig account address

    Returns:
        Parsed config dict or None if fetch fails
    """
    try:
        account = rpc.get_account_info(config_address, encoding="base64")
        if not account:
            return None

        data = account.get("data", [])
        if isinstance(data, list) and len(data) > 0:
            raw_data = base64.b64decode(data[0])
        elif isinstance(data, str):
            raw_data = base64.b64decode(data)
        else:
            return None

        return parse_amm_config(raw_data)
    except Exception:
        return None


def parse_pool_state(account_data: bytes) -> Dict[str, Any]:
    """
    Parse CLMM pool state account (PoolInfoLayout)

    Layout:
    - blob(8): discriminator
    - u8: bump
    - publicKey(32): ammConfig
    - publicKey(32): creator
    - publicKey(32): mintA
    - publicKey(32): mintB
    - publicKey(32): vaultA
    - publicKey(32): vaultB
    - publicKey(32): observationId
    - u8: mintDecimalsA
    - u8: mintDecimalsB
    - u16: tickSpacing
    - u128: liquidity
    - u128: sqrtPriceX64
    - s32: tickCurrent
    - u32: padding
    - ... (fees, rewards, etc.)

    Args:
        account_data: Raw account data bytes

    Returns:
        Parsed pool state dict
    """
    offset = 0

    # Discriminator (8 bytes)
    discriminator = account_data[offset:offset + 8]
    offset += 8

    # bump (1 byte)
    bump = account_data[offset]
    offset += 1

    # ammConfig (32 bytes)
    amm_config = _pubkey_from_bytes(account_data[offset:offset + 32])
    offset += 32

    # creator (32 bytes)
    creator = _pubkey_from_bytes(account_data[offset:offset + 32])
    offset += 32

    # mintA (32 bytes)
    mint_a = _pubkey_from_bytes(account_data[offset:offset + 32])
    offset += 32

    # mintB (32 bytes)
    mint_b = _pubkey_from_bytes(account_data[offset:offset + 32])
    offset += 32

    # vaultA (32 bytes)
    vault_a = _pubkey_from_bytes(account_data[offset:offset + 32])
    offset += 32

    # vaultB (32 bytes)
    vault_b = _pubkey_from_bytes(account_data[offset:offset + 32])
    offset += 32

    # observationId (32 bytes)
    observation_id = _pubkey_from_bytes(account_data[offset:offset + 32])
    offset += 32

    # mintDecimalsA (1 byte)
    mint_decimals_a = account_data[offset]
    offset += 1

    # mintDecimalsB (1 byte)
    mint_decimals_b = account_data[offset]
    offset += 1

    # tickSpacing (2 bytes, u16)
    tick_spacing = struct.unpack_from("<H", account_data, offset)[0]
    offset += 2

    # liquidity (16 bytes, u128)
    liquidity = int.from_bytes(account_data[offset:offset + 16], "little")
    offset += 16

    # sqrtPriceX64 (16 bytes, u128)
    sqrt_price_x64 = int.from_bytes(account_data[offset:offset + 16], "little")
    offset += 16

    # tickCurrent (4 bytes, s32)
    tick_current = struct.unpack_from("<i", account_data, offset)[0]
    offset += 4

    # padding (4 bytes)
    offset += 4

    # feeGrowthGlobalX64A (16 bytes)
    fee_growth_global_a = int.from_bytes(account_data[offset:offset + 16], "little")
    offset += 16

    # feeGrowthGlobalX64B (16 bytes)
    fee_growth_global_b = int.from_bytes(account_data[offset:offset + 16], "little")
    offset += 16

    # protocolFeesTokenA (8 bytes)
    protocol_fees_a = struct.unpack_from("<Q", account_data, offset)[0]
    offset += 8

    # protocolFeesTokenB (8 bytes)
    protocol_fees_b = struct.unpack_from("<Q", account_data, offset)[0]
    offset += 8

    # Skip swap amounts (4 x 16 bytes = 64 bytes)
    offset += 64

    # status (1 byte)
    status = account_data[offset]
    offset += 1

    # Parse 7 bytes of padding
    offset += 7

    # Parse reward_infos (3 x 169 bytes = 507 bytes)
    reward_infos = []
    for i in range(3):
        reward_info = _parse_reward_info(account_data, offset)
        reward_infos.append(reward_info)
        offset += 169  # Size of RewardInfo struct

    return {
        "discriminator": discriminator.hex(),
        "bump": bump,
        "amm_config": amm_config,
        "creator": creator,
        "mint_a": mint_a,
        "mint_b": mint_b,
        "vault_a": vault_a,
        "vault_b": vault_b,
        "observation_id": observation_id,
        "mint_decimals_a": mint_decimals_a,
        "mint_decimals_b": mint_decimals_b,
        "tick_spacing": tick_spacing,
        "liquidity": liquidity,
        "sqrt_price_x64": sqrt_price_x64,
        "tick_current": tick_current,
        "fee_growth_global_a": fee_growth_global_a,
        "fee_growth_global_b": fee_growth_global_b,
        "protocol_fees_a": protocol_fees_a,
        "protocol_fees_b": protocol_fees_b,
        "status": status,
        "reward_infos": reward_infos,
    }


def fetch_pool_state(
    rpc: RpcClient,
    pool_address: str,
) -> Dict[str, Any]:
    """
    Fetch and parse pool state from RPC

    Args:
        rpc: RPC client
        pool_address: Pool address

    Returns:
        Parsed pool state

    Raises:
        PoolUnavailable: If pool not found or not owned by Raydium CLMM program
    """
    from ...errors import PoolUnavailable

    account = rpc.get_account_info(pool_address, encoding="base64")
    if not account:
        raise PoolUnavailable.not_found(pool_address)

    # Validate account owner matches Raydium CLMM program ID
    owner = account.get("owner")
    if owner != CLMM_PROGRAM_ID:
        raise PoolUnavailable.invalid_state(
            pool_address,
            f"Account not owned by Raydium CLMM program (owner={owner})"
        )

    data = account.get("data", [])
    if isinstance(data, list) and len(data) > 0:
        raw_data = base64.b64decode(data[0])
    elif isinstance(data, str):
        raw_data = base64.b64decode(data)
    else:
        raise PoolUnavailable.invalid_state(pool_address, "Invalid account data format")

    return parse_pool_state(raw_data)


def _calculate_tvl(
    rpc: RpcClient,
    vault_a: str,
    vault_b: str,
    decimals_a: int,
    decimals_b: int,
    price: Decimal,
    symbol_a: str = "",
    symbol_b: str = "",
) -> Decimal:
    """
    Calculate TVL from vault balances.

    Args:
        rpc: RPC client
        vault_a: Token A vault address
        vault_b: Token B vault address
        decimals_a: Token A decimals
        decimals_b: Token B decimals
        price: Token A price in Token B terms
        symbol_a: Token A symbol (for stablecoin detection)
        symbol_b: Token B symbol (for stablecoin detection)

    Returns:
        TVL in USD
    """
    # Fetch vault balances
    balance_a_raw = _get_token_balance(rpc, vault_a)
    balance_b_raw = _get_token_balance(rpc, vault_b)

    # Convert to UI amounts
    balance_a = Decimal(balance_a_raw) / Decimal(10 ** decimals_a)
    balance_b = Decimal(balance_b_raw) / Decimal(10 ** decimals_b)

    # Detect which token is the stablecoin
    token_a_is_stable = symbol_a.upper() in STABLECOINS
    token_b_is_stable = symbol_b.upper() in STABLECOINS

    if token_a_is_stable and not token_b_is_stable:
        # Token A is stablecoin: TVL = balance_a + (balance_b / price)
        if price > 0:
            tvl = balance_a + (balance_b / price)
        else:
            tvl = balance_a
    else:
        # Token B is stablecoin (or both/neither): TVL = (balance_a * price) + balance_b
        tvl = (balance_a * price) + balance_b

    return tvl


def _get_token_balance(rpc: RpcClient, token_account: str) -> int:
    """
    Get token balance from a token account.

    Args:
        rpc: RPC client
        token_account: Token account address

    Returns:
        Raw token balance (lamports/smallest unit)
    """
    try:
        result = rpc.get_token_account_balance(token_account)
        if result and "amount" in result:
            return int(result["amount"])
    except Exception:
        pass
    return 0


def pool_state_to_pool(
    pool_address: str,
    state: Dict[str, Any],
    token_a: Optional[Token] = None,
    token_b: Optional[Token] = None,
    rpc: Optional[RpcClient] = None,
) -> Pool:
    """
    Convert parsed pool state to Pool dataclass

    Args:
        pool_address: Pool address
        state: Parsed pool state dict
        token_a: Optional token A info
        token_b: Optional token B info
        rpc: Optional RPC client for fetching vault balances (needed for TVL)

    Returns:
        Pool dataclass
    """
    decimals_a = state["mint_decimals_a"]
    decimals_b = state["mint_decimals_b"]

    # Calculate price
    price = sqrt_price_x64_to_price(
        state["sqrt_price_x64"],
        decimals_a,
        decimals_b,
    )

    # Create token objects if not provided
    if token_a is None:
        symbol_a = get_token_symbol(state["mint_a"]) or state["mint_a"][:8]
        token_a = Token(
            mint=state["mint_a"],
            symbol=symbol_a,
            decimals=decimals_a,
        )

    if token_b is None:
        symbol_b = get_token_symbol(state["mint_b"]) or state["mint_b"][:8]
        token_b = Token(
            mint=state["mint_b"],
            symbol=symbol_b,
            decimals=decimals_b,
        )

    # Construct symbol
    symbol = f"{token_a.symbol or 'TOKEN_A'}/{token_b.symbol or 'TOKEN_B'}"

    # Calculate TVL from vault balances and fetch fee rate
    tvl_usd = Decimal(0)
    fee_rate = Decimal("0.0025")  # Default fallback
    protocol_fee_rate = Decimal(0)
    fund_fee_rate = Decimal(0)

    if rpc is not None:
        # Fetch TVL
        try:
            tvl_usd = _calculate_tvl(
                rpc=rpc,
                vault_a=state["vault_a"],
                vault_b=state["vault_b"],
                decimals_a=decimals_a,
                decimals_b=decimals_b,
                price=price,
                symbol_a=token_a.symbol or "",
                symbol_b=token_b.symbol or "",
            )
        except Exception:
            pass  # TVL calculation failed, use default 0

        # Fetch fee rate from AmmConfig
        amm_config = fetch_amm_config(rpc, state["amm_config"])
        if amm_config:
            fee_rate = amm_config["trade_fee_rate"]
            protocol_fee_rate = amm_config["protocol_fee_rate"]

    return Pool(
        address=pool_address,
        dex="raydium",
        symbol=symbol,
        token0=token_a,
        token1=token_b,
        price=price,
        tvl_usd=tvl_usd,
        fee_rate=fee_rate,
        protocol_fee_rate=protocol_fee_rate,
        fund_fee_rate=fund_fee_rate,
        tick_spacing=state["tick_spacing"],
        current_tick=state["tick_current"],
        sqrt_price_x64=state["sqrt_price_x64"],
        metadata={
            "liquidity": state["liquidity"],
            "amm_config": state["amm_config"],
            "vault_a": state["vault_a"],
            "vault_b": state["vault_b"],
            "status": state["status"],
        },
    )


def _pubkey_from_bytes(data: bytes) -> str:
    """Convert 32 bytes to base58 pubkey string"""
    import base58
    return base58.b58encode(data).decode("ascii")


def _parse_reward_info(account_data: bytes, offset: int) -> Dict[str, Any]:
    """
    Parse RewardInfo struct (169 bytes)

    Layout:
    - reward_state: u8 (1 byte)
    - open_time: u64 (8 bytes)
    - end_time: u64 (8 bytes)
    - last_update_time: u64 (8 bytes)
    - emissions_per_second_x64: u128 (16 bytes)
    - reward_total_emissioned: u64 (8 bytes)
    - reward_claimed: u64 (8 bytes)
    - token_mint: Pubkey (32 bytes)
    - token_vault: Pubkey (32 bytes)
    - authority: Pubkey (32 bytes)
    - reward_growth_global_x64: u128 (16 bytes)

    Total: 169 bytes
    """
    reward_state = account_data[offset]
    offset += 1

    open_time = struct.unpack_from("<Q", account_data, offset)[0]
    offset += 8

    end_time = struct.unpack_from("<Q", account_data, offset)[0]
    offset += 8

    last_update_time = struct.unpack_from("<Q", account_data, offset)[0]
    offset += 8

    emissions_per_second_x64 = int.from_bytes(account_data[offset:offset + 16], "little")
    offset += 16

    reward_total_emissioned = struct.unpack_from("<Q", account_data, offset)[0]
    offset += 8

    reward_claimed = struct.unpack_from("<Q", account_data, offset)[0]
    offset += 8

    token_mint = _pubkey_from_bytes(account_data[offset:offset + 32])
    offset += 32

    token_vault = _pubkey_from_bytes(account_data[offset:offset + 32])
    offset += 32

    authority = _pubkey_from_bytes(account_data[offset:offset + 32])
    offset += 32

    reward_growth_global_x64 = int.from_bytes(account_data[offset:offset + 16], "little")

    return {
        "reward_state": reward_state,
        "open_time": open_time,
        "end_time": end_time,
        "last_update_time": last_update_time,
        "emissions_per_second_x64": emissions_per_second_x64,
        "reward_total_emissioned": reward_total_emissioned,
        "reward_claimed": reward_claimed,
        "token_mint": token_mint,
        "token_vault": token_vault,
        "authority": authority,
        "reward_growth_global_x64": reward_growth_global_x64,
    }
