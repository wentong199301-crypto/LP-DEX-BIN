"""
Market Module Integration Tests

Tests market/pool operations with live RPC connections.
Supports multi-chain: Solana (Raydium/Meteora), Ethereum (Uniswap), BSC (PancakeSwap).

WARNING: These tests use REAL RPC connections!
"""

import sys
import os
from decimal import Decimal
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from conftest import create_client, skip_if_no_config
from dex_adapter_universal.types.pool import (
    RAYDIUM_POOLS,
    METEORA_POOLS,
    UNISWAP_POOLS,
    PANCAKESWAP_POOLS,
)
from dex_adapter_universal.types.solana_tokens import SOLANA_TOKEN_MINTS

# Get pool addresses from registry
RAYDIUM_SOL_USDC_POOL = RAYDIUM_POOLS.get("SOL/USDC")
RAYDIUM_SOL_USD1_POOL = RAYDIUM_POOLS.get("SOL/USD1")
METEORA_SOL_USDC_POOL = METEORA_POOLS.get("SOL/USDC")
UNISWAP_ETH_USDT_POOL = UNISWAP_POOLS.get("ETH/USDT")
PANCAKESWAP_BNB_USDT_POOL = PANCAKESWAP_POOLS.get("WBNB/USDT")


def has_evm_config():
    """Check if EVM config is available"""
    return os.getenv("ETH_RPC_URL") and os.getenv("BSC_RPC_URL")


def test_resolve_token_mint(client):
    """Test resolving token symbol to mint address"""
    print("Testing resolve_token_mint...")

    # Test known symbols
    sol_mint = client.market.resolve_token_mint("SOL")
    assert sol_mint == SOLANA_TOKEN_MINTS["SOL"], f"Wrong SOL mint: {sol_mint}"

    usdc_mint = client.market.resolve_token_mint("USDC")
    assert usdc_mint == SOLANA_TOKEN_MINTS["USDC"], f"Wrong USDC mint: {usdc_mint}"

    usd1_mint = client.market.resolve_token_mint("USD1")
    assert usd1_mint == SOLANA_TOKEN_MINTS["USD1"], f"Wrong USD1 mint: {usd1_mint}"

    # Test case insensitivity
    msol_mint = client.market.resolve_token_mint("mSOL")
    assert msol_mint == SOLANA_TOKEN_MINTS["MSOL"], f"Wrong mSOL mint: {msol_mint}"

    print(f"  SOL -> {sol_mint[:16]}...")
    print(f"  USDC -> {usdc_mint[:16]}...")
    print(f"  USD1 -> {usd1_mint[:16]}...")
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
    assert isinstance(pool.tvl_usd, Decimal), f"TVL should be Decimal, got {type(pool.tvl_usd)}"
    assert pool.tvl_usd > 0, f"TVL should be > 0, got {pool.tvl_usd}"

    print(f"  Pool: {pool.address[:16]}...")
    print(f"  DEX: {pool.dex}")
    print(f"  Token0: {pool.token0.symbol or pool.token0.mint[:16]}")
    print(f"  Token1: {pool.token1.symbol or pool.token1.mint[:16]}")
    print(f"  Price: {pool.price}")
    print(f"  TVL: ${pool.tvl_usd:,.2f}")
    print("  pool by address (Raydium): PASSED")


def test_pool_by_symbol_raydium(client):
    """Test getting Raydium pool by symbol"""
    print("Testing pool by symbol (Raydium)...")

    pool = client.market.pool_by_symbol("SOL/USDC", dex="raydium")

    assert pool is not None, "Pool should not be None"
    assert pool.dex == "raydium", f"Wrong dex: {pool.dex}"
    assert pool.price > 0, f"Price should be > 0"
    assert pool.tvl_usd > 0, f"TVL should be > 0"

    print(f"  SOL/USDC pool: {pool.address[:16]}...")
    print(f"  Price: {pool.price}")
    print(f"  TVL: ${pool.tvl_usd:,.2f}")
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


