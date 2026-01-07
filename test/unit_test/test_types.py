"""
Test Types Module

Tests for dex_adapter.types package.
"""

import sys
from decimal import Decimal
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_token():
    """Test Token dataclass"""
    from dex_adapter.types import Token

    print("Testing Token...")

    # Create token
    sol = Token(
        mint="So11111111111111111111111111111111111111112",
        symbol="SOL",
        decimals=9,
        name="Solana",
    )

    assert sol.mint == "So11111111111111111111111111111111111111112"
    assert sol.symbol == "SOL"
    assert sol.decimals == 9
    assert sol.name == "Solana"

    # Token is frozen (immutable)
    try:
        sol.symbol = "XXX"
        assert False, "Should not be able to modify frozen dataclass"
    except Exception:
        pass  # Expected

    print("  Token: PASSED")


def test_pool():
    """Test Pool dataclass"""
    from dex_adapter.types import Pool, Token

    print("Testing Pool...")

    token0 = Token("mint0", "SOL", 9, "Solana")
    token1 = Token("mint1", "USDC", 6, "USD Coin")

    pool = Pool(
        address="pool_address",
        dex="raydium",
        symbol="SOL/USDC",
        token0=token0,
        token1=token1,
        price=Decimal("100.5"),
        tvl_usd=Decimal("1000000"),
        fee_rate=Decimal("0.003"),
        tick_spacing=1,
        current_tick=1000,
    )

    assert pool.address == "pool_address"
    assert pool.dex == "raydium"
    assert pool.token0.symbol == "SOL"
    assert pool.price == Decimal("100.5")
    assert pool.tick_spacing == 1

    print("  Pool: PASSED")


def test_position():
    """Test Position dataclass"""
    from dex_adapter.types import Position, Pool, Token
    from datetime import datetime

    print("Testing Position...")

    token0 = Token("mint0", "SOL", 9)
    token1 = Token("mint1", "USDC", 6)

    pool = Pool(
        address="pool",
        dex="raydium",
        symbol="SOL/USDC",
        token0=token0,
        token1=token1,
        price=Decimal("100"),
        tvl_usd=Decimal("1000000"),
        fee_rate=Decimal("0.003"),
    )

    position = Position(
        id="position_123",
        pool=pool,
        owner="owner_pubkey",
        price_lower=Decimal("95"),
        price_upper=Decimal("105"),
        amount0=Decimal("1.5"),
        amount1=Decimal("50"),
        liquidity=1000000,
        value_usd=Decimal("200"),
        unclaimed_fees={"SOL": Decimal("0.01"), "USDC": Decimal("1.5")},
        unclaimed_rewards={},
        is_in_range=True,
        created_at=datetime.now(),
    )

    assert position.id == "position_123"
    assert position.is_in_range == True
    assert position.price_lower == Decimal("95")
    assert position.price_upper == Decimal("105")
    assert "SOL" in position.unclaimed_fees

    print("  Position: PASSED")


def test_price_range():
    """Test PriceRange dataclass"""
    from dex_adapter.types import PriceRange, RangeMode

    print("Testing PriceRange...")

    # Percent mode
    pr1 = PriceRange.percent(0.02)
    assert pr1.mode == RangeMode.PERCENT
    assert pr1.lower == Decimal("-0.02")
    assert pr1.upper == Decimal("0.02")

    # One tick mode
    pr2 = PriceRange.one_tick()
    assert pr2.mode == RangeMode.ONE_TICK

    # BPS mode (100 bps = 1% = 0.01)
    pr3 = PriceRange.bps(100)
    assert pr3.mode == RangeMode.BPS
    assert pr3.lower == Decimal("-0.01")  # 100 bps = 0.01
    assert pr3.upper == Decimal("0.01")

    # Absolute mode
    pr4 = PriceRange.absolute(95.0, 105.0)
    assert pr4.mode == RangeMode.ABSOLUTE
    assert pr4.lower == Decimal("95")
    assert pr4.upper == Decimal("105")

    print("  PriceRange: PASSED")


def test_tx_result():
    """Test TxResult dataclass"""
    from dex_adapter.types import TxResult, TxStatus

    print("Testing TxResult...")

    # Success
    result1 = TxResult.success("signature123")
    assert result1.status == TxStatus.SUCCESS
    assert result1.signature == "signature123"
    assert result1.is_success == True

    # Failure
    result2 = TxResult.failed("Transaction failed")
    assert result2.status == TxStatus.FAILED
    assert result2.error == "Transaction failed"
    assert result2.is_success == False

    # Timeout
    result3 = TxResult.timeout()
    assert result3.status == TxStatus.TIMEOUT
    assert result3.is_success == False

    print("  TxResult: PASSED")


def test_quote_result():
    """Test QuoteResult dataclass"""
    from dex_adapter.types import QuoteResult
    from decimal import Decimal

    print("Testing QuoteResult...")

    quote = QuoteResult(
        from_token="SOL",
        to_token="USDC",
        from_amount=1000000000,  # 1 SOL in lamports
        to_amount=100500000,     # 100.5 USDC
        price_impact=Decimal("0.001"),  # 0.1%
        route=["SOL", "USDC"],
    )

    assert quote.from_token == "SOL"
    assert quote.to_token == "USDC"
    assert quote.price_impact_percent == 0.1  # 0.001 * 100 = 0.1%

    print("  QuoteResult: PASSED")


def main():
    """Run all type tests"""
    print("=" * 60)
    print("DEX Adapter Types Tests")
    print("=" * 60)

    tests = [
        test_token,
        test_pool,
        test_position,
        test_price_range,
        test_tx_result,
        test_quote_result,
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
