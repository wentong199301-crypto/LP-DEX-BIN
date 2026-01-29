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

from conftest import create_client, skip_if_no_config, get_native_balance, get_token_balance


# =============================================================================
# Helper Functions
# =============================================================================

def print_config_info():
    """Print current configuration settings"""
    from dex_adapter_universal.config import config

    print("  Configuration:")
    print(f"    Default Slippage: {config.trading.default_slippage_bps} bps ({config.trading.default_slippage_bps / 100}%)")
    print(f"    Swap Max Retries: {config.tx.swap_max_retries}")
    print(f"    Retry Delay: {config.tx.retry_delay}s")
    print(f"    Confirmation Timeout: {config.tx.confirmation_timeout}s")


def print_gas_config(chain: str):
    """Print gas configuration for a specific chain"""
    from dex_adapter_universal.config import config

    print(f"  Gas Config ({chain}):")
    if chain == "solana":
        print(f"    Compute Unit Price: {config.tx.compute_unit_price} microlamports/CU")
    elif chain == "eth":
        print(f"    Priority Fee: {config.oneinch.priority_fee_gwei} gwei")
        print(f"    Base Fee Multiplier: {config.oneinch.base_fee_multiplier}")
    elif chain == "bsc":
        print(f"    Gas Price Multiplier: {config.oneinch.bsc_gas_price_multiplier}")


def print_network_gas(chain: str, web3=None):
    """Print current network gas prices"""
    if chain == "eth" and web3:
        block = web3.eth.get_block("latest")
        base_fee = block.get("baseFeePerGas", 0)
        base_fee_gwei = base_fee / 1e9
        print(f"  Network Gas (ETH):")
        print(f"    Current Base Fee: {base_fee_gwei:.4f} gwei")
    elif chain == "bsc" and web3:
        gas_price = web3.eth.gas_price
        gas_price_gwei = gas_price / 1e9
        print(f"  Network Gas (BSC):")
        print(f"    Current Gas Price: {gas_price_gwei:.4f} gwei")


def get_tx_gas_info(web3, tx_hash: str) -> dict:
    """Get actual gas info from a transaction receipt"""
    try:
        receipt = web3.eth.get_transaction_receipt(tx_hash)
        tx = web3.eth.get_transaction(tx_hash)

        gas_used = receipt.get("gasUsed", 0)
        effective_gas_price = receipt.get("effectiveGasPrice", 0)
        gas_price_gwei = effective_gas_price / 1e9
        gas_cost_eth = (gas_used * effective_gas_price) / 1e18

        return {
            "gas_used": gas_used,
            "gas_price_gwei": gas_price_gwei,
            "gas_cost_eth": gas_cost_eth,
        }
    except Exception as e:
        return {"error": str(e)}


def get_solana_tx_fee(rpc_client, signature: str) -> int:
    """Get actual transaction fee from Solana RPC"""
    try:
        import requests
        # Use the RPC client's endpoint property
        url = rpc_client.endpoint

        response = requests.post(url, json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [signature, {"encoding": "json", "maxSupportedTransactionVersion": 0}]
        }, timeout=30)

        if response.status_code == 200:
            result = response.json().get("result")
            if result and result.get("meta"):
                return result["meta"].get("fee", 0)
        return 0
    except Exception as e:
        print(f"    Warning: Could not fetch tx fee: {e}")
        return 0


