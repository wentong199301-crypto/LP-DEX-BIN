"""
Market Module Integration Tests

Tests market/pool operations with live Solana RPC.

WARNING: These tests use REAL RPC connections!
"""

import sys
from decimal import Decimal
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from conftest import create_client, skip_if_no_config


# Known pool addresses for testing
RAYDIUM_SOL_USDC_POOL = "2QdhepnKRTLjjSqPL1PtKNwqrUkoLee5Gqs8bvZhRdMv"
METEORA_SOL_USDC_POOL = "HTvjzsfX3yU6BUodCjZ5vZkUrAxMDTrBs3CJaq43ashR"


def test_resolve_token_mint(client):
    """Test resolving token symbol to mint address"""
    print("Testing resolve_token_mint...")

    # Test known symbols
    sol_mint = client.market.resolve_token_mint("SOL")
    assert sol_mint == "So11111111111111111111111111111111111111112", f"Wrong SOL mint: {sol_mint}"

    usdc_mint = client.market.resolve_token_mint("USDC")
    assert usdc_mint == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", f"Wrong USDC mint: {usdc_mint}"

    # Test case insensitivity
    msol_mint = client.market.resolve_token_mint("mSOL")
    assert msol_mint == "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So", f"Wrong mSOL mint: {msol_mint}"

    print(f"  SOL -> {sol_mint[:16]}...")
    print(f"  USDC -> {usdc_mint[:16]}...")
    print(f"  mSOL -> {msol_mint[:16]}...")
    print("  resolve_token_mint: PASSED")


def test_pool_by_address_raydium(client):
    """Test getting Raydium pool by address"""
    print("Testing pool by address (Raydium)...")

    pool = client.market.pool(RAYDIUM_SOL_USDC_POOL, dex="raydium")

    assert pool is not None, "Pool should not be None"
    assert pool.address == RAYDIUM_SOL_USDC_POOL, f"Wrong pool address"
    assert pool.dex == "raydium", f"Wrong dex: {pool.dex}"
    assert pool.price > 0, f"Price should be > 0, got {pool.price}"

    print(f"  Pool: {pool.address[:16]}...")
    print(f"  DEX: {pool.dex}")
    print(f"  Token0: {pool.token0.symbol or pool.token0.mint[:16]}")
    print(f"  Token1: {pool.token1.symbol or pool.token1.mint[:16]}")
    print(f"  Price: {pool.price}")
    print(f"  TVL USD: {pool.tvl_usd}")
    print("  pool by address (Raydium): PASSED")


def test_pool_by_symbol_raydium(client):
    """Test getting Raydium pool by symbol"""
    print("Testing pool by symbol (Raydium)...")

    pool = client.market.pool_by_symbol("SOL/USDC", dex="raydium")

    assert pool is not None, "Pool should not be None"
    assert pool.dex == "raydium", f"Wrong dex: {pool.dex}"
    assert pool.price > 0, f"Price should be > 0"

    print(f"  SOL/USDC pool: {pool.address[:16]}...")
    print(f"  Price: {pool.price}")
    print("  pool by symbol (Raydium): PASSED")


def test_pool_by_symbol_case_insensitive(client):
    """Test pool_by_symbol is case insensitive"""
    print("Testing pool by symbol (case insensitive)...")

    pool1 = client.market.pool_by_symbol("sol/usdc", dex="raydium")
    pool2 = client.market.pool_by_symbol("SOL/USDC", dex="raydium")

    assert pool1 is not None, "Pool1 should not be None"
    assert pool2 is not None, "Pool2 should not be None"
    assert pool1.address == pool2.address, "Pools should match"

    print(f"  'sol/usdc' and 'SOL/USDC' resolve to same pool")
    print("  pool by symbol (case insensitive): PASSED")