def test_pool_by_address_raydium_usd1(client):
    """Test getting Raydium SOL/USD1 pool by address"""
    print("Testing pool by address (Raydium SOL/USD1)...")

    pool = client.market.pool(RAYDIUM_SOL_USD1_POOL, dex="raydium")

    assert pool is not None, "Pool should not be None"
    assert pool.address == RAYDIUM_SOL_USD1_POOL, f"Wrong pool address"
    assert pool.dex == "raydium", f"Wrong dex: {pool.dex}"
    assert pool.price > 0, f"Price should be > 0, got {pool.price}"
    assert isinstance(pool.tvl_usd, Decimal), f"TVL should be Decimal, got {type(pool.tvl_usd)}"
    assert pool.tvl_usd > 0, f"TVL should be > 0, got {pool.tvl_usd}"

    print(f"  Pool: {pool.address[:16]}...")
    print(f"  DEX: {pool.dex}")
    print(f"  Token0: {pool.token0.symbol or pool.token0.mint[:16]}")
    print(f"  Token1: {pool.token1.symbol or pool.token1.mint[:16]}")
    print(f"  Price: {pool.price}")
    print(f"  TVL: ${pool.tvl_usd:,.2f}")
    print("  pool by address (Raydium SOL/USD1): PASSED")


def test_pool_by_symbol_raydium_usd1(client):
    """Test getting Raydium SOL/USD1 pool by symbol"""
    print("Testing pool by symbol (Raydium SOL/USD1)...")

    pool = client.market.pool_by_symbol("SOL/USD1", dex="raydium")

    assert pool is not None, "Pool should not be None"
    assert pool.dex == "raydium", f"Wrong dex: {pool.dex}"
    assert pool.price > 0, f"Price should be > 0"
    assert pool.tvl_usd > 0, f"TVL should be > 0"

    print(f"  SOL/USD1 pool: {pool.address[:16]}...")
    print(f"  Price: {pool.price}")
    print(f"  TVL: ${pool.tvl_usd:,.2f}")
    print("  pool by symbol (Raydium SOL/USD1): PASSED")


def test_pool_by_address_meteora(client):
    """Test getting Meteora pool by address"""
    print("Testing pool by address (Meteora)...")

    pool = client.market.pool(METEORA_SOL_USDC_POOL, dex="meteora")

    assert pool is not None, "Pool should not be None"
    assert pool.address == METEORA_SOL_USDC_POOL, f"Wrong pool address"
    assert pool.dex == "meteora", f"Wrong dex: {pool.dex}"
    assert pool.price > 0, f"Price should be > 0"
    assert pool.tvl_usd > 0, f"TVL should be > 0"

    print(f"  Pool: {pool.address[:16]}...")
    print(f"  DEX: {pool.dex}")
    print(f"  Price: {pool.price}")
    print(f"  TVL: ${pool.tvl_usd:,.2f}")
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


# =============================================================================
# Multi-chain Token Resolution Tests
# =============================================================================

def test_resolve_token_multichain(client):
    """Test resolve_token works for all chains"""
    print("Testing resolve_token (multichain)...")

    # Solana
    sol_mint = client.market.resolve_token("SOL", chain="solana")
    assert sol_mint == SOLANA_TOKEN_MINTS["SOL"], f"Wrong SOL mint"
    print(f"  SOL (solana) -> {sol_mint[:16]}...")

    # Solana USD1
    usd1_mint = client.market.resolve_token("USD1", chain="solana")
    assert usd1_mint == SOLANA_TOKEN_MINTS["USD1"], f"Wrong USD1 mint"
    print(f"  USD1 (solana) -> {usd1_mint[:16]}...")

    # Ethereum
    weth_addr = client.market.resolve_token("WETH", chain="eth")
    assert weth_addr.startswith("0x"), "WETH should be 0x prefixed"
    assert len(weth_addr) == 42, "WETH should be 42 chars"
    print(f"  WETH (eth) -> {weth_addr}")

    # Ethereum USD1
    usd1_eth_addr = client.market.resolve_token("USD1", chain="eth")
    assert usd1_eth_addr.startswith("0x"), "USD1 (eth) should be 0x prefixed"
    assert len(usd1_eth_addr) == 42, "USD1 (eth) should be 42 chars"
    print(f"  USD1 (eth) -> {usd1_eth_addr}")

    # BSC
    wbnb_addr = client.market.resolve_token("WBNB", chain="bsc")
    assert wbnb_addr.startswith("0x"), "WBNB should be 0x prefixed"
    assert len(wbnb_addr) == 42, "WBNB should be 42 chars"
    print(f"  WBNB (bsc) -> {wbnb_addr}")

    # BSC USD1
    usd1_bsc_addr = client.market.resolve_token("USD1", chain="bsc")
    assert usd1_bsc_addr.startswith("0x"), "USD1 (bsc) should be 0x prefixed"
    assert len(usd1_bsc_addr) == 42, "USD1 (bsc) should be 42 chars"
    print(f"  USD1 (bsc) -> {usd1_bsc_addr}")

    print("  resolve_token (multichain): PASSED")


