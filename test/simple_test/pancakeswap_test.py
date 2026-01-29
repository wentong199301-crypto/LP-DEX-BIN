"""
Simple PancakeSwap LP Test - Open and Close All Positions

WARNING: This executes REAL transactions and spends REAL tokens!
Chain: BSC (Chain ID 56)
"""

import sys
from decimal import Decimal
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from test.module_test.conftest import skip_if_no_config
from dex_adapter_universal.types.pool import PANCAKESWAP_POOLS
from dex_adapter_universal.types import PriceRange
from dex_adapter_universal.types.evm_tokens import BSC_TOKEN_ADDRESSES


PANCAKESWAP_WBNB_USDT_POOL = PANCAKESWAP_POOLS["USDT/WBNB"]

# Token addresses on BSC
USDT_ADDRESS = BSC_TOKEN_ADDRESSES["USDT"]


def create_adapter():
    """Create PancakeSwapAdapter with real RPC and wallet"""
    from dex_adapter_universal.protocols.pancakeswap import PancakeSwapAdapter
    from dex_adapter_universal.infra.evm_signer import EVMSigner

    signer = EVMSigner.from_env()
    return PancakeSwapAdapter(chain_id=56, signer=signer)


def get_balances(adapter):
    """Get BNB and USDT balances"""
    # BNB balance (native)
    bnb_balance = Decimal(adapter._web3.eth.get_balance(adapter.address)) / Decimal(1e18)

    # USDT balance (BEP20)
    usdt_abi = [{"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"}]
    usdt_contract = adapter._web3.eth.contract(address=adapter._web3.to_checksum_address(USDT_ADDRESS), abi=usdt_abi)
    usdt_raw = usdt_contract.functions.balanceOf(adapter.address).call()
    usdt_balance = Decimal(usdt_raw) / Decimal(1e18)  # BSC USDT has 18 decimals

    return bnb_balance, usdt_balance


def test_open_and_close_position_pancakeswap(adapter):
    """Test opening and closing PancakeSwap V3 LP positions"""

    # Step 1: Check config
    print("Step 1: Checking config...")
    from dex_adapter_universal.config import config
    print(f"  LP slippage: {config.trading.default_lp_slippage_bps} bps")

    # Step 2: Get pool info
    print("\nStep 2: Getting pool info...")
    pool = adapter.get_pool_by_address(PANCAKESWAP_WBNB_USDT_POOL)
    if not pool:
        pool = adapter.get_pool("WBNB", "USDT", fee=2500)
    assert pool is not None, "Pool not found"

    print(f"  Pool: {pool.address}")
    print(f"  Current price: {pool.price}")
    print(f"  Tick spacing: {pool.tick_spacing}")

    # Get initial balances
    print("\n--- WALLET BALANCES (BEFORE) ---")
    bnb_before, usdt_before = get_balances(adapter)
    print(f"  BNB:  {bnb_before:.6f}")
    print(f"  USDT: {usdt_before:.6f}")

    # Step 3: Wrap BNB -> WBNB (needed for symmetric range)
    target_usd = Decimal("1")
    # pool.price = token0/token1 = USDT/WBNB, so price ≈ 0.0011
    # 1 WBNB = 1/price USDT. To get $1 of WBNB: amount_wbnb = target_usd * price
    wbnb_needed = target_usd * pool.price  # WBNB amount worth ~$1
    print(f"\nStep 3: Wrapping ~{wbnb_needed:.6f} BNB -> WBNB...")
    wrap_tx = adapter.wrap_native(wbnb_needed)
    print(f"  Wrap TX: {wrap_tx}")

    # Step 4: Open new position with ±1% symmetric range
    amount0 = target_usd  # USDT ≈ $1
    amount1 = wbnb_needed
    print(f"\nStep 4: Opening position with ~{amount0} USDT + ~{amount1:.6f} WBNB, ±1% range...")

    open_result = adapter.open_position(
        pool=pool,
        price_range=PriceRange.percent(0.01),
        amount0=amount0,
        amount1=amount1,
    )
    print(f"  Status: {open_result.status}")
    print(f"  TX Hash: {open_result.signature}")
    assert open_result.is_success, f"Open position failed: {open_result.error}"

    # Step 4: Close ALL PancakeSwap positions
    print("\nStep 4: Closing ALL PancakeSwap positions...")
    close_results = adapter.close_position()

    if not close_results:
        print("  No positions to close")
    else:
        print(f"  Closed {len(close_results)} position(s):")
        for i, result in enumerate(close_results):
            status = "OK" if result.is_success else "FAILED"
            print(f"    [{i+1}] {status}: {result.signature}")

        failed = [r for r in close_results if not r.is_success]
        assert len(failed) == 0, f"{len(failed)} position(s) failed to close"

    # Get final balances
    print("\n--- WALLET BALANCES (AFTER) ---")
    bnb_after, usdt_after = get_balances(adapter)
    print(f"  BNB:  {bnb_after:.6f}")
    print(f"  USDT: {usdt_after:.6f}")

    # Balance differences
    bnb_diff = bnb_after - bnb_before
    usdt_diff = usdt_after - usdt_before

    # Cost Summary
    print("\n" + "=" * 50)
    print("COST SUMMARY (PancakeSwap)")
    print("=" * 50)
    print("  WALLET BALANCE CHANGES:")
    print(f"    BNB:  {bnb_diff:+.9f}")
    print(f"    USDT: {usdt_diff:+.6f}")
    print()
    print(f"  NET BNB COST (gas only): {-bnb_diff:.9f} BNB")
    print("=" * 50)

    print("\n  Open & Close ALL positions (PancakeSwap): PASSED")


def main():
    print("=" * 60)
    print("PancakeSwap LP Test - Open & Close")
    print("=" * 60)
    print()
    print("WARNING: REAL transactions with REAL tokens!")
    print("Chain: BSC (Chain ID 56)")
    print()

    # Check EVM config
    import os
    if not os.getenv("EVM_PRIVATE_KEY"):
        print("\nSKIPPED: Missing EVM_PRIVATE_KEY")
        return True

    try:
        from web3 import Web3
    except ImportError:
        print("\nSKIPPED: web3 not installed")
        return True

    print("Creating PancakeSwapAdapter...")
    adapter = create_adapter()
    print(f"  Wallet: {adapter.address}")
    print()

    try:
        test_open_and_close_position_pancakeswap(adapter)
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