def test_pool_by_address_meteora(client):
    """Test getting Meteora pool by address"""
    print("Testing pool by address (Meteora)...")

    pool = client.market.pool(METEORA_SOL_USDC_POOL, dex="meteora")

    assert pool is not None, "Pool should not be None"
    assert pool.address == METEORA_SOL_USDC_POOL, f"Wrong pool address"
    assert pool.dex == "meteora", f"Wrong dex: {pool.dex}"

    print(f"  Pool: {pool.address[:16]}...")
    print(f"  DEX: {pool.dex}")
    print(f"  Price: {pool.price}")
    print("  pool by address (Meteora): PASSED")


def test_price(client):
    """Test getting price for a trading pair"""
    print("Testing price...")

    price = client.market.price("SOL/USDC", dex="raydium")

    assert isinstance(price, Decimal), f"Expected Decimal, got {type(price)}"
    assert price > 0, f"Price should be > 0, got {price}"

    print(f"  SOL/USDC price: {price}")
    print("  price: PASSED")


def test_price_by_pool_address(client):
    """Test getting price by pool address"""
    print("Testing price by pool address...")

    price = client.market.price(RAYDIUM_SOL_USDC_POOL)

    assert isinstance(price, Decimal), f"Expected Decimal, got {type(price)}"
    assert price > 0, f"Price should be > 0"

    print(f"  Price via pool address: {price}")
    print("  price by pool address: PASSED")


def test_price_usd(client):
    """Test getting USD price for a token"""
    print("Testing price_usd...")

    price = client.market.price_usd("SOL", dex="raydium")

    if price is not None:
        assert isinstance(price, Decimal), f"Expected Decimal, got {type(price)}"
        assert price > 0, f"Price should be > 0"
        print(f"  SOL USD price: ${price}")
    else:
        print(f"  SOL USD price: None (no stablecoin pool found)")

    print("  price_usd: PASSED")


def test_pool_cache(client):
    """Test pool caching behavior"""
    print("Testing pool cache...")

    # First call should fetch from chain
    pool1 = client.market.pool(RAYDIUM_SOL_USDC_POOL, dex="raydium")

    # Second call should use cache
    pool2 = client.market.pool(RAYDIUM_SOL_USDC_POOL, dex="raydium")

    assert pool1.address == pool2.address, "Cached pool should match"

    # Refresh should fetch new data
    pool3 = client.market.pool(RAYDIUM_SOL_USDC_POOL, dex="raydium", refresh=True)
    assert pool3 is not None, "Refreshed pool should not be None"

    print(f"  Pool caching works correctly")
    print("  pool cache: PASSED")


def test_refresh_pool(client):
    """Test refresh_pool method"""
    print("Testing refresh_pool...")

    pool = client.market.refresh_pool(RAYDIUM_SOL_USDC_POOL)

    assert pool is not None, "Pool should not be None"
    assert pool.price > 0, "Price should be > 0"

    print(f"  Refreshed pool price: {pool.price}")
    print("  refresh_pool: PASSED")


def test_clear_cache(client):
    """Test clear_cache method"""
    print("Testing clear_cache...")

    # Populate cache
    client.market.pool(RAYDIUM_SOL_USDC_POOL, dex="raydium")

    # Clear cache
    client.market.clear_cache()

    print(f"  Cache cleared successfully")
    print("  clear_cache: PASSED")


def main():
    """Run all market module tests"""
    print("=" * 60)
    print("Market Module Integration Tests")
    print("=" * 60)

    # Check if configuration is available
    skip_msg = skip_if_no_config()
    if skip_msg:
        print(f"\nSKIPPED: {skip_msg}")
        return True  # Not a failure, just skipped

    # Create real client with live RPC and wallet
    print("\nCreating DexClient with real RPC and wallet...")
    client = create_client()
    print(f"  Wallet: {client.wallet.address}")
    print()

    tests = [
        test_resolve_token_mint,
        test_pool_by_address_raydium,
        test_pool_by_symbol_raydium,
        test_pool_by_symbol_case_insensitive,
        test_pool_by_address_meteora,
        test_price,
        test_price_by_pool_address,
        test_price_usd,
        test_pool_cache,
        test_refresh_pool,
        test_clear_cache,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test(client)
            passed += 1
        except Exception as e:
            print(f"  FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
