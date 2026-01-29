"""
Meteora Liquidity Module Integration Tests

WARNING: These tests execute REAL LP operations and spend REAL tokens!

Tests Meteora DLMM LP operations with live Solana RPC.
All operations have automatic retry logic for transient failures.
"""

import sys
from decimal import Decimal
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from conftest import create_client, skip_if_no_config
from dex_adapter_universal.types.pool import METEORA_POOLS


# Use pool from registry
METEORA_SOL_USDC_POOL = METEORA_POOLS["SOL/USDC"]

# Minimum balances required for LP tests
MIN_SOL_BALANCE = Decimal("0.03")
MIN_USDC_BALANCE = Decimal("2")


def test_retry_config_meteora(client):
    """Test that retry configuration is properly set for Meteora operations"""
    print("Testing retry config (Meteora)...")

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
    is_recoverable, is_slippage, error_code = classify_error(Exception("timeout error"))
    assert is_recoverable, "timeout should be recoverable"

    is_recoverable, is_slippage, error_code = classify_error(Exception("slippage exceeded"))
    assert is_slippage, "slippage should be identified"

    print("  retry config (Meteora): PASSED")


def test_list_positions_meteora(client):
    """Test listing Meteora LP positions"""
    print("Testing list Meteora positions...")

    positions = client.lp.positions(dex="meteora")

    assert isinstance(positions, list), f"Expected list, got {type(positions)}"
    print(f"  Found {len(positions)} Meteora positions")

    for pos in positions[:3]:
        print(f"    {pos.id[:16]}... | {pos.dex}")
        if hasattr(pos, 'lower_bin_id'):
            print(f"      Bin range: {pos.lower_bin_id} - {pos.upper_bin_id}")

    print("  list Meteora positions: PASSED")


def test_open_position_meteora(client):
    """Test opening a Meteora DLMM LP position with real transaction"""
    print("Testing open position (Meteora) (REAL TRANSACTION)...")

    # Check balances
    sol_balance = client.wallet.balance("SOL")
    usdc_balance = client.wallet.balance("USDC")

    print(f"  SOL balance: {sol_balance}")
    print(f"  USDC balance: {usdc_balance}")

    from dex_adapter_universal.types import PriceRange

    pool = client.market.pool(METEORA_SOL_USDC_POOL, dex="meteora")
    print(f"  Pool: {pool.address[:16]}...")
    print(f"  Current price: {pool.price}")
    print(f"  Active bin ID: {getattr(pool, 'active_bin_id', 'N/A')}")

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
    print("  open position (Meteora): PASSED")


def test_open_position_one_bin_meteora(client):
    """Test opening a one-bin (single bin) Meteora LP position with real transaction"""
    print("Testing open one-bin position (Meteora) (REAL TRANSACTION)...")

    # Check balances
    sol_balance = client.wallet.balance("SOL")
    usdc_balance = client.wallet.balance("USDC")

    print(f"  SOL balance: {sol_balance}")
    print(f"  USDC balance: {usdc_balance}")

    from dex_adapter_universal.types import PriceRange

    pool = client.market.pool(METEORA_SOL_USDC_POOL, dex="meteora")

    # Open one-bin position (narrowest range - Meteora equivalent of one-tick)
    print(f"  Opening one-bin position with $2 USD...")
    result = client.lp.open(
        pool=pool,
        price_range=PriceRange.one_tick(),  # Maps to one_bin_range for Meteora
        amount_usd=Decimal("2"),
    )

    print(f"  Status: {result.status}")
    print(f"  Signature: {result.signature}")

    assert result.is_success, f"Open position failed: {result.error}"
    print("  open one-bin position (Meteora): PASSED")


def test_add_liquidity_meteora(client):
    """Test adding liquidity to existing Meteora position with real transaction"""
    print("Testing add liquidity (Meteora) (REAL TRANSACTION)...")

    # Get existing Meteora positions
    positions = client.lp.positions(dex="meteora")
    assert len(positions) > 0, "No existing Meteora positions to add to"

    position = positions[0]
    print(f"  Adding to position: {position.id[:16]}...")

    # Verify Meteora-specific fields
    if hasattr(position, 'lower_bin_id'):
        print(f"  Lower bin ID: {position.lower_bin_id}")
    if hasattr(position, 'upper_bin_id'):
        print(f"  Upper bin ID: {position.upper_bin_id}")
    if hasattr(position, 'bin_ids'):
        print(f"  Bin IDs count: {len(position.bin_ids)}")

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
    print("  add liquidity (Meteora): PASSED")


def test_remove_liquidity_partial_meteora(client):
    """Test removing partial liquidity from Meteora position with real transaction"""
    print("Testing remove liquidity (Meteora) (partial) (REAL TRANSACTION)...")

    # Get existing Meteora positions
    positions = client.lp.positions(dex="meteora")
    assert len(positions) > 0, "No existing Meteora positions"

    position = positions[0]
    print(f"  Removing 25% from position: {position.id[:16]}...")

    # Verify Meteora-specific fields
    if hasattr(position, 'bin_ids'):
        print(f"  Bin IDs: {position.bin_ids[:5]}..." if len(position.bin_ids) > 5 else f"  Bin IDs: {position.bin_ids}")

    result = client.lp.remove(
        position=position,
        percent=25.0,
    )

    print(f"  Status: {result.status}")
    print(f"  Signature: {result.signature}")

    assert result.is_success, f"Remove liquidity failed: {result.error}"
    print("  remove liquidity (Meteora) (partial): PASSED")


