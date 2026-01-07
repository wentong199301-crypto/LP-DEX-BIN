"""
Uniswap V3/V4 Liquidity Module Integration Tests

WARNING: These tests execute REAL LP operations and spend REAL tokens!

Tests Uniswap V3/V4 LP operations with live Ethereum RPC.

Environment Variables Required:
    EVM_PRIVATE_KEY         - EVM private key
    ETHEREUM_RPC_URL        - Ethereum RPC URL (optional, uses default if not set)
"""

import os
import sys
from decimal import Decimal
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

# Try to load .env file
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent.parent / ".env")
except ImportError:
    pass


# Known Uniswap V3 WETH/USDC pool address on Ethereum for testing
# 0.3% fee tier pool (most liquid)
UNISWAP_WETH_USDC_POOL = "0x8ad599c3A0ff1De082011EFDDc58f1908eb6e6D8"

# Minimum balances required for LP tests
MIN_ETH_BALANCE = Decimal("0.02")
MIN_USDC_BALANCE = Decimal("50")


def skip_if_no_config():
    """Check if required config is available, return skip message if not"""
    if not os.getenv("EVM_PRIVATE_KEY"):
        return "Missing EVM_PRIVATE_KEY environment variable"
    try:
        from web3 import Web3
    except ImportError:
        return "web3 not installed. Install with: pip install web3"
    return None


def create_adapter():
    """Create UniswapAdapter with real RPC and wallet"""
    from dex_adapter_universal.protocols.uniswap import UniswapAdapter
    from dex_adapter_universal.infra.evm_signer import EVMSigner

    signer = EVMSigner.from_env()
    return UniswapAdapter(chain_id=1, signer=signer)


def test_list_positions_uniswap(adapter):
    """Test listing Uniswap LP positions"""
    print("Testing list Uniswap positions...")

    # Get V3 positions
    positions = adapter.get_positions(version="v3")

    assert isinstance(positions, list), f"Expected list, got {type(positions)}"
    print(f"  Found {len(positions)} Uniswap V3 positions")

    for pos in positions[:3]:
        print(f"    ID: {pos.id} | {pos.pool.symbol}")
        print(f"      Range: {pos.price_lower:.6f} - {pos.price_upper:.6f}")
        print(f"      Liquidity: {pos.liquidity}")
        print(f"      In Range: {pos.is_in_range}")

    print("  list Uniswap positions: PASSED")


def test_get_pool_uniswap(adapter):
    """Test getting Uniswap V3 pool info"""
    print("Testing get pool (Uniswap V3)...")

    pool = adapter.get_pool_by_address(UNISWAP_WETH_USDC_POOL)

    if pool:
        print(f"  Pool Address: {pool.address}")
        print(f"  Symbol: {pool.symbol}")
        print(f"  Price: {pool.price}")
        print(f"  Fee Rate: {pool.fee_rate}")
        print(f"  Tick Spacing: {pool.tick_spacing}")
        print(f"  Current Tick: {pool.current_tick}")
        print(f"  Version: {pool.metadata.get('version', 'v3')}")
    else:
        # Try getting by tokens
        pool = adapter.get_pool("WETH", "USDC", fee=3000, version="v3")
        if pool:
            print(f"  Pool Address: {pool.address}")
            print(f"  Symbol: {pool.symbol}")
            print(f"  Price: {pool.price}")

    assert pool is not None, "Pool not found"
    print("  get pool (Uniswap V3): PASSED")
    return pool


def test_open_position_uniswap(adapter):
    """Test opening a Uniswap V3 LP position with real transaction"""
    print("Testing open position (Uniswap V3) (REAL TRANSACTION)...")

    # Check balances
    eth_balance = adapter.get_native_balance()
    print(f"  ETH balance: {eth_balance}")

    if eth_balance < MIN_ETH_BALANCE:
        print(f"  SKIPPED: Insufficient ETH balance (need {MIN_ETH_BALANCE})")
        return None

    from dex_adapter_universal.types import PriceRange

    pool = adapter.get_pool("WETH", "USDC", fee=3000, version="v3")
    if not pool:
        pool = adapter.get_pool_by_address(UNISWAP_WETH_USDC_POOL)

    assert pool is not None, "Pool not found"

    print(f"  Pool: {pool.address}")
    print(f"  Current price: {pool.price}")
    print(f"  Tick spacing: {pool.tick_spacing}")

    # Open position with 5% range
    print(f"  Opening position with 0.005 WETH, +/- 5% range...")
    result = adapter.open_position(
        pool=pool,
        price_range=PriceRange.percent(0.05),
        amount0=Decimal("0.005"),
        slippage_bps=100,
    )

    print(f"  Status: {result.status}")
    print(f"  TX Hash: {result.signature}")

    assert result.is_success, f"Open position failed: {result.error}"
    print("  open position (Uniswap V3): PASSED")
    return result


