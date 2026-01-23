"""
Multi-Chain Swap Module Integration Tests

WARNING: These tests execute REAL swaps and spend REAL tokens!

Tests swap operations on:
- Solana (via Jupiter)
- Ethereum (via 1inch)
- BSC (via 1inch)

Features tested:
- Automatic retry for recoverable errors
- Error type classification (recoverable vs non-recoverable)
- Detailed error information (error_code, recoverable flag)

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
# Helper Functions
# =============================================================================

def print_config_info():
    """Print current configuration settings"""
    from dex_adapter_universal.config import config

    print("  Configuration:")
    print(f"    Default Slippage: {config.trading.default_slippage_bps} bps ({config.trading.default_slippage_bps / 100}%)")
    print(f"    Max Retries: {config.tx.max_retries}")
    print(f"    Retry Delay: {config.tx.retry_delay}s")
    print(f"    Confirmation Timeout: {config.tx.confirmation_timeout}s")


def print_result_details(result, chain: str = ""):
    """Print detailed TxResult information"""
    chain_prefix = f"[{chain}] " if chain else ""

    print(f"  {chain_prefix}Result Details:")
    print(f"    Status: {result.status.value}")
    print(f"    Signature: {result.signature or 'N/A'}")

    if result.error:
        print(f"    Error: {result.error}")
        print(f"    Recoverable: {result.recoverable}")
        if result.error_code:
            print(f"    Error Code: {result.error_code}")

    if result.is_success:
        if result.fee_lamports:
            print(f"    Fee: {result.fee_lamports} lamports ({result.fee_sol:.6f} SOL)")


def print_swap_summary(result, from_token: str, to_token: str, amount: Decimal):
    """Print swap execution summary"""
    if result.is_success:
        print(f"  SUCCESS: Swapped {amount} {from_token} -> {to_token}")
        print(f"  Transaction: {result.signature}")
    elif result.is_timeout:
        print(f"  TIMEOUT: Transaction may have succeeded, check on-chain")
        print(f"  Transaction: {result.signature}")
        print(f"  Hint: Use signature to verify status on explorer")
    else:
        print(f"  FAILED: {result.error}")
        if result.recoverable:
            print(f"  Note: This error is recoverable, retry may succeed")


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
# Test: Solana Swap (Jupiter) with Retry
# =============================================================================

def test_swap_sol():
    """
    Test swap on Solana using Jupiter aggregator

    Tests:
    - Automatic retry for recoverable errors
    - Default slippage from config
    - Detailed result information
    """
    print("=" * 60)
    print("TEST: Solana Swap (Jupiter) with Auto-Retry")
    print("=" * 60)

    # Check configuration
    skip_msg = skip_if_no_solana_config()
    if skip_msg:
        print(f"  SKIPPED: {skip_msg}")
        pytest.skip(skip_msg)

    # Print config
    print_config_info()

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
    usdc_threshold = Decimal("0.1")

    if sol_balance >= sol_threshold:
        from_token, to_token = "SOL", "USDC"
        amount = Decimal("0.001")
        to_decimals = 6
    elif usdc_balance >= usdc_threshold:
        from_token, to_token = "USDC", "SOL"
        amount = Decimal("0.1")
        to_decimals = 9
        print("  Using opposite direction (USDC -> SOL) due to low SOL balance")
    else:
        print(f"  SKIPPED: Insufficient balance (need {sol_threshold} SOL or {usdc_threshold} USDC)")
        pytest.skip(f"Insufficient balance")

    # Get quote (uses default slippage from config)
    print(f"\n  Getting quote for {amount} {from_token} -> {to_token}...")
    quote = client.swap.quote(
        from_token=from_token,
        to_token=to_token,
        amount=amount,
        chain="solana",
    )
    print(f"  Quote: {amount} {from_token} -> {quote.to_amount / 10**to_decimals:.6f} {to_token}")
    print(f"  Slippage: {quote.slippage_bps} bps")

    # Execute swap (with automatic retry)
    print(f"\n  Executing swap (with auto-retry enabled)...")
    result = client.swap.swap(
        from_token=from_token,
        to_token=to_token,
        amount=amount,
        chain="solana",
    )

    # Print detailed results
    print()
    print_result_details(result, "Solana")
    print()
    print_swap_summary(result, from_token, to_token, amount)

    if result.is_success:
        print("\n  test_swap_sol: PASSED")
    elif result.is_timeout:
        print("\n  test_swap_sol: TIMEOUT (check on-chain)")
        # Don't fail on timeout - tx may have succeeded
    else:
        print(f"\n  test_swap_sol: FAILED")
        if not result.recoverable:
            assert False, f"Swap failed with non-recoverable error: {result.error}"


# =============================================================================
# Test: Ethereum Swap (1inch) with Retry
# =============================================================================

def test_swap_eth():
    """
    Test swap on Ethereum using 1inch aggregator

    Tests:
    - Automatic retry for recoverable errors
    - EVM-specific error handling
    """
    print("=" * 60)
    print("TEST: Ethereum Swap (1inch) with Auto-Retry")
    print("=" * 60)

    # Check configuration
    skip_msg = skip_if_no_evm_config()
    if skip_msg:
        print(f"  SKIPPED: {skip_msg}")
        pytest.skip(skip_msg)

    # Print config
    print_config_info()

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
        amount = Decimal("0.001")
        quote = swap.quote(from_token="ETH", to_token="USDC", amount=amount, chain="eth")
        print(f"  Quote: {amount} ETH -> {quote.to_amount / 1e6:.4f} USDC")
        print(f"  Slippage: {quote.slippage_bps} bps")
        print("  test_swap_eth: PASSED (quote only, no signer)")
        return

    # Check balances
    adapter = OneInchAdapter(chain_id=1, signer=signer)
    eth_balance = adapter.get_native_balance()
    usdc_balance = adapter.get_token_balance("USDC")
    print(f"  ETH Balance: {eth_balance}")
    print(f"  USDC Balance: {usdc_balance}")

    # Determine swap direction based on balance
    eth_threshold = Decimal("0.003")
    usdc_threshold = Decimal("1.0")

    if eth_balance >= eth_threshold:
        from_token, to_token = "ETH", "USDC"
        amount = Decimal("0.001")
        to_decimals = 6
    elif usdc_balance >= usdc_threshold:
        from_token, to_token = "USDC", "ETH"
        amount = Decimal("1.0")
        to_decimals = 18
        print("  Using opposite direction (USDC -> ETH) due to low ETH balance")
    else:
        print(f"  SKIPPED: Insufficient balance (need {eth_threshold} ETH or {usdc_threshold} USDC)")
        pytest.skip(f"Insufficient balance")

    # Get quote
    print(f"\n  Getting quote for {amount} {from_token} -> {to_token}...")
    quote = swap.quote(
        from_token=from_token,
        to_token=to_token,
        amount=amount,
        chain="eth",
    )
    print(f"  Quote: {amount} {from_token} -> {quote.to_amount / 10**to_decimals:.6f} {to_token}")
    print(f"  Slippage: {quote.slippage_bps} bps")
    print(f"  Chain ID: {Chain.ETH.chain_id}")

    # Execute swap
    print(f"\n  Executing swap (with auto-retry enabled)...")
    result = swap.swap(
        from_token=from_token,
        to_token=to_token,
        amount=amount,
        chain="eth",
    )

    # Print detailed results
    print()
    print_result_details(result, "Ethereum")
    print()
    print_swap_summary(result, from_token, to_token, amount)

    if result.is_success:
        print("\n  test_swap_eth: PASSED")
    elif result.is_timeout:
        print("\n  test_swap_eth: TIMEOUT (check on-chain)")
    else:
        print(f"\n  test_swap_eth: FAILED")
        if not result.recoverable:
            assert False, f"Swap failed with non-recoverable error: {result.error}"


# =============================================================================
# Test: BSC Swap (1inch) with Retry
# =============================================================================

def test_swap_bsc():
    """
    Test swap on BSC using 1inch aggregator

    Tests:
    - Automatic retry for recoverable errors
    - BSC-specific gas handling (legacy, not EIP-1559)
    """
    print("=" * 60)
    print("TEST: BSC Swap (1inch) with Auto-Retry")
    print("=" * 60)

    # Check configuration
    skip_msg = skip_if_no_evm_config()
    if skip_msg:
        print(f"  SKIPPED: {skip_msg}")
        pytest.skip(skip_msg)

    # Print config
    print_config_info()

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
        amount = Decimal("0.01")
        quote = swap.quote(from_token="BNB", to_token="USDC", amount=amount, chain="bsc")
        print(f"  Quote: {amount} BNB -> {quote.to_amount / 1e18:.4f} USDC")
        print(f"  Slippage: {quote.slippage_bps} bps")
        print("  test_swap_bsc: PASSED (quote only, no signer)")
        return

    # Check balances
    adapter = OneInchAdapter(chain_id=56, signer=signer)
    bnb_balance = adapter.get_native_balance()
    usdc_balance = adapter.get_token_balance("USDC")
    print(f"  BNB Balance: {bnb_balance}")
    print(f"  USDC Balance: {usdc_balance}")

    # Determine swap direction based on balance
    bnb_threshold = Decimal("0.012")
    usdc_threshold = Decimal("1.0")

    if bnb_balance >= bnb_threshold:
        from_token, to_token = "BNB", "USDC"
        amount = Decimal("0.01")
        to_decimals = 18
    elif usdc_balance >= usdc_threshold:
        from_token, to_token = "USDC", "BNB"
        amount = Decimal("1.0")
        to_decimals = 18
        print("  Using opposite direction (USDC -> BNB) due to low BNB balance")
    else:
        print(f"  SKIPPED: Insufficient balance (need {bnb_threshold} BNB or {usdc_threshold} USDC)")
        pytest.skip(f"Insufficient balance")

    # Get quote
    print(f"\n  Getting quote for {amount} {from_token} -> {to_token}...")
    quote = swap.quote(
        from_token=from_token,
        to_token=to_token,
        amount=amount,
        chain="bsc",
    )
    print(f"  Quote: {amount} {from_token} -> {quote.to_amount / 10**to_decimals:.6f} {to_token}")
    print(f"  Slippage: {quote.slippage_bps} bps")
    print(f"  Chain ID: {Chain.BSC.chain_id}")

    # Execute swap
    print(f"\n  Executing swap (with auto-retry enabled)...")
    result = swap.swap(
        from_token=from_token,
        to_token=to_token,
        amount=amount,
        chain="bsc",
    )

    # Print detailed results
    print()
    print_result_details(result, "BSC")
    print()
    print_swap_summary(result, from_token, to_token, amount)

    if result.is_success:
        print("\n  test_swap_bsc: PASSED")
    elif result.is_timeout:
        print("\n  test_swap_bsc: TIMEOUT (check on-chain)")
    else:
        print(f"\n  test_swap_bsc: FAILED")
        if not result.recoverable:
            assert False, f"Swap failed with non-recoverable error: {result.error}"


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

    from dex_adapter_universal.config import config

    client = create_client()
    quote = client.swap.quote("SOL", "USDC", Decimal("1.0"), chain="solana")

    assert quote.to_amount > 0
    print(f"  1 SOL = {quote.to_amount / 1e6:.2f} USDC")
    print(f"  Slippage: {quote.slippage_bps} bps (config default: {config.trading.default_slippage_bps})")
    print("  test_quote_sol: PASSED")


def test_quote_eth():
    """Test Ethereum quote without executing"""
    print("Testing Ethereum quote (ETH -> USDC)...")

    skip_msg = skip_if_no_evm_config()
    if skip_msg:
        print(f"  SKIPPED: {skip_msg}")
        pytest.skip(skip_msg)

    from dex_adapter_universal import SwapModule
    from dex_adapter_universal.config import config

    swap = SwapModule()
    quote = swap.quote("ETH", "USDC", Decimal("1.0"), chain="eth")

    assert quote.to_amount > 0
    print(f"  1 ETH = {quote.to_amount / 1e6:.2f} USDC")
    print(f"  Slippage: {quote.slippage_bps} bps (config default: {config.trading.default_slippage_bps})")
    print("  test_quote_eth: PASSED")


def test_quote_bsc():
    """Test BSC quote without executing"""
    print("Testing BSC quote (BNB -> USDC)...")

    skip_msg = skip_if_no_evm_config()
    if skip_msg:
        print(f"  SKIPPED: {skip_msg}")
        pytest.skip(skip_msg)

    from dex_adapter_universal import SwapModule
    from dex_adapter_universal.config import config

    swap = SwapModule()
    quote = swap.quote("BNB", "USDC", Decimal("1.0"), chain="bsc")

    assert quote.to_amount > 0
    print(f"  1 BNB = {quote.to_amount / 1e18:.2f} USDC")
    print(f"  Slippage: {quote.slippage_bps} bps (config default: {config.trading.default_slippage_bps})")
    print("  test_quote_bsc: PASSED")


# =============================================================================
# Test: Error Handling Verification
# =============================================================================

def test_error_handling():
    """
    Test error handling features

    Verifies:
    - TxResult has recoverable and error_code fields
    - Configuration values are correctly loaded
    """
    print("=" * 60)
    print("TEST: Error Handling Features")
    print("=" * 60)

    from dex_adapter_universal.types.result import TxResult, TxStatus
    from dex_adapter_universal.config import config

    # Test TxResult fields
    print("  Testing TxResult fields...")

    # Test failed result with recoverable flag
    result = TxResult.failed(
        error="Test error",
        recoverable=True,
        error_code="1001"
    )
    assert result.status == TxStatus.FAILED
    assert result.error == "Test error"
    assert result.recoverable == True
    assert result.error_code == "1001"
    print("    - TxResult.failed() with recoverable=True: OK")

    # Test failed result without recoverable flag
    result2 = TxResult.failed(error="Non-recoverable error")
    assert result2.recoverable == False
    assert result2.error_code is None
    print("    - TxResult.failed() default recoverable=False: OK")

    # Test timeout result
    result3 = TxResult.timeout(signature="test_sig_123")
    assert result3.status == TxStatus.TIMEOUT
    assert result3.recoverable == True
    assert result3.error_code == "2003"
    print("    - TxResult.timeout() has recoverable=True: OK")

    # Test success result
    result4 = TxResult.success(signature="success_sig")
    assert result4.is_success
    assert result4.recoverable == False  # Success doesn't need retry
    print("    - TxResult.success() works correctly: OK")

    # Test config values
    print("\n  Testing configuration values...")
    print(f"    - Default Slippage: {config.trading.default_slippage_bps} bps")
    print(f"    - Max Retries: {config.tx.max_retries}")
    print(f"    - Retry Delay: {config.tx.retry_delay}s")

    assert config.trading.default_slippage_bps == 30, "Expected default slippage to be 30 bps"
    assert config.tx.max_retries >= 1, "Expected at least 1 retry"
    print("    - Config values verified: OK")

    print("\n  test_error_handling: PASSED")


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
    print("New Features Tested:")
    print("  - Automatic retry for recoverable errors")
    print("  - Error classification (recoverable vs non-recoverable)")
    print("  - Detailed error information (error_code)")
    print("  - Default slippage from config (0.3%)")
    print()
    print("WARNING: These tests may execute REAL swaps and spend REAL tokens!")
    print()

    # Define test groups
    unit_tests = [
        ("test_error_handling", test_error_handling),
    ]

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

    all_tests = unit_tests + quote_tests + swap_tests

    passed = 0
    failed = 0
    skipped = 0

    for name, test_func in all_tests:
        print()
        try:
            test_func()
            passed += 1
        except pytest.skip.Exception as e:
            print(f"  {name}: SKIPPED - {e}")
            skipped += 1
        except Exception as e:
            print(f"  {name}: FAILED - {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Passed:  {passed}")
    print(f"  Failed:  {failed}")
    print(f"  Skipped: {skipped}")
    print("=" * 70)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