def test_claim_fees_meteora(client):
    """Test claiming fees from Meteora position with real transaction"""
    print("Testing claim fees (Meteora) (REAL TRANSACTION)...")

    # Get existing Meteora positions
    positions = client.lp.positions(dex="meteora")
    assert len(positions) > 0, "No existing Meteora positions"

    position = positions[0]
    print(f"  Claiming fees from position: {position.id[:16]}...")

    result = client.lp.claim(position)

    print(f"  Status: {result.status}")
    print(f"  Signature: {result.signature}")

    # May skip if nothing to claim - that's OK
    if not result.is_success:
        if "Nothing to claim" in str(result.error):
            print(f"  No fees to claim (this is OK)")
        else:
            assert result.is_success, f"Claim fees failed: {result.error}"

    print("  claim fees (Meteora): PASSED")


def test_close_position_meteora(client):
    """Test closing a single Meteora LP position with real transaction"""
    print("Testing close single position (Meteora) (REAL TRANSACTION)...")

    # Get existing Meteora positions
    positions = client.lp.positions(dex="meteora")
    assert len(positions) > 0, "No existing Meteora positions to close"

    position = positions[0]
    print(f"  Closing position: {position.id[:16]}...")

    result = client.lp.close(position)

    print(f"  Status: {result.status}")
    print(f"  Signature: {result.signature}")

    assert result.is_success, f"Close position failed: {result.error}"
    print("  close single position (Meteora): PASSED")


def test_close_all_positions_meteora(client):
    """Test closing all Meteora LP positions with real transaction"""
    print("Testing close ALL positions (Meteora) (REAL TRANSACTION)...")

    # Check how many positions exist
    positions = client.lp.positions(dex="meteora")
    print(f"  Found {len(positions)} Meteora positions to close")

    if not positions:
        print("  No positions to close (this is OK)")
        print("  close ALL positions (Meteora): PASSED")
        return

    # Close all Meteora positions
    results = client.lp.close(dex="meteora")

    print(f"  Closed {len(results)} position(s):")
    for i, result in enumerate(results):
        status = "OK" if result.is_success else "FAILED"
        print(f"    [{i+1}] {status}: {result.signature}")

    # Check all succeeded
    failed = [r for r in results if not r.is_success]
    assert len(failed) == 0, f"{len(failed)} position(s) failed to close"

    print("  close ALL positions (Meteora): PASSED")


def test_full_lifecycle_meteora(client):
    """Test full Meteora position lifecycle: open -> claim -> close with Meteora-specific validations"""
    print("Testing full lifecycle (Meteora) (REAL TRANSACTIONS)...")

    # Check balances
    sol_balance = client.wallet.balance("SOL")
    usdc_balance = client.wallet.balance("USDC")

    print(f"  SOL balance: {sol_balance}")
    print(f"  USDC balance: {usdc_balance}")

    from dex_adapter_universal.types import PriceRange

    pool = client.market.pool(METEORA_SOL_USDC_POOL, dex="meteora")
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

    # Step 2: Get the position and verify Meteora-specific fields
    print(f"  Step 2: Fetching position and verifying Meteora fields...")
    positions = client.lp.positions(dex="meteora")
    assert len(positions) > 0, "Position not found after opening"

    position = positions[0]
    print(f"    Position ID: {position.id[:16]}...")

    # Verify Meteora-specific fields are populated
    if hasattr(position, 'lower_bin_id'):
        print(f"    Lower bin ID: {position.lower_bin_id}")
        assert position.lower_bin_id is not None, "lower_bin_id should be populated"
    if hasattr(position, 'upper_bin_id'):
        print(f"    Upper bin ID: {position.upper_bin_id}")
        assert position.upper_bin_id is not None, "upper_bin_id should be populated"
    if hasattr(position, 'bin_ids'):
        print(f"    Bin IDs count: {len(position.bin_ids)}")
        assert len(position.bin_ids) > 0, "bin_ids list should not be empty"

    # Step 3: Claim fees (may have nothing to claim)
    print(f"  Step 3: Claiming fees...")
    claim_result = client.lp.claim(position)
    print(f"    Claim status: {claim_result.status}")

    # Step 4: Close ALL Meteora positions
    print(f"  Step 4: Closing ALL Meteora positions...")
    close_results = client.lp.close(dex="meteora")

    if isinstance(close_results, list):
        print(f"    Closed {len(close_results)} position(s)")
        for result in close_results:
            assert result.is_success, f"Close failed: {result.error}"
    else:
        assert close_results.is_success, f"Close failed: {close_results.error}"

    print("  full lifecycle (Meteora): PASSED")


def main():
    """Run all Meteora liquidity module tests"""
    print("=" * 60)
    print("Meteora Liquidity Module Integration Tests")
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
        test_retry_config_meteora,
        test_list_positions_meteora,
        test_open_position_meteora,
        test_open_position_one_bin_meteora,
        test_add_liquidity_meteora,
        test_remove_liquidity_partial_meteora,
        test_claim_fees_meteora,
        test_close_position_meteora,
        test_close_all_positions_meteora,
        test_full_lifecycle_meteora,
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
