"""
Wallet Module Integration Tests

Tests wallet operations with live RPC connections and real wallets.

Supports:
- Solana: SOL and SPL tokens
- Ethereum: ETH and ERC20 tokens (requires ETH_RPC_URL, EVM_PRIVATE_KEY)
- BSC: BNB and BEP20 tokens (requires BSC_RPC_URL, EVM_PRIVATE_KEY)

WARNING: These tests use REAL RPC connections and REAL wallets!
"""

import os
import sys
from decimal import Decimal
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from conftest import create_client, skip_if_no_config, skip_if_no_evm_config
from dex_adapter_universal.types.evm_tokens import ETH_TOKEN_ADDRESSES, BSC_TOKEN_ADDRESSES
from dex_adapter_universal.types.solana_tokens import SOLANA_TOKEN_MINTS


# =============================================================================
# Helper Functions
# =============================================================================

def get_evm_address() -> str:
    """Get EVM wallet address from private key"""
    try:
        from dex_adapter_universal.infra.evm_signer import EVMSigner
        signer = EVMSigner.from_env()
        return signer.address
    except Exception as e:
        raise EnvironmentError(f"Cannot get EVM address: {e}")


def skip_if_no_eth_config():
    """Check if ETH config is available"""
    base_skip = skip_if_no_evm_config()
    if base_skip:
        return base_skip
    if not os.getenv("ETH_RPC_URL"):
        return "Missing ETH_RPC_URL environment variable"
    return None


def skip_if_no_bsc_config():
    """Check if BSC config is available"""
    base_skip = skip_if_no_evm_config()
    if base_skip:
        return base_skip
    if not os.getenv("BSC_RPC_URL"):
        return "Missing BSC_RPC_URL environment variable"
    return None


# =============================================================================
# Solana Tests
# =============================================================================

def test_balance_by_symbol(client):
    """Test getting balance by token symbol"""
    print("Testing balance by symbol...")

    # Test SOL (should work for any wallet)
    sol_balance = client.wallet.balance("SOL", chain="sol")
    assert isinstance(sol_balance, Decimal), f"Expected Decimal, got {type(sol_balance)}"
    print(f"  SOL via symbol: {sol_balance}")

    # Test with solana alias
    sol_balance2 = client.wallet.balance("SOL", chain="solana")
    assert sol_balance == sol_balance2, "balance(chain='sol') should equal balance(chain='solana')"
    print(f"  SOL via symbol (chain='solana'): {sol_balance2}")

    # Test USDC (may be 0 if wallet doesn't hold USDC)
    usdc_balance = client.wallet.balance("USDC", chain="sol")
    assert isinstance(usdc_balance, Decimal), f"Expected Decimal, got {type(usdc_balance)}"
    print(f"  USDC via symbol: {usdc_balance}")

    print("  balance by symbol: PASSED")


def test_balance_by_mint(client):
    """Test getting balance by mint address"""
    print("Testing balance by mint...")

    # USDC mint address
    usdc_mint = SOLANA_TOKEN_MINTS["USDC"]
    balance = client.wallet.balance(usdc_mint, chain="sol")

    assert isinstance(balance, Decimal), f"Expected Decimal, got {type(balance)}"
    print(f"  USDC by mint: {balance}")
    print("  balance by mint: PASSED")


def test_balance_raw(client):
    """Test getting raw balance (smallest units)"""
    print("Testing balance_raw...")

    # Test SOL
    sol_raw = client.wallet.balance_raw("SOL", chain="sol")
    assert isinstance(sol_raw, int), f"Expected int, got {type(sol_raw)}"
    print(f"  SOL raw: {sol_raw}")

    # Test USDC
    usdc_raw = client.wallet.balance_raw("USDC", chain="sol")
    assert isinstance(usdc_raw, int), f"Expected int, got {type(usdc_raw)}"
    print(f"  USDC raw: {usdc_raw}")

    print("  balance_raw: PASSED")


def test_balances(client):
    """Test getting all balances"""
    print("Testing balances...")

    balances = client.wallet.balances()

    assert isinstance(balances, dict), f"Expected dict, got {type(balances)}"
    print(f"  Found {len(balances)} token balances")

    for mint, balance in list(balances.items())[:5]:
        print(f"    {mint[:16]}...: {balance}")

    print("  balances: PASSED")


def test_token_accounts(client):
    """Test listing token accounts"""
    print("Testing token_accounts...")

    accounts = client.wallet.token_accounts()

    assert isinstance(accounts, list), f"Expected list, got {type(accounts)}"
    print(f"  Found {len(accounts)} token accounts")

    for acc in accounts[:3]:
        print(f"    {acc.mint[:16]}...: {acc.balance}")

    print("  token_accounts: PASSED")


