"""
Simple Meteora LP Test - Open and Close All Positions

WARNING: This executes REAL transactions and spends REAL tokens!
"""

import sys
from decimal import Decimal
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from test.module_test.conftest import create_client, skip_if_no_config
from dex_adapter_universal.types.pool import METEORA_POOLS
from dex_adapter_universal.types import PriceRange
METEORA_SOL_USDC_POOL = METEORA_POOLS["SOL/USDC"]


def get_balances(client):
    """Get SOL and USDC balances"""
    sol_balance = client.wallet.balance("SOL", "solana")
    usdc_balance = client.wallet.balance("USDC", "solana")
    return sol_balance, usdc_balance


def test_open_and_close_position_meteora(client):
    """Test opening and closing Meteora DLMM LP positions"""

    # Cost tracking
    costs = {"open": [], "close": []}

    # Step 1: Check config
    print("Step 1: Checking config...")
    from dex_adapter_universal.config import config
    print(f"  LP slippage: {config.trading.default_lp_slippage_bps} bps")

    # Step 2: Get pool info
    print("\nStep 2: Getting pool info...")
    pool = client.market.pool(METEORA_SOL_USDC_POOL, dex="meteora")
    print(f"  Pool: {pool.address[:16]}...")
    print(f"  Current price: {pool.price}")
    print(f"  Bin step: {getattr(pool, 'bin_step', 'N/A')}")

    # Get initial balances
    print("\n--- WALLET BALANCES (BEFORE) ---")
    sol_before, usdc_before = get_balances(client)
    print(f"  SOL:  {sol_before}")
    print(f"  USDC: {usdc_before}")

    # Step 3: Open new position
    print("\nStep 3: Opening position with $2 USD, +/- 1% range...")
    open_result = client.lp.open(
        pool=pool,
        price_range=PriceRange.percent(0.01),
        amount_usd=Decimal("2"),
    )
    print(f"  Status: {open_result.status}")
    print(f"  Signature: {open_result.signature}")
    if open_result.fee_lamports:
        costs["open"].append(open_result.fee_lamports)
        print(f"  Fee: {open_result.fee_lamports} lamports ({open_result.fee_sol:.6f} SOL)")
    assert open_result.is_success, f"Open position failed: {open_result.error}"

    # Step 4: Close ALL Meteora positions
    print("\nStep 4: Closing ALL Meteora positions...")

    # Debug: List all positions with their bin_ids
    positions = client.lp.positions(dex="meteora")
    print(f"  Found {len(positions)} position(s):")
    for i, pos in enumerate(positions):
        bin_ids = getattr(pos, 'bin_ids', [])
        lower = getattr(pos, 'lower_bin_id', 'N/A')
        upper = getattr(pos, 'upper_bin_id', 'N/A')
        liq = pos.liquidity
        print(f"    [{i+1}] {pos.id[:16]}...")
        print(f"        bin_ids count: {len(bin_ids)}, range: {lower} to {upper}")
        print(f"        liquidity: {liq}")
        if bin_ids:
            print(f"        first 5 bin_ids: {bin_ids[:5]}")
            print(f"        last 5 bin_ids: {bin_ids[-5:]}")

    close_results = client.lp.close(dex="meteora")

    if not close_results:
        print("  No positions to close")
    else:
        print(f"  Closed {len(close_results)} position(s):")
        for i, result in enumerate(close_results):
            status = "OK" if result.is_success else "FAILED"
            fee_info = ""
            if result.fee_lamports:
                costs["close"].append(result.fee_lamports)
                fee_info = f" | Fee: {result.fee_lamports} lamports"
            print(f"    [{i+1}] {status}: {result.signature}{fee_info}")

        failed = [r for r in close_results if not r.is_success]
        assert len(failed) == 0, f"{len(failed)} position(s) failed to close"

    # Get final balances
    print("\n--- WALLET BALANCES (AFTER) ---")
    sol_after, usdc_after = get_balances(client)
    print(f"  SOL:  {sol_after}")
    print(f"  USDC: {usdc_after}")

    # Balance differences
    sol_diff = sol_after - sol_before
    usdc_diff = usdc_after - usdc_before

    # Cost Summary
    print("\n" + "=" * 50)
    print("COST SUMMARY (Meteora)")
    print("=" * 50)
    total_open = sum(costs["open"])
    total_close = sum(costs["close"])
    total_fees = total_open + total_close
    print(f"  Open fee:       {total_open:>10} lamports ({total_open / 1e9:.6f} SOL)")
    print(f"  Close fee:      {total_close:>10} lamports ({total_close / 1e9:.6f} SOL)")
    print(f"  ----------------------------------------")
    print(f"  TOTAL FEES:     {total_fees:>10} lamports ({total_fees / 1e9:.6f} SOL)")
    print()
    print("  WALLET BALANCE CHANGES:")
    print(f"    SOL:  {sol_diff:+.9f}")
    print(f"    USDC: {usdc_diff:+.6f}")
    print()
    print(f"  NET SOL COST (fees only): {-sol_diff:.9f} SOL")
    print("=" * 50)

    print("\n  Open & Close ALL positions (Meteora): PASSED")


def main():
    print("=" * 60)
    print("Meteora LP Test - Open & Close")
    print("=" * 60)
    print()
    print("WARNING: REAL transactions with REAL tokens!")
    print()

    skip_msg = skip_if_no_config()
    if skip_msg:
        print(f"\nSKIPPED: {skip_msg}")
        return True

    print("Creating DexClient...")
    client = create_client()
    print(f"  Wallet: {client.wallet.address}")
    print()

    try:
        test_open_and_close_position_meteora(client)
        print()
        print("=" * 60)
        print("All tests PASSED")
        print("=" * 60)
        return True
    except Exception as e:
        print(f"\nFAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
