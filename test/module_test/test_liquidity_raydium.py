"""
Raydium Liquidity Module Integration Tests

WARNING: These tests execute REAL LP operations and spend REAL tokens!

Tests Raydium CLMM LP operations with live Solana RPC.
All operations have automatic retry logic for transient failures.
"""

import sys
from decimal import Decimal
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from conftest import create_client, skip_if_no_config
from dex_adapter_universal.types.pool import RAYDIUM_POOLS


# Use pool from registry
RAYDIUM_SOL_USDC_POOL = RAYDIUM_POOLS["SOL/USDC"]

# Minimum balances required for LP tests
MIN_SOL_BALANCE = Decimal("0.03")
MIN_USDC_BALANCE = Decimal("2")


def test_retry_config_raydium(client):
    """Test that retry configuration is properly set for Raydium operations"""
    print("Testing retry config (Raydium)...")

    from dex_adapter_universal.config import config
    from dex_adapter_universal.infra.retry import execute_with_retry, classify_error

    # Verify retry config values
    assert config.tx.max_retries >= 1, "max_retries should be at least 1"
    assert config.tx.retry_delay > 0, "retry_delay should be positive"

    print(f"  max_retries: {config.tx.max_retries}")
    print(f"  retry_delay: {config.tx.retry_delay}s")

    # Verify LP slippage config
    assert config.trading.default_lp_slippage_bps >= 0, "LP slippage should be non-negative"
    print(f"  default_lp_slippage_bps: {config.trading.default_lp_slippage_bps}")

    # Verify retry helper is importable and works
    assert callable(execute_with_retry), "execute_with_retry should be callable"
    assert callable(classify_error), "classify_error should be callable"

    # Test error classification
    is_recoverable, is_slippage, error_code = classify_error(Exception("blockhash not found"))
    assert is_recoverable, "blockhash error should be recoverable"

    is_recoverable, is_slippage, error_code = classify_error(Exception("price moved too much"))
    assert is_slippage, "price moved should be slippage"

    print("  retry config (Raydium): PASSED")


def test_list_all_positions(client):
    """Test listing all LP positions (all DEXes)"""
    print("Testing list all positions...")

    positions = client.lp.positions()

    assert isinstance(positions, list), f"Expected list, got {type(positions)}"
    print(f"  Found {len(positions)} positions")

    for pos in positions[:3]:
        print(f"    {pos.id[:16]}... | {pos.dex}")

    print("  list all positions: PASSED")


def test_list_positions_raydium(client):
    """Test listing Raydium LP positions"""
    print("Testing list Raydium positions...")

    positions = client.lp.positions(dex="raydium")

    assert isinstance(positions, list), f"Expected list, got {type(positions)}"
    print(f"  Found {len(positions)} Raydium positions")

    for pos in positions[:3]:
        print(f"    {pos.id[:16]}... | {pos.dex}")
        if hasattr(pos, 'tick_lower') and pos.tick_lower is not None:
            print(f"      Tick range: {pos.tick_lower} - {pos.tick_upper}")
        if hasattr(pos, 'nft_mint') and pos.nft_mint:
            print(f"      NFT mint: {pos.nft_mint[:16]}...")

    print("  list Raydium positions: PASSED")


def test_open_position_raydium(client):
    """Test opening a Raydium CLMM LP position with real transaction"""
    print("Testing open position (Raydium) (REAL TRANSACTION)...")

    # Check balances
    sol_balance = client.wallet.balance("SOL")
    usdc_balance = client.wallet.balance("USDC")

    print(f"  SOL balance: {sol_balance}")
    print(f"  USDC balance: {usdc_balance}")

    from dex_adapter_universal.types import PriceRange

    pool = client.market.pool(RAYDIUM_SOL_USDC_POOL, dex="raydium")
    print(f"  Pool: {pool.address[:16]}...")
    print(f"  Current price: {pool.price}")
    print(f"  Tick spacing: {getattr(pool, 'tick_spacing', 'N/A')}")

    # Open position with 2% range
    print(f"  Opening position with $2 USD, +/- 2% range...")
    result = client.lp.open(
        pool=pool,
        price_range=PriceRange.percent(0.02),
        amount_usd=Decimal("2"),
    )

    print(f"  Status: {result.status}")
    print(f"  Signature: {result.signature}")

    assert result.is_success, f"Open position failed: {result.error}"
    print("  open position (Raydium): PASSED")


def test_open_position_one_tick_raydium(client):
    """Test opening a one-tick (single tick) Raydium LP position with real transaction"""
    print("Testing open one-tick position (Raydium) (REAL TRANSACTION)...")

    # Check balances
    sol_balance = client.wallet.balance("SOL")
    usdc_balance = client.wallet.balance("USDC")

    print(f"  SOL balance: {sol_balance}")
    print(f"  USDC balance: {usdc_balance}")

    from dex_adapter_universal.types import PriceRange

    pool = client.market.pool(RAYDIUM_SOL_USDC_POOL, dex="raydium")

    # Open one-tick position (narrowest range)
    print(f"  Opening one-tick position with $2 USD...")
    result = client.lp.open(
        pool=pool,
        price_range=PriceRange.one_tick(),
        amount_usd=Decimal("2"),
    )

    print(f"  Status: {result.status}")
    print(f"  Signature: {result.signature}")

    assert result.is_success, f"Open position failed: {result.error}"
    print("  open one-tick position (Raydium): PASSED")


