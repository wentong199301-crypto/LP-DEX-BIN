"""
Test Raydium Math Module

Tests for tick/price conversions and liquidity calculations.
"""

import sys
from decimal import Decimal
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def test_tick_to_sqrt_price_x64():
    """Test tick to sqrt price conversion"""
    from dex_adapter_universal.protocols.raydium.math import tick_to_sqrt_price_x64
    from dex_adapter_universal.protocols.raydium.constants import MIN_TICK, MAX_TICK

    print("Testing tick_to_sqrt_price_x64...")

    # Tick 0 should give sqrt(1) * 2^64
    sqrt_price_0 = tick_to_sqrt_price_x64(0)
    expected_0 = 2 ** 64  # sqrt(1) * 2^64
    assert sqrt_price_0 == expected_0, f"Tick 0: expected {expected_0}, got {sqrt_price_0}"

    # Positive ticks should give higher prices
    sqrt_price_100 = tick_to_sqrt_price_x64(100)
    assert sqrt_price_100 > sqrt_price_0, "Positive tick should give higher sqrt price"

    # Negative ticks should give lower prices
    sqrt_price_neg100 = tick_to_sqrt_price_x64(-100)
    assert sqrt_price_neg100 < sqrt_price_0, "Negative tick should give lower sqrt price"

    # Edge cases
    sqrt_price_min = tick_to_sqrt_price_x64(MIN_TICK)
    sqrt_price_max = tick_to_sqrt_price_x64(MAX_TICK)
    assert sqrt_price_min > 0, "Min tick sqrt price should be positive"
    assert sqrt_price_max > sqrt_price_min, "Max tick sqrt price should be greater than min"

    # Invalid ticks should raise ConfigurationError
    from dex_adapter_universal.errors import ConfigurationError
    try:
        tick_to_sqrt_price_x64(MIN_TICK - 1)
        assert False, "Should raise for tick below MIN_TICK"
    except ConfigurationError:
        pass

    try:
        tick_to_sqrt_price_x64(MAX_TICK + 1)
        assert False, "Should raise for tick above MAX_TICK"
    except ConfigurationError:
        pass

    print("  tick_to_sqrt_price_x64: PASSED")


def test_sqrt_price_x64_to_price():
    """Test sqrt price to human-readable price conversion"""
    from dex_adapter_universal.protocols.raydium.math import sqrt_price_x64_to_price

    print("Testing sqrt_price_x64_to_price...")

    # Q64 is 2^64, which represents sqrt(1) = 1
    Q64 = 2 ** 64

    # sqrt(1) with same decimals should give price 1
    price = sqrt_price_x64_to_price(Q64, 9, 9)
    assert abs(float(price) - 1.0) < 0.0001, f"Price should be ~1, got {price}"

    # With different decimals, price should adjust
    # token0=9 decimals, token1=6 decimals
    # price should be multiplied by 10^(9-6) = 1000
    price_adjusted = sqrt_price_x64_to_price(Q64, 9, 6)
    assert abs(float(price_adjusted) - 1000.0) < 1, f"Adjusted price should be ~1000, got {price_adjusted}"

    print("  sqrt_price_x64_to_price: PASSED")


def test_tick_to_price():
    """Test tick to price conversion"""
    from dex_adapter_universal.protocols.raydium.math import tick_to_price

    print("Testing tick_to_price...")

    # Tick 0 should give price 1 (with same decimals)
    price_0 = tick_to_price(0, 9, 9)
    assert abs(float(price_0) - 1.0) < 0.0001, f"Tick 0 price should be ~1, got {price_0}"

    # Tick 10000 (1.0001^10000) ≈ 2.718
    price_10000 = tick_to_price(10000, 9, 9)
    assert 2.5 < float(price_10000) < 3.0, f"Tick 10000 price should be ~2.718, got {price_10000}"

    # Negative tick should give price < 1
    price_neg10000 = tick_to_price(-10000, 9, 9)
    assert 0.3 < float(price_neg10000) < 0.4, f"Tick -10000 price should be ~0.368, got {price_neg10000}"

    print("  tick_to_price: PASSED")


def test_price_to_tick():
    """Test price to tick conversion"""
    from dex_adapter_universal.protocols.raydium.math import price_to_tick, tick_to_price

    print("Testing price_to_tick...")

    # Price 1 should give tick 0
    tick = price_to_tick(Decimal("1.0"), 9, 9)
    assert tick == 0, f"Price 1 should give tick 0, got {tick}"

    # Round-trip test: tick -> price -> tick should be consistent
    original_tick = 5000
    price = tick_to_price(original_tick, 9, 9)
    recovered_tick = price_to_tick(price, 9, 9, tick_spacing=1)
    assert abs(recovered_tick - original_tick) <= 1, f"Round-trip failed: {original_tick} -> {price} -> {recovered_tick}"

    # Test with tick spacing
    price = tick_to_price(105, 9, 9)  # Tick 105
    tick_with_spacing = price_to_tick(price, 9, 9, tick_spacing=10)
    assert tick_with_spacing % 10 == 0, f"Tick should be aligned to spacing 10, got {tick_with_spacing}"

    print("  price_to_tick: PASSED")


def test_one_tick_range():
    """Test one tick range calculation"""
    from dex_adapter_universal.protocols.raydium.math import one_tick_range

    print("Testing one_tick_range...")

    # Current tick 100, spacing 1
    lower, upper = one_tick_range(100, 1)
    assert lower == 100, f"Lower should be 100, got {lower}"
    assert upper == 101, f"Upper should be 101, got {upper}"

    # Current tick 105, spacing 10
    lower, upper = one_tick_range(105, 10)
    assert lower == 100, f"Lower should be 100, got {lower}"
    assert upper == 110, f"Upper should be 110, got {upper}"

    # Negative tick
    lower, upper = one_tick_range(-105, 10)
    assert lower == -110, f"Lower should be -110, got {lower}"
    assert upper == -100, f"Upper should be -100, got {upper}"

    print("  one_tick_range: PASSED")