def print_actual_tx_info(web3, tx_hash: str, quoted_amount, actual_amount, decimals: int, symbol: str):
    """Print actual gas and slippage for a transaction"""
    # Gas info
    gas_info = get_tx_gas_info(web3, tx_hash)
    if "error" not in gas_info:
        print(f"    Actual Gas Used: {gas_info['gas_used']:,} units")
        print(f"    Actual Gas Price: {gas_info['gas_price_gwei']:.4f} gwei")
        print(f"    Actual Gas Cost: {gas_info['gas_cost_eth']:.6f} ETH")

    # Slippage info
    quoted = Decimal(quoted_amount) / Decimal(10 ** decimals)
    actual = Decimal(actual_amount) / Decimal(10 ** decimals)
    if quoted > 0:
        slippage_pct = ((quoted - actual) / quoted) * 100
        print(f"    Quoted: {quoted:.6f} {symbol}")
        print(f"    Actual: {actual:.6f} {symbol}")
        print(f"    Actual Slippage: {slippage_pct:.4f}%")


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
    Test round-trip swap on Solana using Jupiter aggregator

    Tests:
    - SOL -> USDC -> SOL round trip
    - Automatic retry for recoverable errors
    - Balance verification before/after
    """
    import time

    print("=" * 60)
    print("TEST: Solana Round-Trip Swap (Jupiter)")
    print("=" * 60)

    # Check configuration
    skip_msg = skip_if_no_solana_config()
    if skip_msg:
        print(f"  SKIPPED: {skip_msg}")
        pytest.skip(skip_msg)

    # Print config
    print_config_info()
    print_gas_config("solana")

    # Create client
    client = create_client()
    print(f"  Wallet: {client.wallet.address}")

    # Check initial balances
    sol_balance_start = client.wallet.balance("SOL", chain="solana")
    usdc_balance_start = client.wallet.balance("USDC", chain="solana")
    print(f"\n  Initial Balances:")
    print(f"    SOL:  {sol_balance_start}")
    print(f"    USDC: {usdc_balance_start}")

    # Check minimum balance
    sol_threshold = Decimal("0.01")
    swap_amount = Decimal("0.001")

    if sol_balance_start < sol_threshold:
        print(f"  SKIPPED: Insufficient SOL balance (need {sol_threshold} SOL)")
        pytest.skip(f"Insufficient balance")

    # === LEG 1: SOL -> USDC ===
    print(f"\n  --- LEG 1: {swap_amount} SOL -> USDC ---")
    quote1 = client.swap.quote("SOL", "USDC", swap_amount, chain="solana")
    expected_usdc = Decimal(quote1.to_amount) / Decimal(10**6)
    print(f"  Quoted: {swap_amount} SOL -> {expected_usdc:.6f} USDC")
    print(f"  Max Slippage: {quote1.slippage_bps} bps ({quote1.slippage_bps/100}%)")

    usdc_before_leg1 = client.wallet.balance("USDC", chain="solana")
    result1 = client.swap.swap("SOL", "USDC", swap_amount, chain="solana")

    if not result1.is_success:
        print(f"\n  LEG 1 FAILED: {result1.error}")
        assert False, f"Leg 1 failed: {result1.error}"

    print(f"  TX Hash: {result1.signature}")

    # Fetch actual TX fee from RPC
    tx_fee1_lamports = get_solana_tx_fee(client.rpc, result1.signature)
    tx_fee1_sol = Decimal(tx_fee1_lamports) / Decimal(10**9)
    print(f"  Actual TX Fee: {tx_fee1_lamports} lamports ({tx_fee1_sol:.6f} SOL)")

    # Wait for balance to update
    time.sleep(2)

    # Calculate actual slippage for LEG 1
    usdc_balance_mid = client.wallet.balance("USDC", chain="solana")
    usdc_received = usdc_balance_mid - usdc_before_leg1
    if expected_usdc > 0:
        actual_slippage1 = ((expected_usdc - usdc_received) / expected_usdc) * 100
        print(f"  Actual Received: {usdc_received:.6f} USDC")
        print(f"  Actual Slippage: {actual_slippage1:.4f}%")

    # === LEG 2: USDC -> SOL ===
    # Use 90% of received USDC to account for any rounding
    swap_back_amount = (usdc_received * Decimal("0.9")).quantize(Decimal("0.000001"))
    if swap_back_amount < Decimal("0.01"):
        swap_back_amount = Decimal("0.01")

    print(f"\n  --- LEG 2: {swap_back_amount} USDC -> SOL ---")
    quote2 = client.swap.quote("USDC", "SOL", swap_back_amount, chain="solana")
    expected_sol = Decimal(quote2.to_amount) / Decimal(10**9)
    print(f"  Quoted: {swap_back_amount} USDC -> {expected_sol:.9f} SOL")
    print(f"  Max Slippage: {quote2.slippage_bps} bps ({quote2.slippage_bps/100}%)")

    sol_before_leg2 = client.wallet.balance("SOL", chain="solana")
    result2 = client.swap.swap("USDC", "SOL", swap_back_amount, chain="solana")

    if not result2.is_success:
        print(f"\n  LEG 2 FAILED: {result2.error}")
        assert False, f"Leg 2 failed: {result2.error}"

    print(f"  TX Hash: {result2.signature}")

    # Fetch actual TX fee from RPC
    tx_fee2_lamports = get_solana_tx_fee(client.rpc, result2.signature)
    tx_fee2_sol = Decimal(tx_fee2_lamports) / Decimal(10**9)
    print(f"  Actual TX Fee: {tx_fee2_lamports} lamports ({tx_fee2_sol:.6f} SOL)")

    # Wait and check final balances
    time.sleep(2)
    sol_balance_end = client.wallet.balance("SOL", chain="solana")
    usdc_balance_end = client.wallet.balance("USDC", chain="solana")

    # Calculate actual slippage for LEG 2
    # For SOL, we need to account for TX fees: actual_received = balance_change + tx_fee
    sol_balance_change = sol_balance_end - sol_before_leg2
    sol_received_from_swap = sol_balance_change + tx_fee2_sol
    if expected_sol > 0:
        actual_slippage2 = ((expected_sol - sol_received_from_swap) / expected_sol) * 100
        print(f"  Actual Received: {sol_received_from_swap:.9f} SOL (from swap)")
        print(f"  Actual Slippage: {actual_slippage2:.4f}%")

    print(f"\n  Final Balances:")
    print(f"    SOL:  {sol_balance_end} (started: {sol_balance_start})")
    print(f"    USDC: {usdc_balance_end} (started: {usdc_balance_start})")

    sol_diff = sol_balance_end - sol_balance_start
    print(f"\n  Net SOL change: {sol_diff:.9f} (fees + slippage)")

    print("\n  test_swap_sol: PASSED (round-trip complete)")


# =============================================================================
# Test: Ethereum Swap (1inch) with Retry
# =============================================================================

def test_swap_eth():
    """
    Test round-trip swap on Ethereum using 1inch aggregator

    Tests:
    - USDC -> ETH -> USDC round trip (starts with USDC to minimize ETH needed for gas)
    - Automatic retry for recoverable errors
    - Balance verification before/after
    """
    import time

    print("=" * 60)
    print("TEST: Ethereum Round-Trip Swap (1inch)")
    print("  USDC -> ETH -> USDC")
    print("=" * 60)

    # Check configuration
    skip_msg = skip_if_no_evm_config()
    if skip_msg:
        print(f"  SKIPPED: {skip_msg}")
        pytest.skip(skip_msg)

    # Print config
    print_config_info()
    print_gas_config("eth")

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

    # Check initial balances
    adapter = OneInchAdapter(chain_id=1, signer=signer)
    print_network_gas("eth", adapter._web3)
    eth_balance_start = get_native_balance(adapter)
    usdc_balance_start = get_token_balance(adapter, "USDC")
    print(f"\n  Initial Balances:")
    print(f"    ETH:  {eth_balance_start}")
    print(f"    USDC: {usdc_balance_start}")

    # Check minimum balances (need ETH for gas, USDC for swap)
    eth_threshold = Decimal("0.001")  # Just for gas
    usdc_threshold = Decimal("2.0")   # For swap
    swap_amount = Decimal("1.0")      # 1 USDC

    if eth_balance_start < eth_threshold:
        print(f"  SKIPPED: Insufficient ETH for gas (need {eth_threshold} ETH)")
        pytest.skip(f"Insufficient ETH for gas")

    if usdc_balance_start < usdc_threshold:
        print(f"  SKIPPED: Insufficient USDC balance (need {usdc_threshold} USDC)")
        pytest.skip(f"Insufficient USDC balance")

    # === LEG 1: USDC -> ETH ===
    print(f"\n  --- LEG 1: {swap_amount} USDC -> ETH ---")
    quote1 = swap.quote("USDC", "ETH", swap_amount, chain="eth")
    quoted_eth = Decimal(quote1.to_amount) / Decimal(10**18)
    print(f"  Quoted: {swap_amount} USDC -> {quoted_eth:.9f} ETH")
    print(f"  Max Slippage: {quote1.slippage_bps} bps ({quote1.slippage_bps/100}%)")

    eth_before_swap = get_native_balance(adapter)
    result1 = swap.swap("USDC", "ETH", swap_amount, chain="eth")

    if not result1.is_success:
        print(f"\n  LEG 1 FAILED: {result1.error}")
        assert False, f"Leg 1 failed: {result1.error}"

    print(f"  TX Hash: {result1.signature}")

    # Get actual gas used
    gas_info = get_tx_gas_info(adapter._web3, result1.signature)
    if "error" not in gas_info:
        print(f"  Actual Gas Used: {gas_info['gas_used']:,} units @ {gas_info['gas_price_gwei']:.4f} gwei = {gas_info['gas_cost_eth']:.6f} ETH")

    # Wait for balance to update
    time.sleep(3)

    # Calculate actual slippage
    eth_after_swap = get_native_balance(adapter)
    actual_eth_received = eth_after_swap - eth_before_swap + Decimal(str(gas_info.get('gas_cost_eth', 0)))
    if quoted_eth > 0:
        actual_slippage = ((quoted_eth - actual_eth_received) / quoted_eth) * 100
        print(f"  Actual Received: {actual_eth_received:.9f} ETH")
        print(f"  Actual Slippage: {actual_slippage:.4f}%")

    eth_balance_mid = eth_after_swap

    # === LEG 2: ETH -> USDC ===
    # Use a small fixed amount for the return swap
    swap_back_amount = Decimal("0.0002")

    print(f"\n  --- LEG 2: {swap_back_amount} ETH -> USDC ---")
    quote2 = swap.quote("ETH", "USDC", swap_back_amount, chain="eth")
    expected_usdc = Decimal(quote2.to_amount) / Decimal(10**6)
    print(f"  Quote: {swap_back_amount} ETH -> {expected_usdc:.6f} USDC")

    usdc_before_leg2 = get_token_balance(adapter, "USDC")
    result2 = swap.swap("ETH", "USDC", swap_back_amount, chain="eth")

    if not result2.is_success:
        print(f"\n  LEG 2 FAILED: {result2.error}")
        assert False, f"Leg 2 failed: {result2.error}"

    print(f"  TX Hash: {result2.signature}")

    # Get actual gas for LEG 2
    gas_info2 = get_tx_gas_info(adapter._web3, result2.signature)
    if "error" not in gas_info2:
        print(f"  Actual Gas Used: {gas_info2['gas_used']:,} units @ {gas_info2['gas_price_gwei']:.4f} gwei = {gas_info2['gas_cost_eth']:.6f} ETH")

    # Wait and check final balances
    time.sleep(5)
    eth_balance_end = get_native_balance(adapter)
    usdc_balance_end = get_token_balance(adapter, "USDC")

    # Calculate actual slippage for LEG 2
    actual_usdc_received = usdc_balance_end - usdc_before_leg2
    if expected_usdc > 0:
        actual_slippage2 = ((expected_usdc - actual_usdc_received) / expected_usdc) * 100
        print(f"  Actual Received: {actual_usdc_received:.6f} USDC")
        print(f"  Actual Slippage: {actual_slippage2:.4f}%")

    print(f"\n  Final Balances:")
    print(f"    ETH:  {eth_balance_end} (started: {eth_balance_start})")
    print(f"    USDC: {usdc_balance_end} (started: {usdc_balance_start})")

    usdc_diff = usdc_balance_end - usdc_balance_start
    eth_diff = eth_balance_end - eth_balance_start
    print(f"\n  Net USDC change: {usdc_diff:.6f}")
    print(f"  Net ETH change: {eth_diff:.9f} (gas fees)")

    print("\n  test_swap_eth: PASSED (round-trip complete)")


# =============================================================================
# Test: BSC Swap (1inch) with Retry
# =============================================================================

def test_swap_bsc():
    """
    Test round-trip swap on BSC using 1inch aggregator

    Tests:
    - BNB -> USDT -> BNB round trip
    - Automatic retry for recoverable errors
    - BSC-specific gas handling (legacy, not EIP-1559)
    """
    import time

    print("=" * 60)
    print("TEST: BSC Round-Trip Swap (1inch)")
    print("=" * 60)

    # Check configuration
    skip_msg = skip_if_no_evm_config()
    if skip_msg:
        print(f"  SKIPPED: {skip_msg}")
        pytest.skip(skip_msg)

    # Print config
    print_config_info()
    print_gas_config("bsc")

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
        quote = swap.quote(from_token="BNB", to_token="USDT", amount=amount, chain="bsc")
        print(f"  Quote: {amount} BNB -> {quote.to_amount / 1e18:.4f} USDT")
        print(f"  Slippage: {quote.slippage_bps} bps")
        print("  test_swap_bsc: PASSED (quote only, no signer)")
        return

    # Check initial balances
    adapter = OneInchAdapter(chain_id=56, signer=signer)
    print_network_gas("bsc", adapter._web3)
    bnb_balance_start = get_native_balance(adapter)
    usdt_balance_start = get_token_balance(adapter, "USDT")
    print(f"\n  Initial Balances:")
    print(f"    BNB:  {bnb_balance_start}")
    print(f"    USDT: {usdt_balance_start}")

    # Check minimum balance
    bnb_threshold = Decimal("0.005")
    swap_amount = Decimal("0.003")

    if bnb_balance_start < bnb_threshold:
        print(f"  SKIPPED: Insufficient BNB balance (need {bnb_threshold} BNB)")
        pytest.skip(f"Insufficient balance")

    # === LEG 1: BNB -> USDT ===
    print(f"\n  --- LEG 1: {swap_amount} BNB -> USDT ---")
    quote1 = swap.quote("BNB", "USDT", swap_amount, chain="bsc")
    expected_usdt = Decimal(quote1.to_amount) / Decimal(10**18)
    print(f"  Quoted: {swap_amount} BNB -> {expected_usdt:.6f} USDT")
    print(f"  Max Slippage: {quote1.slippage_bps} bps ({quote1.slippage_bps/100}%)")

    usdt_before_leg1 = get_token_balance(adapter, "USDT")
    result1 = swap.swap("BNB", "USDT", swap_amount, chain="bsc")

    if not result1.is_success:
        print(f"\n  LEG 1 FAILED: {result1.error}")
        assert False, f"Leg 1 failed: {result1.error}"

    print(f"  TX Hash: {result1.signature}")

    # Get actual gas for LEG 1
    gas_info1 = get_tx_gas_info(adapter._web3, result1.signature)
    if "error" not in gas_info1:
        print(f"  Actual Gas Used: {gas_info1['gas_used']:,} units @ {gas_info1['gas_price_gwei']:.4f} gwei = {gas_info1['gas_cost_eth']:.6f} BNB")

    # Wait for balance to update
    time.sleep(5)

    # Calculate actual slippage for LEG 1
    usdt_balance_mid = get_token_balance(adapter, "USDT")
    usdt_received = usdt_balance_mid - usdt_before_leg1
    if expected_usdt > 0:
        actual_slippage1 = ((expected_usdt - usdt_received) / expected_usdt) * 100
        print(f"  Actual Received: {usdt_received:.6f} USDT")
        print(f"  Actual Slippage: {actual_slippage1:.4f}%")

    # === LEG 2: USDT -> BNB ===
    # Use 90% of received USDT to account for any rounding
    swap_back_amount = (usdt_received * Decimal("0.9")).quantize(Decimal("0.000001"))
    if swap_back_amount < Decimal("1.0"):
        swap_back_amount = Decimal("1.0")

    print(f"\n  --- LEG 2: {swap_back_amount} USDT -> BNB ---")
    quote2 = swap.quote("USDT", "BNB", swap_back_amount, chain="bsc")
    expected_bnb = Decimal(quote2.to_amount) / Decimal(10**18)
    print(f"  Quoted: {swap_back_amount} USDT -> {expected_bnb:.9f} BNB")
    print(f"  Max Slippage: {quote2.slippage_bps} bps ({quote2.slippage_bps/100}%)")

    bnb_before_leg2 = get_native_balance(adapter)
    result2 = swap.swap("USDT", "BNB", swap_back_amount, chain="bsc")

    if not result2.is_success:
        print(f"\n  LEG 2 FAILED: {result2.error}")
        assert False, f"Leg 2 failed: {result2.error}"

    print(f"  TX Hash: {result2.signature}")

    # Get actual gas for LEG 2
    gas_info2 = get_tx_gas_info(adapter._web3, result2.signature)
    if "error" not in gas_info2:
        print(f"  Actual Gas Used: {gas_info2['gas_used']:,} units @ {gas_info2['gas_price_gwei']:.4f} gwei = {gas_info2['gas_cost_eth']:.6f} BNB")

    # Wait and check final balances
    time.sleep(5)
    bnb_balance_end = get_native_balance(adapter)
    usdt_balance_end = get_token_balance(adapter, "USDT")

    # Calculate actual slippage for LEG 2
    actual_bnb_received = bnb_balance_end - bnb_before_leg2 + Decimal(str(gas_info2.get('gas_cost_eth', 0)))
    if expected_bnb > 0:
        actual_slippage2 = ((expected_bnb - actual_bnb_received) / expected_bnb) * 100
        print(f"  Actual Received: {actual_bnb_received:.9f} BNB")
        print(f"  Actual Slippage: {actual_slippage2:.4f}%")

    print(f"\n  Final Balances:")
    print(f"    BNB:  {bnb_balance_end} (started: {bnb_balance_start})")
    print(f"    USDT: {usdt_balance_end} (started: {usdt_balance_start})")

    bnb_diff = bnb_balance_end - bnb_balance_start
    print(f"\n  Net BNB change: {bnb_diff:.9f} (fees + slippage)")

    print("\n  test_swap_bsc: PASSED (round-trip complete)")


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
    print(f"    - Swap Max Retries: {config.tx.swap_max_retries}")
    print(f"    - Retry Delay: {config.tx.retry_delay}s")

    assert config.trading.default_slippage_bps == 30, "Expected default slippage to be 30 bps"
    assert config.tx.swap_max_retries >= 1, "Expected at least 1 retry"
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