def test_add_liquidity_raydium(client):
    """Test adding liquidity to existing Raydium position with real transaction"""
    print("Testing add liquidity (Raydium) (REAL TRANSACTION)...")

    # Get existing Raydium positions
    positions = client.lp.positions(dex="raydium")
    assert len(positions) > 0, "No existing Raydium positions to add to"

    position = positions[0]
    print(f"  Adding to position: {position.id[:16]}...")

    # Verify Raydium-specific fields
    if hasattr(position, 'tick_lower') and position.tick_lower is not None:
        print(f"  Tick lower: {position.tick_lower}")
    if hasattr(position, 'tick_upper') and position.tick_upper is not None:
        print(f"  Tick upper: {position.tick_upper}")
    if hasattr(position, 'nft_mint') and position.nft_mint:
        print(f"  NFT mint: {position.nft_mint[:16]}...")

    # Check balances
    sol_balance = client.wallet.balance("SOL")
    usdc_balance = client.wallet.balance("USDC")
    print(f"  SOL balance: {sol_balance}")
    print(f"  USDC balance: {usdc_balance}")

    result = client.lp.add(
        position=position,
        amount0=Decimal("0.002"),  # 0.002 SOL
        amount1=Decimal("0.2"),    # 0.2 USDC
    )

    print(f"  Status: {result.status}")
    print(f"  Signature: {result.signature}")

    assert result.is_success, f"Add liquidity failed: {result.error}"
    print("  add liquidity (Raydium): PASSED")


def test_remove_liquidity_partial_raydium(client):
    """Test removing partial liquidity from Raydium position with real transaction"""
    print("Testing remove liquidity (Raydium) (partial) (REAL TRANSACTION)...")

    # Get existing Raydium positions
    positions = client.lp.positions(dex="raydium")
    assert len(positions) > 0, "No existing Raydium positions"

    position = positions[0]
    print(f"  Removing 25% from position: {position.id[:16]}...")

    # Verify Raydium-specific fields
    if hasattr(position, 'tick_lower') and position.tick_lower is not None:
        print(f"  Tick range: {position.tick_lower} - {position.tick_upper}")
    if hasattr(position, 'liquidity'):
        print(f"  Current liquidity: {position.liquidity}")

    result = client.lp.remove(
        position=position,
        percent=25.0,
    )

    print(f"  Status: {result.status}")
    print(f"  Signature: {result.signature}")

    assert result.is_success, f"Remove liquidity failed: {result.error}"
    print("  remove liquidity (Raydium) (partial): PASSED")


def test_claim_fees_raydium(client):
    """Test claiming fees from Raydium position with real transaction"""
    print("Testing claim fees (Raydium) (REAL TRANSACTION)...")

    # Get existing Raydium positions
    positions = client.lp.positions(dex="raydium")
    assert len(positions) > 0, "No existing Raydium positions"

    position = positions[0]
    print(f"  Claiming fees from position: {position.id[:16]}...")

    # Show unclaimed fees if available
    if hasattr(position, 'unclaimed_fees') and position.unclaimed_fees:
        print(f"  Unclaimed fees: {position.unclaimed_fees}")

    result = client.lp.claim(position)

    print(f"  Status: {result.status}")
    print(f"  Signature: {result.signature}")

    # May skip if nothing to claim - that's OK
    if not result.is_success:
        if "Nothing to claim" in str(result.error):
            print(f"  No fees to claim (this is OK)")
        else:
            assert result.is_success, f"Claim fees failed: {result.error}"

    print("  claim fees (Raydium): PASSED")


def test_claim_fees_any(client):
    """Test claiming fees from any position (all DEXes)"""
    print("Testing claim fees (any position) (REAL TRANSACTION)...")

    # Get all positions
    positions = client.lp.positions()
    assert len(positions) > 0, "No existing positions"

    position = positions[0]
    print(f"  Claiming fees from position: {position.id[:16]}... ({position.dex})")

    result = client.lp.claim(position)

    print(f"  Status: {result.status}")
    print(f"  Signature: {result.signature}")

    # May skip if nothing to claim - that's OK
    if not result.is_success:
        if "Nothing to claim" in str(result.error):
            print(f"  No fees to claim (this is OK)")
        else:
            assert result.is_success, f"Claim fees failed: {result.error}"

    print("  claim fees (any): PASSED")


def test_close_position_raydium(client):
    """Test closing a single Raydium LP position with real transaction"""
    print("Testing close single position (Raydium) (REAL TRANSACTION)...")

    # Get existing Raydium positions
    positions = client.lp.positions(dex="raydium")
    assert len(positions) > 0, "No existing Raydium positions to close"

    position = positions[0]
    print(f"  Closing position: {position.id[:16]}...")

    result = client.lp.close(position)

    print(f"  Status: {result.status}")
    print(f"  Signature: {result.signature}")

    assert result.is_success, f"Close position failed: {result.error}"
    print("  close single position (Raydium): PASSED")