def test_add_liquidity_uniswap(adapter):
    """Test adding liquidity to existing Uniswap position with real transaction"""
    print("Testing add liquidity (Uniswap V3) (REAL TRANSACTION)...")

    # Get existing positions
    positions = adapter.get_positions(version="v3")
    assert len(positions) > 0, "No existing Uniswap positions to add to"

    position = positions[0]
    print(f"  Adding to position: {position.id}")
    print(f"  Pool: {position.pool.symbol}")
    print(f"  Range: {position.price_lower:.6f} - {position.price_upper:.6f}")

    # Check balances
    eth_balance = adapter.get_native_balance()
    print(f"  ETH balance: {eth_balance}")

    result = adapter.add_liquidity(
        position=position,
        amount0=Decimal("0.002"),  # 0.002 WETH
        amount1=Decimal("5"),       # 5 USDC
        slippage_bps=100,
    )

    print(f"  Status: {result.status}")
    print(f"  TX Hash: {result.signature}")

    assert result.is_success, f"Add liquidity failed: {result.error}"
    print("  add liquidity (Uniswap V3): PASSED")


def test_remove_liquidity_partial_uniswap(adapter):
    """Test removing partial liquidity from Uniswap position with real transaction"""
    print("Testing remove liquidity (Uniswap V3) (partial) (REAL TRANSACTION)...")

    # Get existing positions
    positions = adapter.get_positions(version="v3")
    assert len(positions) > 0, "No existing Uniswap positions"

    position = positions[0]
    print(f"  Removing 25% from position: {position.id}")
    print(f"  Current liquidity: {position.liquidity}")

    result = adapter.remove_liquidity(
        position=position,
        percent=25.0,
        slippage_bps=100,
    )

    print(f"  Status: {result.status}")
    print(f"  TX Hash: {result.signature}")

    assert result.is_success, f"Remove liquidity failed: {result.error}"
    print("  remove liquidity (Uniswap V3) (partial): PASSED")


def test_claim_fees_uniswap(adapter):
    """Test claiming fees from Uniswap position with real transaction"""
    print("Testing claim fees (Uniswap V3) (REAL TRANSACTION)...")

    # Get existing positions
    positions = adapter.get_positions(version="v3")
    assert len(positions) > 0, "No existing Uniswap positions"

    position = positions[0]
    print(f"  Claiming fees from position: {position.id}")

    # Show unclaimed fees if available
    if position.unclaimed_fees:
        print(f"  Unclaimed fees: {position.unclaimed_fees}")

    result = adapter.claim_fees(position)

    print(f"  Status: {result.status}")
    print(f"  TX Hash: {result.signature}")

    # May skip if nothing to claim - that's OK
    if not result.is_success:
        if "Nothing to claim" in str(result.error) or result.status.value == "skipped":
            print(f"  No fees to claim (this is OK)")
        else:
            assert result.is_success, f"Claim fees failed: {result.error}"

    print("  claim fees (Uniswap V3): PASSED")


def test_close_position_uniswap(adapter):
    """Test closing a Uniswap LP position with real transaction"""
    print("Testing close position (Uniswap V3) (REAL TRANSACTION)...")

    # Get existing positions
    positions = adapter.get_positions(version="v3")
    assert len(positions) > 0, "No existing Uniswap positions to close"

    position = positions[0]
    print(f"  Closing position: {position.id}")

    result = adapter.close_position(position)

    print(f"  Status: {result.status}")
    print(f"  TX Hash: {result.signature}")

    assert result.is_success, f"Close position failed: {result.error}"
    print("  close position (Uniswap V3): PASSED")


