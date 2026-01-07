"""
Meteora DLMM Math Utilities

Provides bin/price conversion and liquidity calculations.
"""

import math
from decimal import Decimal
from typing import Tuple

from .constants import MIN_BIN_ID, MAX_BIN_ID, MAX_BIN_PER_ARRAY


def bin_id_to_price(
    bin_id: int,
    bin_step: int,
    decimals_x: int,
    decimals_y: int,
) -> Decimal:
    """
    Convert bin ID to price

    Formula: price = (1 + bin_step/10000)^bin_id * 10^(decimals_x - decimals_y)

    Args:
        bin_id: Bin ID
        bin_step: Bin step in basis points
        decimals_x: Token X decimals
        decimals_y: Token Y decimals

    Returns:
        Price of token X in terms of token Y
    """
    # Base = 1 + bin_step / 10000
    base = 1.0 + bin_step / 10000.0

    # Price = base^bin_id (use float to avoid Decimal overflow for large bin_ids)
    try:
        price_float = math.pow(base, bin_id)
    except OverflowError:
        # Handle extremely large/small bin_ids
        if bin_id > 0:
            price_float = float('inf')
        else:
            price_float = 0.0

    # Adjust for decimals
    decimal_adjustment = 10.0 ** (decimals_x - decimals_y)
    adjusted_price = price_float * decimal_adjustment

    # Convert to Decimal, handling infinity
    if math.isinf(adjusted_price) or math.isnan(adjusted_price):
        return Decimal('999999999')  # Return a large number for display

    return Decimal(str(adjusted_price))


def price_to_bin_id(
    price: Decimal,
    bin_step: int,
    decimals_x: int,
    decimals_y: int,
) -> int:
    """
    Convert price to bin ID

    Formula: bin_id = log(price / decimal_adjustment) / log(1 + bin_step/10000)

    Args:
        price: Price of token X in terms of token Y
        bin_step: Bin step in basis points
        decimals_x: Token X decimals
        decimals_y: Token Y decimals

    Returns:
        Bin ID (rounded)
    """
    # Adjust for decimals
    decimal_adjustment = Decimal(10) ** (decimals_x - decimals_y)
    adjusted_price = price / decimal_adjustment

    # Base = 1 + bin_step / 10000
    base = float(Decimal(1) + Decimal(bin_step) / Decimal(10000))

    # bin_id = log(adjusted_price) / log(base)
    if float(adjusted_price) <= 0:
        return MIN_BIN_ID

    bin_id = int(round(math.log(float(adjusted_price)) / math.log(base)))

    # Clamp to valid range
    return max(MIN_BIN_ID, min(MAX_BIN_ID, bin_id))


def get_active_bin(active_id: int) -> Tuple[int, int]:
    """
    Get the single active bin as a range

    Args:
        active_id: Active bin ID from pool state

    Returns:
        (lower_bin, upper_bin) - same value for single bin
    """
    return active_id, active_id


def one_bin_range(active_id: int) -> Tuple[int, int]:
    """
    Get single-bin range (equivalent to one_tick for Raydium)

    Args:
        active_id: Active bin ID

    Returns:
        (lower_bin, upper_bin) for single-bin position
    """
    return active_id, active_id


def get_bin_array_index(bin_id: int) -> int:
    """
    Calculate bin array index for a given bin ID

    Bin arrays contain 70 consecutive bins:
    - Array 0: bins [0, 69]
    - Array 1: bins [70, 139]
    - Array -1: bins [-70, -1]
    - Array -2: bins [-140, -71]

    Python's floor division naturally handles negative numbers correctly.

    Args:
        bin_id: Bin ID

    Returns:
        Bin array index
    """
    # Python floor division handles both positive and negative correctly:
    # - Positive: 69 // 70 = 0, 70 // 70 = 1
    # - Negative: -1 // 70 = -1, -70 // 70 = -1, -71 // 70 = -2
    return bin_id // MAX_BIN_PER_ARRAY


def get_bin_array_lower_upper_bin_id(bin_array_index: int) -> Tuple[int, int]:
    """
    Get lower and upper bin IDs for a bin array

    Args:
        bin_array_index: Bin array index

    Returns:
        (lower_bin_id, upper_bin_id)
    """
    lower_bin_id = bin_array_index * MAX_BIN_PER_ARRAY
    upper_bin_id = lower_bin_id + MAX_BIN_PER_ARRAY - 1
    return lower_bin_id, upper_bin_id


def calculate_distribution(
    active_id: int,
    lower_bin_id: int,
    upper_bin_id: int,
    amount_x: int,
    amount_y: int,
) -> list[dict]:
    """
    Calculate bin distribution for adding liquidity

    For SpotBalanced strategy, distributes evenly across bins.

    Args:
        active_id: Active bin ID
        lower_bin_id: Lower bin ID
        upper_bin_id: Upper bin ID
        amount_x: Token X amount
        amount_y: Token Y amount

    Returns:
        List of bin distributions
    """
    distributions = []
    num_bins = upper_bin_id - lower_bin_id + 1

    if num_bins <= 0:
        return distributions

    # Simple uniform distribution
    amount_x_per_bin = amount_x // num_bins
    amount_y_per_bin = amount_y // num_bins

    for bin_id in range(lower_bin_id, upper_bin_id + 1):
        if bin_id < active_id:
            # Below active: only token Y
            distributions.append({
                "bin_id": bin_id,
                "amount_x": 0,
                "amount_y": amount_y_per_bin,
            })
        elif bin_id > active_id:
            # Above active: only token X
            distributions.append({
                "bin_id": bin_id,
                "amount_x": amount_x_per_bin,
                "amount_y": 0,
            })
        else:
            # Active bin: both tokens
            distributions.append({
                "bin_id": bin_id,
                "amount_x": amount_x_per_bin,
                "amount_y": amount_y_per_bin,
            })

    return distributions


def get_amounts_from_bin_distribution(
    distributions: list[dict],
    bin_step: int,
    decimals_x: int,
    decimals_y: int,
) -> Tuple[Decimal, Decimal]:
    """
    Calculate total amounts from bin distribution

    Args:
        distributions: List of bin distributions
        bin_step: Bin step
        decimals_x: Token X decimals
        decimals_y: Token Y decimals

    Returns:
        (total_amount_x, total_amount_y) in UI units
    """
    total_x = sum(d.get("amount_x", 0) for d in distributions)
    total_y = sum(d.get("amount_y", 0) for d in distributions)

    return (
        Decimal(total_x) / Decimal(10 ** decimals_x),
        Decimal(total_y) / Decimal(10 ** decimals_y),
    )