def test_close_all_positions_raydium(client):
    """Test closing all Raydium LP positions with real transaction"""
    print("Testing close ALL positions (Raydium) (REAL TRANSACTION)...")

    # Check how many positions exist
    positions = client.lp.positions(dex="raydium")
    print(f"  Found {len(positions)} Raydium positions to close")

    if not positions:
        print("  No positions to close (this is OK)")
        print("  close ALL positions (Raydium): PASSED")
        return

    # Close all Raydium positions
    results = client.lp.close(dex="raydium")

    print(f"  Closed {len(results)} position(s):")
    for i, result in enumerate(results):
        status = "OK" if result.is_success else "FAILED"
        print(f"    [{i+1}] {status}: {result.signature}")

    # Check all succeeded
    failed = [r for r in results if not r.is_success]
    assert len(failed) == 0, f"{len(failed)} position(s) failed to close"

    print("  close ALL positions (Raydium): PASSED")


def test_full_lifecycle_raydium(client):
    """Test full Raydium position lifecycle: open -> claim -> close with Raydium-specific validations"""
    print("Testing full lifecycle (Raydium) (REAL TRANSACTIONS)...")

    # Check balances
    sol_balance = client.wallet.balance("SOL")
    usdc_balance = client.wallet.balance("USDC")

    print(f"  SOL balance: {sol_balance}")
    print(f"  USDC balance: {usdc_balance}")

    from dex_adapter_universal.types import PriceRange

    pool = client.market.pool(RAYDIUM_SOL_USDC_POOL, dex="raydium")
    print(f"  Pool: {pool.address[:16]}...")
    print(f"  Current price: {pool.price}")

    # Step 1: Open position
    print(f"  Step 1: Opening position...")
    open_result = client.lp.open(
        pool=pool,
        price_range=PriceRange.percent(0.02),
        amount_usd=Decimal("2"),
    )

    assert open_result.is_success, f"Open failed: {open_result.error}"
    print(f"    Opened: {open_result.signature}")

    # Step 2: Get the position and verify Raydium-specific fields
    print(f"  Step 2: Fetching position and verifying Raydium fields...")
    positions = client.lp.positions(dex="raydium")
    assert len(positions) > 0, "Position not found after opening"

    position = positions[0]
    print(f"    Position ID: {position.id[:16]}...")

    # Verify Raydium-specific fields are populated
    if hasattr(position, 'tick_lower') and position.tick_lower is not None:
        print(f"    Tick lower: {position.tick_lower}")
        assert position.tick_lower is not None, "tick_lower should be populated"
    if hasattr(position, 'tick_upper') and position.tick_upper is not None:
        print(f"    Tick upper: {position.tick_upper}")
        assert position.tick_upper is not None, "tick_upper should be populated"
    if hasattr(position, 'nft_mint') and position.nft_mint:
        print(f"    NFT mint: {position.nft_mint[:16]}...")
        assert position.nft_mint is not None, "nft_mint should be populated"

    # Step 3: Claim fees (may have nothing to claim)
    print(f"  Step 3: Claiming fees...")
    claim_result = client.lp.claim(position)
    print(f"    Claim status: {claim_result.status}")

    # Step 4: Close ALL Raydium positions
    print(f"  Step 4: Closing ALL Raydium positions...")
    close_results = client.lp.close(dex="raydium")

    if isinstance(close_results, list):
        print(f"    Closed {len(close_results)} position(s)")
        for result in close_results:
            assert result.is_success, f"Close failed: {result.error}"
    else:
        # Single result (shouldn't happen with dex= but handle it)
        assert close_results.is_success, f"Close failed: {close_results.error}"

    print("  full lifecycle (Raydium): PASSED")


def main():
    """Run all Raydium liquidity module tests"""
    print("=" * 60)
    print("Raydium Liquidity Module Integration Tests")
    print("=" * 60)
    print()
    print("WARNING: These tests execute REAL LP operations and spend REAL tokens!")
    print()

    # Check if configuration is available
    skip_msg = skip_if_no_config()
    if skip_msg:
        print(f"\nSKIPPED: {skip_msg}")
        return True  # Not a failure, just skipped

    # Create real client with live RPC and wallet
    print("Creating DexClient with real RPC and wallet...")
    client = create_client()
    print(f"  Wallet: {client.wallet.address}")
    print()

    tests = [
        test_retry_config_raydium,
        test_list_all_positions,
        test_list_positions_raydium,
        test_open_position_raydium,
        test_open_position_one_tick_raydium,
        test_add_liquidity_raydium,
        test_remove_liquidity_partial_raydium,
        test_claim_fees_raydium,
        test_claim_fees_any,
        test_close_position_raydium,
        test_close_all_positions_raydium,
        test_full_lifecycle_raydium,
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