def test_get_token_account(client):
    """Test getting specific token account"""
    print("Testing get_token_account...")

    # Try to get USDC token account (may not exist)
    account = client.wallet.get_token_account("USDC")

    if account:
        print(f"  USDC token account: {account[:16]}...")
    else:
        print(f"  No USDC token account found (this is OK)")

    print("  get_token_account: PASSED")


def test_has_token_account(client):
    """Test checking if token account exists"""
    print("Testing has_token_account...")

    # Check for WSOL (wrapped SOL)
    has_wsol = client.wallet.has_token_account("WSOL")
    print(f"  Has WSOL account: {has_wsol}")

    # Check for USDC
    has_usdc = client.wallet.has_token_account("USDC")
    print(f"  Has USDC account: {has_usdc}")

    print("  has_token_account: PASSED")


def test_usd1_balance_solana(client):
    """Test getting USD1 balance on Solana"""
    print("Testing USD1 balance (Solana)...")

    # Test USD1 by symbol
    usd1_balance = client.wallet.balance("USD1", chain="sol")
    assert isinstance(usd1_balance, Decimal), f"Expected Decimal, got {type(usd1_balance)}"
    assert usd1_balance >= 0, f"Balance should be >= 0, got {usd1_balance}"
    print(f"  USD1 Balance: {usd1_balance}")

    # Test USD1 by mint address
    usd1_mint = SOLANA_TOKEN_MINTS["USD1"]
    usd1_by_mint = client.wallet.balance(usd1_mint, chain="sol")
    assert isinstance(usd1_by_mint, Decimal), f"Expected Decimal, got {type(usd1_by_mint)}"
    assert usd1_balance == usd1_by_mint, "Balance by symbol should equal balance by mint"
    print(f"  USD1 by mint: {usd1_by_mint}")

    print("  USD1 balance (Solana): PASSED")


def test_usd1_token_account(client):
    """Test checking USD1 token account on Solana"""
    print("Testing USD1 token account...")

    # Check if USD1 token account exists
    has_usd1 = client.wallet.has_token_account("USD1")
    print(f"  Has USD1 account: {has_usd1}")

    # Try to get USD1 token account address
    account = client.wallet.get_token_account("USD1")
    if account:
        print(f"  USD1 token account: {account[:16]}...")
    else:
        print(f"  No USD1 token account found (this is OK)")

    print("  USD1 token account: PASSED")


def test_wallet_address(client):
    """Test wallet address property"""
    print("Testing wallet_address...")

    address = client.wallet.address

    assert isinstance(address, str), f"Expected str, got {type(address)}"
    assert len(address) > 30, f"Address seems too short: {address}"

    print(f"  Wallet address: {address}")
    print("  wallet_address: PASSED")


def test_get_address_solana(client):
    """Test get_address for Solana chain"""
    print("Testing get_address (Solana)...")

    address = client.wallet.get_address(chain="sol")
    address_solana = client.wallet.get_address(chain="solana")

    assert address == address_solana, "get_address(chain='sol') should equal get_address(chain='solana')"
    assert address == client.wallet.address, "get_address(chain='sol') should equal .address"

    print(f"  Solana address: {address}")
    print("  get_address (Solana): PASSED")


# =============================================================================
# Ethereum Tests
# =============================================================================

def test_eth_balance(client):
    """Test getting ETH balance on Ethereum"""
    print("Testing ETH balance...")

    evm_address = get_evm_address()
    client.wallet.set_evm_address(evm_address)

    balance = client.wallet.balance("ETH", chain="eth")

    assert isinstance(balance, Decimal), f"Expected Decimal, got {type(balance)}"
    assert balance >= 0, f"Balance should be >= 0, got {balance}"

    print(f"  EVM Address: {evm_address}")
    print(f"  ETH Balance: {balance}")
    print("  ETH balance: PASSED")


def test_eth_balance_raw(client):
    """Test getting ETH balance in wei"""
    print("Testing ETH balance_raw...")

    evm_address = get_evm_address()
    client.wallet.set_evm_address(evm_address)

    balance_wei = client.wallet.balance_raw("ETH", chain="eth")

    assert isinstance(balance_wei, int), f"Expected int, got {type(balance_wei)}"
    assert balance_wei >= 0, f"Balance should be >= 0, got {balance_wei}"

    print(f"  ETH Balance (wei): {balance_wei}")
    print("  ETH balance_raw: PASSED")


def test_eth_usdc_balance(client):
    """Test getting USDC balance on Ethereum"""
    print("Testing USDC balance on ETH...")

    evm_address = get_evm_address()
    client.wallet.set_evm_address(evm_address)

    balance = client.wallet.balance("USDC", chain="eth")

    assert isinstance(balance, Decimal), f"Expected Decimal, got {type(balance)}"
    assert balance >= 0, f"Balance should be >= 0, got {balance}"

    print(f"  USDC Balance (ETH): {balance}")
    print("  USDC balance (ETH): PASSED")


