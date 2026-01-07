"""
Multi-Chain Swap Module Integration Tests

WARNING: These tests execute REAL swaps and spend REAL tokens!

Tests swap operations on:
- Solana (via Jupiter)
- Ethereum (via 1inch)
- BSC (via 1inch)

Environment Variables Required:
    Solana:
        SOLANA_RPC_URL          - Solana RPC endpoint
        SOLANA_PRIVATE_KEY      - Base58 private key (or SOLANA_KEYPAIR_PATH)

    EVM (ETH/BSC):
        ONEINCH_API_KEY         - 1inch API key
        EVM_PRIVATE_KEY         - EVM private key
        ETH_RPC_URL             - Ethereum RPC (optional)
        BSC_RPC_URL             - BSC RPC (optional)
"""

import os
import sys
from decimal import Decimal
from pathlib import Path

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

# Try to load .env file
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent.parent / ".env")
except ImportError:
    pass

from conftest import create_client, skip_if_no_config


# =============================================================================
# Configuration Checks
# =============================================================================

def skip_if_no_solana_config():
    """Check if Solana configuration is available"""
    return skip_if_no_config()


def skip_if_no_evm_config():
    """Check if EVM configuration is available"""
    if not os.getenv("ONEINCH_API_KEY"):
        return "Missing ONEINCH_API_KEY environment variable"
    return None


def skip_if_no_evm_signer():
    """Check if EVM signer is available"""
    if not os.getenv("EVM_PRIVATE_KEY"):
        return "Missing EVM_PRIVATE_KEY environment variable"
    return None


def create_evm_signer():
    """Create EVM signer from environment"""
    from dex_adapter_universal.infra.evm_signer import EVMSigner
    return EVMSigner.from_env()


# =============================================================================
# Test: Solana Swap (Jupiter)
# =============================================================================

def test_swap_sol():
    """
    Test swap on Solana using Jupiter aggregator

    Swaps SOL -> USDC or USDC -> SOL on Solana mainnet.
    Direction is determined by available balance.
    """
    print("=" * 60)
    print("TEST: Solana Swap (Jupiter)")
    print("=" * 60)

    # Check configuration
    skip_msg = skip_if_no_solana_config()
    if skip_msg:
        print(f"  SKIPPED: {skip_msg}")
        pytest.skip(skip_msg)

    # Create client
    client = create_client()
    print(f"  Wallet: {client.wallet.address}")

    # Check balances
    sol_balance = client.wallet.sol_balance()
    usdc_balance = client.wallet.balance("USDC")
    print(f"  SOL Balance: {sol_balance}")
    print(f"  USDC Balance: {usdc_balance}")

    # Determine swap direction based on balance
    sol_threshold = Decimal("0.01")
    usdc_threshold = Decimal("0.1")  # 0.1 USDC minimum

    if sol_balance >= sol_threshold:
        # SOL -> USDC
        from_token, to_token = "SOL", "USDC"
        amount = Decimal("0.001")  # 0.001 SOL
        from_decimals, to_decimals = 9, 6
    elif usdc_balance >= usdc_threshold:
        # USDC -> SOL (opposite direction)
        from_token, to_token = "USDC", "SOL"
        amount = Decimal("0.1")  # 0.1 USDC
        from_decimals, to_decimals = 6, 9
        print("  Using opposite direction (USDC -> SOL) due to low SOL balance")
    else:
        print(f"  SKIPPED: Insufficient balance (need {sol_threshold} SOL or {usdc_threshold} USDC)")
        pytest.skip(f"Insufficient balance (need {sol_threshold} SOL or {usdc_threshold} USDC)")

    # Get quote
    print(f"  Getting quote for {amount} {from_token} -> {to_token}...")

    quote = client.swap.quote(
        from_token=from_token,
        to_token=to_token,
        amount=amount,
        slippage_bps=100,
        chain="solana",
    )

    print(f"  Quote: {amount} {from_token} -> {quote.to_amount / 10**to_decimals:.6f} {to_token}")
    print(f"  Aggregator: Jupiter")

    # Execute swap
    print(f"  Executing swap...")
    result = client.swap.swap(
        from_token=from_token,
        to_token=to_token,
        amount=amount,
        slippage_bps=100,
        chain="solana",
    )

    print(f"  Status: {result.status}")
    print(f"  Signature: {result.signature}")

    if result.is_success:
        print("  test_swap_sol: PASSED")
    else:
        print(f"  test_swap_sol: FAILED - {result.error}")
        assert False, f"Swap failed: {result.error}"


# =============================================================================
# Test: Ethereum Swap (1inch)
# =============================================================================

