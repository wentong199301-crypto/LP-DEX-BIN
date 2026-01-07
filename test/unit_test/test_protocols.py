"""
Test Protocols Module

Tests for dex_adapter.protocols package.
"""

import sys
from decimal import Decimal
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_protocol_registry():
    """Test ProtocolRegistry"""
    from dex_adapter.protocols import ProtocolRegistry

    print("Testing ProtocolRegistry...")

    # List available protocols
    protocols = ProtocolRegistry.list()
    assert "raydium" in protocols
    assert "meteora" in protocols

    print("  ProtocolRegistry: PASSED")


def test_raydium_adapter_registration():
    """Test RaydiumAdapter is registered"""
    from dex_adapter.protocols import ProtocolRegistry
    from dex_adapter.protocols.raydium import RaydiumAdapter

    print("Testing Raydium Registration...")

    # Should be able to get adapter
    protocols = ProtocolRegistry.list()
    assert "raydium" in protocols

    print("  Raydium Registration: PASSED")


def test_meteora_adapter_registration():
    """Test MeteoraAdapter is registered"""
    from dex_adapter.protocols import ProtocolRegistry
    from dex_adapter.protocols.meteora import MeteoraAdapter

    print("Testing Meteora Registration...")

    protocols = ProtocolRegistry.list()
    assert "meteora" in protocols

    print("  Meteora Registration: PASSED")


def test_raydium_math():
    """Test Raydium math utilities"""
    from dex_adapter.protocols.raydium.math import (
        tick_to_sqrt_price_x64,
        sqrt_price_x64_to_price,
        tick_to_price,
        price_to_tick,
        one_tick_range,
    )

    print("Testing Raydium Math...")

    # Tick to sqrt price
    tick = 1000
    sqrt_price = tick_to_sqrt_price_x64(tick)
    assert sqrt_price > 0

    # Sqrt price to human-readable price
    price = sqrt_price_x64_to_price(sqrt_price, 9, 6)  # SOL/USDC
    assert price > 0

    # Tick to price
    price2 = tick_to_price(tick, 9, 6)  # SOL/USDC
    assert price2 > 0

    # Price to tick - round trip test
    recovered_tick = price_to_tick(price2, 9, 6)
    assert abs(recovered_tick - tick) <= 1  # Allow small rounding

    # One tick range
    lower, upper = one_tick_range(tick, tick_spacing=1)
    assert lower == tick
    assert upper == tick + 1

    print("  Raydium Math: PASSED")


def test_meteora_math():
    """Test Meteora math utilities"""
    from dex_adapter.protocols.meteora.math import (
        bin_id_to_price,
        price_to_bin_id,
        one_bin_range,
    )

    print("Testing Meteora Math...")

    # Bin to price and back
    bin_id = 1000
    bin_step = 10
    decimals_x = 9  # SOL
    decimals_y = 6  # USDC

    price = bin_id_to_price(bin_id, bin_step, decimals_x, decimals_y)
    assert price > 0

    recovered_bin = price_to_bin_id(price, bin_step, decimals_x, decimals_y)
    assert abs(recovered_bin - bin_id) <= 1

    # One bin range
    lower, upper = one_bin_range(bin_id)
    assert lower == bin_id
    assert upper == bin_id

    print("  Meteora Math: PASSED")


def test_jupiter_adapter_init():
    """Test JupiterAdapter initialization"""
    from dex_adapter.protocols.jupiter import JupiterAdapter

    print("Testing Jupiter Adapter...")

    # Check adapter has required methods
    assert hasattr(JupiterAdapter, "quote")
    assert hasattr(JupiterAdapter, "swap")
    assert hasattr(JupiterAdapter, "execute_quote")

    print("  Jupiter Adapter: PASSED")


def test_protocol_adapter_interface():
    """Test ProtocolAdapter ABC interface"""
    from dex_adapter.protocols.base import ProtocolAdapter

    print("Testing ProtocolAdapter Interface...")

    # Check required abstract methods
    import inspect
    abstract_methods = [
        name for name, method in inspect.getmembers(ProtocolAdapter)
        if getattr(method, '__isabstractmethod__', False)
    ]

    # These are the actual abstract methods in the base class
    expected_abstract_methods = [
        "get_pool",
        "get_position",
        "get_positions",
        "build_open_position",
        "build_close_position",
        "build_add_liquidity",
        "build_remove_liquidity",
        "build_claim_fees",
        "calculate_amounts_for_range",
        "price_range_to_ticks",
        "ticks_to_prices",
    ]

    for method in expected_abstract_methods:
        assert method in abstract_methods, f"Missing abstract method: {method}"

    # These methods have default implementations (not abstract)
    default_methods = [
        "get_pools_by_token",  # Returns [] by default
        "is_in_range",
        "build_claim_rewards",
        "get_token_info",
        "estimate_fees",
    ]

    for method in default_methods:
        assert hasattr(ProtocolAdapter, method), f"Missing method: {method}"

    print("  ProtocolAdapter Interface: PASSED")


def main():
    """Run all protocol tests"""
    print("=" * 60)
    print("DEX Adapter Protocols Tests")
    print("=" * 60)

    tests = [
        test_protocol_registry,
        test_raydium_adapter_registration,
        test_meteora_adapter_registration,
        test_raydium_math,
        test_meteora_math,
        test_jupiter_adapter_init,
        test_protocol_adapter_interface,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  FAILED: {e}")
            failed += 1

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