def test_eth_token_by_address(client):
    """Test getting token balance by contract address on Ethereum"""
    print("Testing token by address on ETH...")

    evm_address = get_evm_address()
    client.wallet.set_evm_address(evm_address)

    # USDC contract address on Ethereum
    usdc_address = ETH_TOKEN_ADDRESSES["USDC"]
    balance = client.wallet.balance(usdc_address, chain="eth")

    assert isinstance(balance, Decimal), f"Expected Decimal, got {type(balance)}"
    print(f"  USDC by address: {balance}")
    print("  token by address (ETH): PASSED")


def test_get_address_eth(client):
    """Test get_address for Ethereum chain"""
    print("Testing get_address (ETH)...")

    evm_address = get_evm_address()
    client.wallet.set_evm_address(evm_address)

    address = client.wallet.get_address(chain="eth")

    assert address == evm_address, f"Expected {evm_address}, got {address}"
    print(f"  ETH address: {address}")
    print("  get_address (ETH): PASSED")


def test_eth_usd1_balance(client):
    """Test getting USD1 balance on Ethereum"""
    print("Testing USD1 balance on ETH...")

    evm_address = get_evm_address()
    client.wallet.set_evm_address(evm_address)

    # Test USD1 by symbol
    balance = client.wallet.balance("USD1", chain="eth")
    assert isinstance(balance, Decimal), f"Expected Decimal, got {type(balance)}"
    assert balance >= 0, f"Balance should be >= 0, got {balance}"
    print(f"  USD1 Balance (ETH): {balance}")

    # Test USD1 by contract address
    usd1_address = ETH_TOKEN_ADDRESSES["USD1"]
    balance_by_addr = client.wallet.balance(usd1_address, chain="eth")
    assert isinstance(balance_by_addr, Decimal), f"Expected Decimal, got {type(balance_by_addr)}"
    assert balance == balance_by_addr, "Balance by symbol should equal balance by address"
    print(f"  USD1 by address: {balance_by_addr}")

    print("  USD1 balance (ETH): PASSED")


# =============================================================================
# BSC Tests
# =============================================================================

def test_bnb_balance(client):
    """Test getting BNB balance on BSC"""
    print("Testing BNB balance...")

    evm_address = get_evm_address()
    client.wallet.set_evm_address(evm_address)

    balance = client.wallet.balance("BNB", chain="bsc")

    assert isinstance(balance, Decimal), f"Expected Decimal, got {type(balance)}"
    assert balance >= 0, f"Balance should be >= 0, got {balance}"

    print(f"  EVM Address: {evm_address}")
    print(f"  BNB Balance: {balance}")
    print("  BNB balance: PASSED")


def test_bnb_balance_raw(client):
    """Test getting BNB balance in wei"""
    print("Testing BNB balance_raw...")

    evm_address = get_evm_address()
    client.wallet.set_evm_address(evm_address)

    balance_wei = client.wallet.balance_raw("BNB", chain="bsc")

    assert isinstance(balance_wei, int), f"Expected int, got {type(balance_wei)}"
    assert balance_wei >= 0, f"Balance should be >= 0, got {balance_wei}"

    print(f"  BNB Balance (wei): {balance_wei}")
    print("  BNB balance_raw: PASSED")


def test_bsc_usdc_balance(client):
    """Test getting USDC balance on BSC"""
    print("Testing USDC balance on BSC...")

    evm_address = get_evm_address()
    client.wallet.set_evm_address(evm_address)

    balance = client.wallet.balance("USDC", chain="bsc")

    assert isinstance(balance, Decimal), f"Expected Decimal, got {type(balance)}"
    assert balance >= 0, f"Balance should be >= 0, got {balance}"

    print(f"  USDC Balance (BSC): {balance}")
    print("  USDC balance (BSC): PASSED")


def test_bsc_token_by_address(client):
    """Test getting token balance by contract address on BSC"""
    print("Testing token by address on BSC...")

    evm_address = get_evm_address()
    client.wallet.set_evm_address(evm_address)

    # USDC contract address on BSC
    usdc_address = BSC_TOKEN_ADDRESSES["USDC"]
    balance = client.wallet.balance(usdc_address, chain="bsc")

    assert isinstance(balance, Decimal), f"Expected Decimal, got {type(balance)}"
    print(f"  USDC by address: {balance}")
    print("  token by address (BSC): PASSED")


def test_get_address_bsc(client):
    """Test get_address for BSC chain"""
    print("Testing get_address (BSC)...")

    evm_address = get_evm_address()
    client.wallet.set_evm_address(evm_address)

    address = client.wallet.get_address(chain="bsc")

    assert address == evm_address, f"Expected {evm_address}, got {address}"
    print(f"  BSC address: {address}")
    print("  get_address (BSC): PASSED")