# =============================================================================
# Ethereum (Uniswap) Tests
# =============================================================================

def test_pool_by_symbol_uniswap(client):
    """Test getting Uniswap pool by symbol"""
    print("Testing pool by symbol (Uniswap ETH)...")

    if not has_evm_config():
        print("  SKIPPED: ETH_RPC_URL not configured")
        return

    pool = client.market.pool_by_symbol("ETH/USDT", chain="eth")

    assert pool is not None, "Pool should not be None"
    assert pool.dex == "uniswap", f"Wrong dex: {pool.dex}"
    assert pool.price > 0, f"Price should be > 0, got {pool.price}"
    assert isinstance(pool.tvl_usd, Decimal), f"TVL should be Decimal"
    assert pool.tvl_usd > 0, f"TVL should be > 0, got {pool.tvl_usd}"

    print(f"  ETH/USDT pool: {pool.address}")
    print(f"  Price: {pool.price}")
    print(f"  TVL: ${pool.tvl_usd:,.2f}")
    print(f"  Token0: {pool.token0.symbol}")
    print(f"  Token1: {pool.token1.symbol}")
    print("  pool by symbol (Uniswap ETH): PASSED")


def test_pool_by_address_uniswap(client):
    """Test getting Uniswap pool by address"""
    print("Testing pool by address (Uniswap ETH)...")

    if not has_evm_config():
        print("  SKIPPED: ETH_RPC_URL not configured")
        return

    pool = client.market.pool(UNISWAP_ETH_USDT_POOL, chain="eth")

    assert pool is not None, "Pool should not be None"
    assert pool.address.lower() == UNISWAP_ETH_USDT_POOL.lower(), "Wrong pool address"
    assert pool.dex == "uniswap", f"Wrong dex: {pool.dex}"
    assert pool.price > 0, f"Price should be > 0"
    assert pool.tvl_usd > 0, f"TVL should be > 0"

    print(f"  Pool: {pool.address}")
    print(f"  Price: {pool.price}")
    print(f"  TVL: ${pool.tvl_usd:,.2f}")
    print("  pool by address (Uniswap ETH): PASSED")


def test_price_eth(client):
    """Test getting price on Ethereum"""
    print("Testing price (ETH chain)...")

    if not has_evm_config():
        print("  SKIPPED: ETH_RPC_URL not configured")
        return

    price = client.market.price("ETH/USDT", chain="eth")

    assert isinstance(price, Decimal), f"Expected Decimal, got {type(price)}"
    assert price > 0, f"Price should be > 0, got {price}"

    print(f"  ETH/USDT price: ${price}")
    print("  price (ETH chain): PASSED")


def test_price_usd_eth(client):
    """Test getting USD price for ETH token"""
    print("Testing price_usd (ETH chain)...")

    if not has_evm_config():
        print("  SKIPPED: ETH_RPC_URL not configured")
        return

    price = client.market.price_usd("WETH", chain="eth")

    if price is not None:
        assert isinstance(price, Decimal), f"Expected Decimal, got {type(price)}"
        assert price > 0, f"Price should be > 0"
        print(f"  WETH USD price: ${price}")
    else:
        print(f"  WETH USD price: None (no stablecoin pool found)")

    print("  price_usd (ETH chain): PASSED")


# =============================================================================
# BSC (PancakeSwap) Tests
# =============================================================================

def test_pool_by_symbol_pancakeswap(client):
    """Test getting PancakeSwap pool by symbol"""
    print("Testing pool by symbol (PancakeSwap BSC)...")

    if not has_evm_config():
        print("  SKIPPED: BSC_RPC_URL not configured")
        return

    pool = client.market.pool_by_symbol("WBNB/USDT", chain="bsc")

    assert pool is not None, "Pool should not be None"
    assert pool.dex == "pancakeswap", f"Wrong dex: {pool.dex}"
    assert pool.price > 0, f"Price should be > 0, got {pool.price}"
    assert isinstance(pool.tvl_usd, Decimal), f"TVL should be Decimal"
    assert pool.tvl_usd > 0, f"TVL should be > 0, got {pool.tvl_usd}"

    print(f"  WBNB/USDT pool: {pool.address}")
    print(f"  Price: {pool.price}")
    print(f"  TVL: ${pool.tvl_usd:,.2f}")
    print(f"  Token0: {pool.token0.symbol}")
    print(f"  Token1: {pool.token1.symbol}")
    print("  pool by symbol (PancakeSwap BSC): PASSED")


