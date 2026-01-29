"""
Raydium CLMM Math Utilities

Provides tick/price conversion and liquidity calculations.
"""

import math
from decimal import Decimal
from typing import Tuple

from .constants import Q64, MAX_UINT128, MIN_TICK, MAX_TICK, TICK_ARRAY_SIZE
from ...errors import ConfigurationError


# Precomputed constants for tick_to_sqrt_price_x64
_TICK_CONSTANTS = [
    0x10000000000000000,
    0x10000000000000000,
    0xfff97272373d4130,
    0xfff2e50f5f656932,
    0xffe5caca7e10e6e2,
    0xffcb9843d37f513e,
    0xff973b41fa98c081,
    0xff2ea16466c96a3e,
    0xfe5dee046a99a2f8,
    0xfcbe86c7900a88a6,
    0xf987a7253ac41317,
    0xf3392b0822b70003,
    0xe7159475a2c29b64,
    0xd097f3bdfd2022b8,
    0xa9f746462d8706df,
    0x70d869a156d2a1b8,
    0x31be135f97d08fd9,
    0x9aa508b5b7a84e1c,
    0x5d6af8dedb811966,
    0x2216e584f5fa1ea,
    0x48a170391f7dc22,
]


def tick_to_sqrt_price_x64(tick: int) -> int:
    """
    Convert tick to sqrt price in X64 fixed-point format

    Args:
        tick: Tick index

    Returns:
        Sqrt price as X64 fixed-point integer
    """
    if tick < MIN_TICK or tick > MAX_TICK:
        raise ConfigurationError.invalid("tick", f"tick must be in [{MIN_TICK}, {MAX_TICK}], got {tick}")

    tick_abs = abs(tick)

    # Start with base ratio
    ratio = _TICK_CONSTANTS[1] if (tick_abs & 0x1) != 0 else _TICK_CONSTANTS[0]

    # Apply bit manipulations
    for i in range(1, 20):
        bit_mask = 1 << i
        if (tick_abs & bit_mask) != 0:
            ratio = (ratio * _TICK_CONSTANTS[i + 1]) >> 64

    # The algorithm computes ratio = 1.0001^(-|tick|)
    # For positive ticks, invert to get 1.0001^tick
    # Use 2^128 (not MAX_UINT128 which is 2^128-1) to avoid off-by-1 bias
    if tick > 0:
        ratio = (1 << 128) // ratio

    return ratio


def sqrt_price_x64_to_price(
    sqrt_price_x64: int,
    decimals_a: int,
    decimals_b: int,
) -> Decimal:
    """
    Convert sqrt price X64 to human-readable price

    Args:
        sqrt_price_x64: Sqrt price in X64 format
        decimals_a: Token A decimals
        decimals_b: Token B decimals

    Returns:
        Price of token A in terms of token B
    """
    # price = (sqrt_price_x64 / 2^64)^2 * 10^(decimals_a - decimals_b)
    sqrt_price = Decimal(sqrt_price_x64) / Decimal(Q64)
    price = sqrt_price * sqrt_price

    # Adjust for decimals
    decimal_adjustment = Decimal(10) ** (decimals_a - decimals_b)
    return price * decimal_adjustment


def price_to_sqrt_price_x64(
    price: Decimal,
    decimals_a: int,
    decimals_b: int,
) -> int:
    """
    Convert price to sqrt price X64

    Args:
        price: Price of token A in terms of token B
        decimals_a: Token A decimals
        decimals_b: Token B decimals

    Returns:
        Sqrt price in X64 format
    """
    # Adjust for decimals
    decimal_adjustment = Decimal(10) ** (decimals_a - decimals_b)
    adjusted_price = price / decimal_adjustment

    # sqrt_price_x64 = sqrt(adjusted_price) * 2^64
    sqrt_price = adjusted_price.sqrt()
    return int(sqrt_price * Q64)


def tick_to_price(
    tick: int,
    decimals_a: int,
    decimals_b: int,
) -> Decimal:
    """
    Convert tick to human-readable price

    Args:
        tick: Tick index
        decimals_a: Token A decimals
        decimals_b: Token B decimals

    Returns:
        Price of token A in terms of token B
    """
    sqrt_price_x64 = tick_to_sqrt_price_x64(tick)
    return sqrt_price_x64_to_price(sqrt_price_x64, decimals_a, decimals_b)