def test_bsc_usd1_balance(client):
    """Test getting USD1 balance on BSC"""
    print("Testing USD1 balance on BSC...")

    evm_address = get_evm_address()
    client.wallet.set_evm_address(evm_address)

    # Test USD1 by symbol
    balance = client.wallet.balance("USD1", chain="bsc")
    assert isinstance(balance, Decimal), f"Expected Decimal, got {type(balance)}"
    assert balance >= 0, f"Balance should be >= 0, got {balance}"
    print(f"  USD1 Balance (BSC): {balance}")

    # Test USD1 by contract address
    usd1_address = BSC_TOKEN_ADDRESSES["USD1"]
    balance_by_addr = client.wallet.balance(usd1_address, chain="bsc")
    assert isinstance(balance_by_addr, Decimal), f"Expected Decimal, got {type(balance_by_addr)}"
    assert balance == balance_by_addr, "Balance by symbol should equal balance by address"
    print(f"  USD1 by address: {balance_by_addr}")

    print("  USD1 balance (BSC): PASSED")


# =============================================================================
# Main Test Runner
# =============================================================================

def main():
    """Run all wallet module tests"""
    print("=" * 60)
    print("Wallet Module Integration Tests")
    print("=" * 60)

    # -------------------------------------------------------------------------
    # Solana Tests
    # -------------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("SOLANA TESTS")
    print("=" * 60)

    skip_msg = skip_if_no_config()
    if skip_msg:
        print(f"\nSKIPPED: {skip_msg}")
        solana_passed = 0
        solana_failed = 0
    else:
        print("\nCreating DexClient with real RPC and wallet...")
        client = create_client()
        print(f"  Wallet: {client.wallet.address}")
        print()

        solana_tests = [
            test_balance_by_symbol,
            test_balance_by_mint,
            test_balance_raw,
            test_balances,
            test_token_accounts,
            test_get_token_account,
            test_has_token_account,
            test_usd1_balance_solana,
            test_usd1_token_account,
            test_wallet_address,
            test_get_address_solana,
        ]

        solana_passed = 0
        solana_failed = 0

        for test in solana_tests:
            try:
                test(client)
                solana_passed += 1
            except Exception as e:
                print(f"  FAILED: {e}")
                import traceback
                traceback.print_exc()
                solana_failed += 1

    # -------------------------------------------------------------------------
    # Ethereum Tests
    # -------------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("ETHEREUM TESTS")
    print("=" * 60)

    eth_skip_msg = skip_if_no_eth_config()
    if eth_skip_msg:
        print(f"\nSKIPPED: {eth_skip_msg}")
        eth_passed = 0
        eth_failed = 0
    else:
        if 'client' not in locals():
            client = create_client()
        print(f"\n  EVM Address: {get_evm_address()}")
        print()

        eth_tests = [
            test_eth_balance,
            test_eth_balance_raw,
            test_eth_usdc_balance,
            test_eth_usd1_balance,
            test_eth_token_by_address,
            test_get_address_eth,
        ]

        eth_passed = 0
        eth_failed = 0

        for test in eth_tests:
            try:
                test(client)
                eth_passed += 1
            except Exception as e:
                print(f"  FAILED: {e}")
                import traceback
                traceback.print_exc()
                eth_failed += 1

    # -------------------------------------------------------------------------
    # BSC Tests
    # -------------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("BSC TESTS")
    print("=" * 60)

    bsc_skip_msg = skip_if_no_bsc_config()
    if bsc_skip_msg:
        print(f"\nSKIPPED: {bsc_skip_msg}")
        bsc_passed = 0
        bsc_failed = 0
    else:
        if 'client' not in locals():
            client = create_client()
        print(f"\n  EVM Address: {get_evm_address()}")
        print()

        bsc_tests = [
            test_bnb_balance,
            test_bnb_balance_raw,
            test_bsc_usdc_balance,
            test_bsc_usd1_balance,
            test_bsc_token_by_address,
            test_get_address_bsc,
        ]

        bsc_passed = 0
        bsc_failed = 0

        for test in bsc_tests:
            try:
                test(client)
                bsc_passed += 1
            except Exception as e:
                print(f"  FAILED: {e}")
                import traceback
                traceback.print_exc()
                bsc_failed += 1

    # -------------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    total_passed = solana_passed + eth_passed + bsc_passed
    total_failed = solana_failed + eth_failed + bsc_failed

    print(f"\n  Solana:   {solana_passed} passed, {solana_failed} failed")
    print(f"  Ethereum: {eth_passed} passed, {eth_failed} failed")
    print(f"  BSC:      {bsc_passed} passed, {bsc_failed} failed")
    print(f"\n  TOTAL:    {total_passed} passed, {total_failed} failed")
    print("=" * 60)

    return total_failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