def test_get_token_amount_from_liquidity():
    """Test token amount calculations from liquidity"""
    from dex_adapter_universal.protocols.raydium.math import (
        get_token_amount_a_from_liquidity,
        get_token_amount_b_from_liquidity,
        get_amounts_from_liquidity,
        tick_to_sqrt_price_x64,
    )

    print("Testing get_token_amount_from_liquidity...")

    # Use large liquidity and wider tick range for meaningful amounts
    liquidity = 10_000_000_000_000_000  # Very large liquidity

    # Use wider tick range (tick 0 to 10000) for more meaningful price difference
    sqrt_price_lower = tick_to_sqrt_price_x64(0)
    sqrt_price_upper = tick_to_sqrt_price_x64(10000)
    sqrt_price_current = tick_to_sqrt_price_x64(5000)

    # In-range: both tokens
    amount_a, amount_b = get_amounts_from_liquidity(
        liquidity,
        sqrt_price_current,
        sqrt_price_lower,
        sqrt_price_upper,
    )
    assert amount_a >= 0, f"Amount A should be non-negative, got {amount_a}"
    assert amount_b >= 0, f"Amount B should be non-negative, got {amount_b}"
    assert amount_a > 0 or amount_b > 0, "At least one amount should be positive in range"

    # Below range: only token A
    sqrt_price_below = tick_to_sqrt_price_x64(-5000)
    amount_a_below, amount_b_below = get_amounts_from_liquidity(
        liquidity,
        sqrt_price_below,
        sqrt_price_lower,
        sqrt_price_upper,
    )
    assert amount_a_below >= 0, "Should have non-negative token A below range"
    assert amount_b_below == 0, "Should have no token B below range"

    # Above range: only token B
    sqrt_price_above = tick_to_sqrt_price_x64(15000)
    amount_a_above, amount_b_above = get_amounts_from_liquidity(
        liquidity,
        sqrt_price_above,
        sqrt_price_lower,
        sqrt_price_upper,
    )
    assert amount_a_above == 0, "Should have no token A above range"
    assert amount_b_above >= 0, "Should have non-negative token B above range"

    print("  get_token_amount_from_liquidity: PASSED")


def test_get_liquidity_from_amounts():
    """Test liquidity calculation from amounts"""
    from dex_adapter_universal.protocols.raydium.math import (
        get_liquidity_from_amounts,
        get_amounts_from_liquidity,
        tick_to_sqrt_price_x64,
    )

    print("Testing get_liquidity_from_amounts...")

    sqrt_price_lower = tick_to_sqrt_price_x64(0)
    sqrt_price_upper = tick_to_sqrt_price_x64(100)
    sqrt_price_current = tick_to_sqrt_price_x64(50)

    # Calculate liquidity from amounts
    amount_a = 1_000_000_000  # 1 token (9 decimals)
    amount_b = 1_000_000     # 1 token (6 decimals)

    liquidity = get_liquidity_from_amounts(
        amount_a,
        amount_b,
        sqrt_price_current,
        sqrt_price_lower,
        sqrt_price_upper,
    )
    assert liquidity > 0, f"Liquidity should be positive, got {liquidity}"

    # Verify round-trip (with some tolerance for rounding)
    recovered_a, recovered_b = get_amounts_from_liquidity(
        liquidity,
        sqrt_price_current,
        sqrt_price_lower,
        sqrt_price_upper,
    )

    # The recovered amounts should be close to min of the inputs (since we take min liquidity)
    assert recovered_a <= amount_a, "Recovered amount A should not exceed input"
    assert recovered_b <= amount_b, "Recovered amount B should not exceed input"

    print("  get_liquidity_from_amounts: PASSED")


def test_get_tick_array_start_index():
    """Test tick array start index calculation"""
    from dex_adapter_universal.protocols.raydium.math import get_tick_array_start_index
    from dex_adapter_universal.protocols.raydium.constants import TICK_ARRAY_SIZE

    print("Testing get_tick_array_start_index...")

    tick_spacing = 10
    ticks_per_array = TICK_ARRAY_SIZE * tick_spacing  # 60 * 10 = 600

    # Tick 0 -> array starting at 0
    start = get_tick_array_start_index(0, tick_spacing)
    assert start == 0, f"Tick 0 should start array at 0, got {start}"

    # Tick 300 (middle of first array) -> array starting at 0
    start = get_tick_array_start_index(300, tick_spacing)
    assert start == 0, f"Tick 300 should start array at 0, got {start}"

    # Tick 600 -> next array
    start = get_tick_array_start_index(600, tick_spacing)
    assert start == 600, f"Tick 600 should start array at 600, got {start}"

    # Negative tick
    start = get_tick_array_start_index(-100, tick_spacing)
    assert start == -600, f"Tick -100 should start array at -600, got {start}"

    print("  get_tick_array_start_index: PASSED")


def main():
    """Run all Raydium math tests"""
    print("=" * 60)
    print("Raydium Math Tests")
    print("=" * 60)

    tests = [
        test_tick_to_sqrt_price_x64,
        test_sqrt_price_x64_to_price,
        test_tick_to_price,
        test_price_to_tick,
        test_one_tick_range,
        test_get_token_amount_from_liquidity,
        test_get_liquidity_from_amounts,
        test_get_tick_array_start_index,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
