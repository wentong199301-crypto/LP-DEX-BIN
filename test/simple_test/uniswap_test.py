"""
Simple Uniswap LP Test - Open and Close All Positions

WARNING: This executes REAL transactions and spends REAL tokens!
Chain: Ethereum (Chain ID 1)
"""

import sys
from decimal import Decimal
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from test.module_test.conftest import skip_if_no_config
from dex_adapter_universal.types.pool import UNISWAP_POOLS
from dex_adapter_universal.types import PriceRange
from dex_adapter_universal.types.evm_tokens import ETH_TOKEN_ADDRESSES


UNISWAP_WETH_USDC_POOL = UNISWAP_POOLS["USDC/WETH"]

# Token addresses on Ethereum
USDC_ADDRESS = ETH_TOKEN_ADDRESSES["USDC"]


def create_adapter():
    """Create UniswapAdapter with real RPC and wallet"""
    from dex_adapter_universal.protocols.uniswap import UniswapAdapter
    from dex_adapter_universal.infra.evm_signer import EVMSigner

    signer = EVMSigner.from_env()
    return UniswapAdapter(chain_id=1, signer=signer)


def get_balances(adapter):
    """Get ETH and USDC balances"""
    # ETH balance (native)
    eth_balance = Decimal(adapter._web3.eth.get_balance(adapter.address)) / Decimal(1e18)

    # USDC balance (ERC20)
    usdc_abi = [{"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"}]
    usdc_contract = adapter._web3.eth.contract(address=adapter._web3.to_checksum_address(USDC_ADDRESS), abi=usdc_abi)
    usdc_raw = usdc_contract.functions.balanceOf(adapter.address).call()
    usdc_balance = Decimal(usdc_raw) / Decimal(1e6)  # USDC has 6 decimals

    return eth_balance, usdc_balance


def test_open_and_close_position_uniswap(adapter):
    """Test opening and closing Uniswap V3 LP positions"""

    # Step 1: Check config
    print("Step 1: Checking config...")
    from dex_adapter_universal.config import config
    print(f"  LP slippage: {config.trading.default_lp_slippage_bps} bps")

    # Step 2: Get pool info
    print("\nStep 2: Getting pool info...")
    pool = adapter.get_pool_by_address(UNISWAP_WETH_USDC_POOL)
    if not pool:
        pool = adapter.get_pool("WETH", "USDC", fee=3000, version="v3")
    assert pool is not None, "Pool not found"

    print(f"  Pool: {pool.address}")
    print(f"  Token0: {pool.token0.symbol} (USDC)")
    print(f"  Token1: {pool.token1.symbol} (WETH)")
    print(f"  Current price: {pool.price}")
    print(f"  Tick spacing: {pool.tick_spacing}")

    # Get initial balances
    print("\n--- WALLET BALANCES (BEFORE) ---")
    eth_before, usdc_before = get_balances(adapter)
    print(f"  ETH:  {eth_before:.6f}")
    print(f"  USDC: {usdc_before:.6f}")

    # Check minimum balance for opening new position
    min_eth_for_open = Decimal("0.001")
    min_usdc_for_position = Decimal("1")

    if eth_before >= min_eth_for_open and usdc_before >= min_usdc_for_position:
        # Step 3: Open new position
        # Pool is USDC/WETH, so amount0=USDC, amount1=WETH
        # In-range positions require BOTH tokens, so provide both
        usdc_amount = min(Decimal("2"), usdc_before - Decimal("0.5"))
        weth_amount = Decimal("0.0005")  # Small WETH amount (sent as native ETH)
        print(f"\nStep 3: Opening position with {usdc_amount} USDC + {weth_amount} WETH, +/- 1% range...")
        open_result = adapter.open_position(
            pool=pool,
            price_range=PriceRange.percent(0.01),
            amount0=usdc_amount,   # USDC (token0)
            amount1=weth_amount,   # WETH (token1), sent as native ETH
        )
        print(f"  Status: {open_result.status}")
        print(f"  TX Hash: {open_result.signature}")
        assert open_result.is_success, f"Open position failed: {open_result.error}"
    else:
        print(f"\nStep 3: SKIPPED open (ETH={eth_before:.6f}, USDC={usdc_before:.6f})")

    # Step 4: Close ALL Uniswap positions
    print("\nStep 4: Closing ALL Uniswap positions...")
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
    eth_after, usdc_after = get_balances(adapter)
    print(f"  ETH:  {eth_after:.6f}")
    print(f"  USDC: {usdc_after:.6f}")

    # Balance differences
    eth_diff = eth_after - eth_before
    usdc_diff = usdc_after - usdc_before

    # Cost Summary
    print("\n" + "=" * 50)
    print("COST SUMMARY (Uniswap)")
    print("=" * 50)
    print("  WALLET BALANCE CHANGES:")
    print(f"    ETH:  {eth_diff:+.9f}")
    print(f"    USDC: {usdc_diff:+.6f}")
    print()
    print("  Note: ETH change includes gas + WETH deposited/withdrawn.")
    print("  Net change close to 0 means positions were fully recovered.")
    print("=" * 50)

    print("\n  Open & Close ALL positions (Uniswap): PASSED")


def main():
    print("=" * 60)
    print("Uniswap LP Test - Open & Close")
    print("=" * 60)
    print()
    print("WARNING: REAL transactions with REAL tokens!")
    print("Chain: Ethereum (Chain ID 1)")
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

    print("Creating UniswapAdapter...")
    adapter = create_adapter()
    print(f"  Wallet: {adapter.address}")
    print()

    try:
        test_open_and_close_position_uniswap(adapter)
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