def test_full_lifecycle_uniswap(adapter):
    """Test full Uniswap position lifecycle: open -> add -> remove -> claim -> close"""
    print("Testing full lifecycle (Uniswap V3) (REAL TRANSACTIONS)...")

    # Check balances
    eth_balance = adapter.get_native_balance()
    print(f"  ETH balance: {eth_balance}")

    if eth_balance < MIN_ETH_BALANCE:
        print(f"  SKIPPED: Insufficient ETH balance (need {MIN_ETH_BALANCE})")
        return

    from dex_adapter_universal.types import PriceRange

    pool = adapter.get_pool("WETH", "USDC", fee=3000, version="v3")
    if not pool:
        pool = adapter.get_pool_by_address(UNISWAP_WETH_USDC_POOL)

    assert pool is not None, "Pool not found"

    print(f"  Pool: {pool.address}")
    print(f"  Current price: {pool.price}")

    # Step 1: Open position
    print(f"  Step 1: Opening position...")
    open_result = adapter.open_position(
        pool=pool,
        price_range=PriceRange.percent(0.05),
        amount0=Decimal("0.005"),
        slippage_bps=100,
    )

    assert open_result.is_success, f"Open failed: {open_result.error}"
    print(f"    Opened: {open_result.signature}")

    # Step 2: Get the position and verify fields
    print(f"  Step 2: Fetching position...")
    positions = adapter.get_positions(version="v3")
    assert len(positions) > 0, "Position not found after opening"

    position = positions[0]
    print(f"    Position ID: {position.id}")
    print(f"    Pool: {position.pool.symbol}")
    print(f"    Range: {position.price_lower:.6f} - {position.price_upper:.6f}")
    print(f"    Liquidity: {position.liquidity}")

    # Step 3: Add liquidity
    print(f"  Step 3: Adding liquidity...")
    add_result = adapter.add_liquidity(
        position=position,
        amount0=Decimal("0.002"),
        amount1=Decimal("5"),
        slippage_bps=100,
    )
    print(f"    Add status: {add_result.status}")

    # Step 4: Remove partial liquidity
    print(f"  Step 4: Removing 25% liquidity...")
    # Refresh position
    positions = adapter.get_positions(version="v3")
    position = positions[0]

    remove_result = adapter.remove_liquidity(
        position=position,
        percent=25.0,
        slippage_bps=100,
    )
    print(f"    Remove status: {remove_result.status}")

    # Step 5: Claim fees
    print(f"  Step 5: Claiming fees...")
    positions = adapter.get_positions(version="v3")
    position = positions[0]

    claim_result = adapter.claim_fees(position)
    print(f"    Claim status: {claim_result.status}")

    # Step 6: Close position
    print(f"  Step 6: Closing position...")
    positions = adapter.get_positions(version="v3")
    position = positions[0]

    close_result = adapter.close_position(position)

    print(f"    Closed: {close_result.signature}")
    assert close_result.is_success, f"Close failed: {close_result.error}"

    print("  full lifecycle (Uniswap V3): PASSED")


def main():
    """Run all Uniswap liquidity module tests"""
    print("=" * 60)
    print("Uniswap V3/V4 Liquidity Module Integration Tests")
    print("=" * 60)
    print()
    print("WARNING: These tests execute REAL LP operations and spend REAL tokens!")
    print("Chain: Ethereum (Chain ID 1)")
    print()

    # Check if configuration is available
    skip_msg = skip_if_no_config()
    if skip_msg:
        print(f"\nSKIPPED: {skip_msg}")
        return True  # Not a failure, just skipped

    # Create adapter with real RPC and wallet
    print("Creating UniswapAdapter with real RPC and wallet...")
    adapter = create_adapter()
    print(f"  Wallet: {adapter.address}")
    print(f"  Chain: {adapter.chain_name}")
    print()

    tests = [
        test_list_positions_uniswap,
        test_get_pool_uniswap,
        test_open_position_uniswap,
        test_add_liquidity_uniswap,
        test_remove_liquidity_partial_uniswap,
        test_claim_fees_uniswap,
        test_close_position_uniswap,
        test_full_lifecycle_uniswap,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test(adapter)
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