def test_pool_by_address_pancakeswap(client):
    """Test getting PancakeSwap pool by address"""
    print("Testing pool by address (PancakeSwap BSC)...")

    if not has_evm_config():
        print("  SKIPPED: BSC_RPC_URL not configured")
        return

    pool = client.market.pool(PANCAKESWAP_BNB_USDT_POOL, chain="bsc")

    assert pool is not None, "Pool should not be None"
    assert pool.address.lower() == PANCAKESWAP_BNB_USDT_POOL.lower(), "Wrong pool address"
    assert pool.dex == "pancakeswap", f"Wrong dex: {pool.dex}"
    assert pool.price > 0, f"Price should be > 0"
    assert pool.tvl_usd > 0, f"TVL should be > 0"

    print(f"  Pool: {pool.address}")
    print(f"  Price: {pool.price}")
    print(f"  TVL: ${pool.tvl_usd:,.2f}")
    print("  pool by address (PancakeSwap BSC): PASSED")


def test_price_bsc(client):
    """Test getting price on BSC"""
    print("Testing price (BSC chain)...")

    if not has_evm_config():
        print("  SKIPPED: BSC_RPC_URL not configured")
        return

    price = client.market.price("WBNB/USDT", chain="bsc")

    assert isinstance(price, Decimal), f"Expected Decimal, got {type(price)}"
    assert price > 0, f"Price should be > 0, got {price}"

    print(f"  WBNB/USDT price: ${price}")
    print("  price (BSC chain): PASSED")


def test_price_usd_bsc(client):
    """Test getting USD price for BNB token"""
    print("Testing price_usd (BSC chain)...")

    if not has_evm_config():
        print("  SKIPPED: BSC_RPC_URL not configured")
        return

    price = client.market.price_usd("WBNB", chain="bsc")

    if price is not None:
        assert isinstance(price, Decimal), f"Expected Decimal, got {type(price)}"
        assert price > 0, f"Price should be > 0"
        print(f"  WBNB USD price: ${price}")
    else:
        print(f"  WBNB USD price: None (no stablecoin pool found)")

    print("  price_usd (BSC chain): PASSED")


# =============================================================================
# Chain/DEX Validation Tests
# =============================================================================

def test_invalid_chain_dex_combination(client):
    """Test that invalid chain/dex combinations raise errors"""
    print("Testing invalid chain/dex combinations...")

    from dex_adapter_universal.errors import OperationNotSupported

    # Try using raydium on ETH chain
    try:
        client.market.pool_by_symbol("ETH/USDC", dex="raydium", chain="eth")
        assert False, "Should have raised OperationNotSupported"
    except OperationNotSupported:
        print("  raydium on eth: correctly rejected")

    # Try using uniswap on BSC chain
    try:
        client.market.pool_by_symbol("BNB/USDT", dex="uniswap", chain="bsc")
        assert False, "Should have raised OperationNotSupported"
    except OperationNotSupported:
        print("  uniswap on bsc: correctly rejected")

    # Try using pancakeswap on Solana chain
    try:
        client.market.pool_by_symbol("SOL/USDC", dex="pancakeswap", chain="solana")
        assert False, "Should have raised OperationNotSupported"
    except OperationNotSupported:
        print("  pancakeswap on solana: correctly rejected")

    print("  invalid chain/dex combinations: PASSED")


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

    # Solana tests
    solana_tests = [
        test_resolve_token_mint,
        test_pool_by_address_raydium,
        test_pool_by_symbol_raydium,
        test_pool_by_symbol_case_insensitive,
        test_pool_by_address_raydium_usd1,
        test_pool_by_symbol_raydium_usd1,
        test_pool_by_address_meteora,
        test_price,
        test_price_by_pool_address,
        test_price_usd,
    ]

    # Multi-chain tests (token resolution doesn't need EVM RPC)
    multichain_tests = [
        test_resolve_token_multichain,
        test_invalid_chain_dex_combination,
    ]

    # EVM tests (require ETH_RPC_URL and BSC_RPC_URL)
    evm_tests = [
        test_pool_by_symbol_uniswap,
        test_pool_by_address_uniswap,
        test_price_eth,
        test_price_usd_eth,
        test_pool_by_symbol_pancakeswap,
        test_pool_by_address_pancakeswap,
        test_price_bsc,
        test_price_usd_bsc,
    ]

    tests = solana_tests + multichain_tests + evm_tests

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