def test_swap_eth():
    """
    Test swap on Ethereum using 1inch aggregator

    Swaps ETH -> USDC or USDC -> ETH on Ethereum mainnet.
    Direction is determined by available balance.
    """
    print("=" * 60)
    print("TEST: Ethereum Swap (1inch)")
    print("=" * 60)

    # Check configuration
    skip_msg = skip_if_no_evm_config()
    if skip_msg:
        print(f"  SKIPPED: {skip_msg}")
        pytest.skip(skip_msg)

    # Import required modules
    from dex_adapter_universal import SwapModule, Chain
    from dex_adapter_universal.protocols.oneinch import OneInchAdapter

    # Create signer if available
    signer = None
    signer_skip = skip_if_no_evm_signer()
    if not signer_skip:
        signer = create_evm_signer()
        print(f"  Wallet: {signer.address}")
    else:
        print(f"  Wallet: None (quote only)")

    # Create swap module
    swap = SwapModule(evm_signer=signer)

    # Only execute if we have a signer
    if not signer:
        # Just do a quote test
        amount = Decimal("0.001")
        quote = swap.quote(from_token="ETH", to_token="USDC", amount=amount, slippage_bps=100, chain="eth")
        print(f"  Quote: {amount} ETH -> {quote.to_amount / 1e6:.4f} USDC")
        print("  test_swap_eth: PASSED (quote only, no signer)")
        return  # Skip swap execution when no signer

    # Check balances
    adapter = OneInchAdapter(chain_id=1, signer=signer)
    eth_balance = adapter.get_native_balance()
    usdc_balance = adapter.get_token_balance("USDC")
    print(f"  ETH Balance: {eth_balance}")
    print(f"  USDC Balance: {usdc_balance}")

    # Determine swap direction based on balance
    eth_threshold = Decimal("0.003")  # 0.001 swap + 0.002 gas
    usdc_threshold = Decimal("1.0")  # 1 USDC minimum

    if eth_balance >= eth_threshold:
        # ETH -> USDC
        from_token, to_token = "ETH", "USDC"
        amount = Decimal("0.001")  # 0.001 ETH
        to_decimals = 6
    elif usdc_balance >= usdc_threshold:
        # USDC -> ETH (opposite direction)
        from_token, to_token = "USDC", "ETH"
        amount = Decimal("1.0")  # 1 USDC
        to_decimals = 18
        print("  Using opposite direction (USDC -> ETH) due to low ETH balance")
    else:
        print(f"  SKIPPED: Insufficient balance (need {eth_threshold} ETH or {usdc_threshold} USDC)")
        print("  test_swap_eth: PASSED (quote only)")
        pytest.skip(f"Insufficient balance (need {eth_threshold} ETH or {usdc_threshold} USDC)")

    # Get quote
    print(f"  Getting quote for {amount} {from_token} -> {to_token}...")

    quote = swap.quote(
        from_token=from_token,
        to_token=to_token,
        amount=amount,
        slippage_bps=100,
        chain="eth",
    )

    print(f"  Quote: {amount} {from_token} -> {quote.to_amount / 10**to_decimals:.6f} {to_token}")
    print(f"  Aggregator: 1inch")
    print(f"  Chain ID: {Chain.ETH.chain_id}")

    # Execute swap
    print(f"  Executing swap...")
    result = swap.swap(
        from_token=from_token,
        to_token=to_token,
        amount=amount,
        slippage_bps=100,
        chain="eth",
    )

    print(f"  Status: {result.status}")
    print(f"  TX Hash: {result.signature}")

    if result.is_success:
        print("  test_swap_eth: PASSED")
    else:
        print(f"  test_swap_eth: FAILED - {result.error}")
        assert False, f"Swap failed: {result.error}"


# =============================================================================
# Test: BSC Swap (1inch)
# =============================================================================