def price_to_tick(
    price: Decimal,
    decimals_a: int,
    decimals_b: int,
    tick_spacing: int = 1,
) -> int:
    """
    Convert price to tick (rounded to tick spacing)

    Args:
        price: Price of token A in terms of token B
        decimals_a: Token A decimals
        decimals_b: Token B decimals
        tick_spacing: Tick spacing for the pool

    Returns:
        Tick index (rounded to tick spacing)
    """
    # Adjust for decimals
    decimal_adjustment = Decimal(10) ** (decimals_a - decimals_b)
    adjusted_price = price / decimal_adjustment

    # tick = log_1.0001(price)
    # Since price = 1.0001^tick
    # Use Decimal.ln() to avoid float precision loss for extreme prices
    # Note: Decimal has no log() method, so we use float but with floor() for correctness
    log_base = math.log(1.0001)
    # Use math.floor() instead of int() - int() truncates toward 0 which is wrong
    # for negative ticks (prices < 1). floor() always rounds down.
    tick = math.floor(math.log(float(adjusted_price)) / log_base)

    # Round to tick spacing (floor division for consistent rounding)
    tick = (tick // tick_spacing) * tick_spacing

    # Clamp to valid range
    tick = max(MIN_TICK, min(MAX_TICK, tick))

    return tick


def one_tick_range(
    current_tick: int,
    tick_spacing: int,
) -> Tuple[int, int]:
    """
    Calculate single-tick range around current tick

    Args:
        current_tick: Current pool tick
        tick_spacing: Pool tick spacing

    Returns:
        (lower_tick, upper_tick) for single-tick position
    """
    # Round current tick down to nearest tick spacing
    lower_tick = (current_tick // tick_spacing) * tick_spacing
    upper_tick = lower_tick + tick_spacing

    return lower_tick, upper_tick


def get_token_amount_a_from_liquidity(
    liquidity: int,
    sqrt_price_x64_a: int,
    sqrt_price_x64_b: int,
) -> int:
    """
    Calculate token A amount from liquidity

    Formula: liquidity * (sqrtPriceB - sqrtPriceA) * Q64 / (sqrtPriceA * sqrtPriceB)

    Note: The Q64 factor is needed because sqrt prices are in X64 fixed-point format.
    Without it, the result would be off by a factor of 2^64.
    """
    if sqrt_price_x64_a > sqrt_price_x64_b:
        sqrt_price_x64_a, sqrt_price_x64_b = sqrt_price_x64_b, sqrt_price_x64_a

    if liquidity == 0 or sqrt_price_x64_a == sqrt_price_x64_b:
        return 0

    numerator = liquidity * (sqrt_price_x64_b - sqrt_price_x64_a) * Q64
    denominator = sqrt_price_x64_a * sqrt_price_x64_b

    return numerator // denominator


def get_token_amount_b_from_liquidity(
    liquidity: int,
    sqrt_price_x64_a: int,
    sqrt_price_x64_b: int,
) -> int:
    """
    Calculate token B amount from liquidity

    Formula: liquidity * (sqrtPriceB - sqrtPriceA) / 2^64
    """
    if sqrt_price_x64_a > sqrt_price_x64_b:
        sqrt_price_x64_a, sqrt_price_x64_b = sqrt_price_x64_b, sqrt_price_x64_a

    if liquidity == 0 or sqrt_price_x64_a == sqrt_price_x64_b:
        return 0

    numerator = liquidity * (sqrt_price_x64_b - sqrt_price_x64_a)
    return numerator // Q64


def get_amounts_from_liquidity(
    liquidity: int,
    sqrt_price_current_x64: int,
    sqrt_price_x64_lower: int,
    sqrt_price_x64_upper: int,
) -> Tuple[int, int]:
    """
    Calculate token amounts from liquidity and price range

    Args:
        liquidity: Liquidity amount
        sqrt_price_current_x64: Current sqrt price
        sqrt_price_x64_lower: Lower bound sqrt price
        sqrt_price_x64_upper: Upper bound sqrt price

    Returns:
        (amount_a, amount_b) raw token amounts
    """
    if sqrt_price_x64_lower > sqrt_price_x64_upper:
        sqrt_price_x64_lower, sqrt_price_x64_upper = sqrt_price_x64_upper, sqrt_price_x64_lower

    if sqrt_price_current_x64 <= sqrt_price_x64_lower:
        # Below range: only token A
        amount_a = get_token_amount_a_from_liquidity(
            liquidity, sqrt_price_x64_lower, sqrt_price_x64_upper
        )
        amount_b = 0
    elif sqrt_price_current_x64 < sqrt_price_x64_upper:
        # In range: both tokens
        amount_a = get_token_amount_a_from_liquidity(
            liquidity, sqrt_price_current_x64, sqrt_price_x64_upper
        )
        amount_b = get_token_amount_b_from_liquidity(
            liquidity, sqrt_price_x64_lower, sqrt_price_current_x64
        )
    else:
        # Above range: only token B
        amount_a = 0
        amount_b = get_token_amount_b_from_liquidity(
            liquidity, sqrt_price_x64_lower, sqrt_price_x64_upper
        )

    return amount_a, amount_b


def get_liquidity_from_amount_a(
    amount_a: int,
    sqrt_price_x64_lower: int,
    sqrt_price_x64_upper: int,
) -> int:
    """
    Calculate liquidity from token A amount

    Formula: amount * sqrtPriceA * sqrtPriceB / ((sqrtPriceB - sqrtPriceA) * Q64)

    Note: The Q64 divisor is needed because sqrt prices are in X64 fixed-point format.
    This is the inverse of get_token_amount_a_from_liquidity.
    """
    if sqrt_price_x64_lower > sqrt_price_x64_upper:
        sqrt_price_x64_lower, sqrt_price_x64_upper = sqrt_price_x64_upper, sqrt_price_x64_lower

    if amount_a == 0 or sqrt_price_x64_lower == sqrt_price_x64_upper:
        return 0

    numerator = amount_a * sqrt_price_x64_lower * sqrt_price_x64_upper
    denominator = (sqrt_price_x64_upper - sqrt_price_x64_lower) * Q64

    return numerator // denominator


def get_liquidity_from_amount_b(
    amount_b: int,
    sqrt_price_x64_lower: int,
    sqrt_price_x64_upper: int,
) -> int:
    """
    Calculate liquidity from token B amount

    Formula: amount * 2^64 / (sqrtPriceB - sqrtPriceA)
    """
    if sqrt_price_x64_lower > sqrt_price_x64_upper:
        sqrt_price_x64_lower, sqrt_price_x64_upper = sqrt_price_x64_upper, sqrt_price_x64_lower

    if amount_b == 0 or sqrt_price_x64_lower == sqrt_price_x64_upper:
        return 0

    numerator = amount_b * Q64
    denominator = sqrt_price_x64_upper - sqrt_price_x64_lower

    return numerator // denominator


def get_liquidity_from_amounts(
    amount_a: int,
    amount_b: int,
    sqrt_price_current_x64: int,
    sqrt_price_x64_lower: int,
    sqrt_price_x64_upper: int,
) -> int:
    """
    Calculate liquidity from both token amounts

    Returns the minimum liquidity that can be created from given amounts.

    Args:
        amount_a: Token A amount
        amount_b: Token B amount
        sqrt_price_current_x64: Current sqrt price
        sqrt_price_x64_lower: Lower bound sqrt price
        sqrt_price_x64_upper: Upper bound sqrt price

    Returns:
        Maximum liquidity achievable with given amounts
    """
    if sqrt_price_x64_lower > sqrt_price_x64_upper:
        sqrt_price_x64_lower, sqrt_price_x64_upper = sqrt_price_x64_upper, sqrt_price_x64_lower

    if sqrt_price_current_x64 <= sqrt_price_x64_lower:
        # Below range: only use token A
        return get_liquidity_from_amount_a(amount_a, sqrt_price_x64_lower, sqrt_price_x64_upper)
    elif sqrt_price_current_x64 < sqrt_price_x64_upper:
        # In range: use minimum of both
        liq_a = get_liquidity_from_amount_a(amount_a, sqrt_price_current_x64, sqrt_price_x64_upper)
        liq_b = get_liquidity_from_amount_b(amount_b, sqrt_price_x64_lower, sqrt_price_current_x64)
        return min(liq_a, liq_b)
    else:
        # Above range: only use token B
        return get_liquidity_from_amount_b(amount_b, sqrt_price_x64_lower, sqrt_price_x64_upper)


def get_tick_array_start_index(tick: int, tick_spacing: int) -> int:
    """
    Calculate tick array start index for a given tick

    Args:
        tick: Tick index
        tick_spacing: Pool tick spacing

    Returns:
        Start tick of the tick array containing this tick
    """
    ticks_in_array = TICK_ARRAY_SIZE * tick_spacing

    # Python floor division already rounds towards negative infinity,
    # which is correct for tick array indexing
    array_index = tick // ticks_in_array

    return array_index * ticks_in_array