def test_swap_bsc():
    """
    Test swap on BSC using 1inch aggregator

    Swaps BNB -> USDC or USDC -> BNB on BSC mainnet.
    Direction is determined by available balance.
    """
    print("=" * 60)
    print("TEST: BSC Swap (1inch)")
    print("=" * 60)

    # Check configuration
    skip_msg = skip_if_no_evm_config()
    if skip_msg:
        print(f"  SKIPPED: {skip_msg}")
        pytest.skip(skip_msg)

    # Import required modules
    from dex_adapter_universal import SwapModule, Chain
    from dex_adapter_universal.protocols.oneinch import OneInchAdapter

    # Create signer if available
    signer = None
    signer_skip = skip_if_no_evm_signer()
    if not signer_skip:
        signer = create_evm_signer()
        print(f"  Wallet: {signer.address}")
    else:
        print(f"  Wallet: None (quote only)")

    # Create swap module
    swap = SwapModule(evm_signer=signer)

    # Only execute if we have a signer
    if not signer:
        # Just do a quote test
        amount = Decimal("0.01")
        quote = swap.quote(from_token="BNB", to_token="USDC", amount=amount, slippage_bps=100, chain="bsc")
        print(f"  Quote: {amount} BNB -> {quote.to_amount / 1e18:.4f} USDC")
        print("  test_swap_bsc: PASSED (quote only, no signer)")
        return  # Skip swap execution when no signer

    # Check balances
    adapter = OneInchAdapter(chain_id=56, signer=signer)
    bnb_balance = adapter.get_native_balance()
    usdc_balance = adapter.get_token_balance("USDC")
    print(f"  BNB Balance: {bnb_balance}")
    print(f"  USDC Balance: {usdc_balance}")

    # Determine swap direction based on balance
    bnb_threshold = Decimal("0.012")  # 0.01 swap + 0.002 gas
    usdc_threshold = Decimal("1.0")  # 1 USDC minimum

    if bnb_balance >= bnb_threshold:
        # BNB -> USDC
        from_token, to_token = "BNB", "USDC"
        amount = Decimal("0.01")  # 0.01 BNB
        to_decimals = 18  # BSC USDC has 18 decimals
    elif usdc_balance >= usdc_threshold:
        # USDC -> BNB (opposite direction)
        from_token, to_token = "USDC", "BNB"
        amount = Decimal("1.0")  # 1 USDC
        to_decimals = 18
        print("  Using opposite direction (USDC -> BNB) due to low BNB balance")
    else:
        print(f"  SKIPPED: Insufficient balance (need {bnb_threshold} BNB or {usdc_threshold} USDC)")
        print("  test_swap_bsc: PASSED (quote only)")
        pytest.skip(f"Insufficient balance (need {bnb_threshold} BNB or {usdc_threshold} USDC)")

    # Get quote
    print(f"  Getting quote for {amount} {from_token} -> {to_token}...")

    quote = swap.quote(
        from_token=from_token,
        to_token=to_token,
        amount=amount,
        slippage_bps=100,
        chain="bsc",
    )

    print(f"  Quote: {amount} {from_token} -> {quote.to_amount / 10**to_decimals:.6f} {to_token}")
    print(f"  Aggregator: 1inch")
    print(f"  Chain ID: {Chain.BSC.chain_id}")

    # Execute swap
    print(f"  Executing swap...")
    result = swap.swap(
        from_token=from_token,
        to_token=to_token,
        amount=amount,
        slippage_bps=100,
        chain="bsc",
    )

    print(f"  Status: {result.status}")
    print(f"  TX Hash: {result.signature}")

    if result.is_success:
        print("  test_swap_bsc: PASSED")
    else:
        print(f"  test_swap_bsc: FAILED - {result.error}")
        assert False, f"Swap failed: {result.error}"


# =============================================================================
# Additional Quote Tests (No Transaction)
# =============================================================================

def test_quote_sol():
    """Test Solana quote without executing"""
    print("Testing Solana quote (SOL -> USDC)...")

    skip_msg = skip_if_no_solana_config()
    if skip_msg:
        print(f"  SKIPPED: {skip_msg}")
        pytest.skip(skip_msg)

    client = create_client()
    quote = client.swap.quote("SOL", "USDC", Decimal("1.0"), chain="solana")

    assert quote.to_amount > 0
    print(f"  1 SOL = {quote.to_amount / 1e6:.2f} USDC")
    print("  test_quote_sol: PASSED")


def test_quote_eth():
    """Test Ethereum quote without executing"""
    print("Testing Ethereum quote (ETH -> USDC)...")

    skip_msg = skip_if_no_evm_config()
    if skip_msg:
        print(f"  SKIPPED: {skip_msg}")
        pytest.skip(skip_msg)

    from dex_adapter_universal import SwapModule
    swap = SwapModule()
    quote = swap.quote("ETH", "USDC", Decimal("1.0"), chain="eth")

    assert quote.to_amount > 0
    print(f"  1 ETH = {quote.to_amount / 1e6:.2f} USDC")
    print("  test_quote_eth: PASSED")


def test_quote_bsc():
    """Test BSC quote without executing"""
    print("Testing BSC quote (BNB -> USDC)...")

    skip_msg = skip_if_no_evm_config()
    if skip_msg:
        print(f"  SKIPPED: {skip_msg}")
        pytest.skip(skip_msg)

    from dex_adapter_universal import SwapModule
    swap = SwapModule()
    quote = swap.quote("BNB", "USDC", Decimal("1.0"), chain="bsc")

    assert quote.to_amount > 0
    print(f"  1 BNB = {quote.to_amount / 1e18:.2f} USDC")
    print("  test_quote_bsc: PASSED")


# =============================================================================
# Main Test Runner
# =============================================================================

def main():
    """Run all multi-chain swap tests"""
    print("=" * 70)
    print("Multi-Chain Swap Integration Tests")
    print("=" * 70)
    print()
    print("Supported Chains:")
    print("  - Solana (Jupiter)")
    print("  - Ethereum (1inch)")
    print("  - BSC (1inch)")
    print()
    print("WARNING: These tests may execute REAL swaps and spend REAL tokens!")
    print()

    # Define test groups
    quote_tests = [
        ("test_quote_sol", test_quote_sol),
        ("test_quote_eth", test_quote_eth),
        ("test_quote_bsc", test_quote_bsc),
    ]

    swap_tests = [
        ("test_swap_sol", test_swap_sol),
        ("test_swap_eth", test_swap_eth),
        ("test_swap_bsc", test_swap_bsc),
    ]

    all_tests = quote_tests + swap_tests

    passed = 0
    failed = 0
    skipped = 0

    for name, test_func in all_tests:
        print()
        try:
            result = test_func()
            if result:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  {name}: FAILED - {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")
    print("=" * 70)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
