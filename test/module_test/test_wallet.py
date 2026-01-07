"""
Wallet Module Integration Tests

Tests wallet operations with live Solana RPC and real wallet.

WARNING: These tests use REAL RPC connections and REAL wallets!
"""

import sys
from decimal import Decimal
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from conftest import create_client, skip_if_no_config


def test_sol_balance(client):
    """Test getting SOL balance"""
    print("Testing sol_balance...")

    balance = client.wallet.sol_balance()

    assert isinstance(balance, Decimal), f"Expected Decimal, got {type(balance)}"
    assert balance >= 0, f"Balance should be >= 0, got {balance}"

    print(f"  SOL Balance: {balance}")
    print("  sol_balance: PASSED")


def test_sol_balance_lamports(client):
    """Test getting SOL balance in lamports"""
    print("Testing sol_balance_lamports...")

    lamports = client.wallet.sol_balance_lamports()

    assert isinstance(lamports, int), f"Expected int, got {type(lamports)}"
    assert lamports >= 0, f"Lamports should be >= 0, got {lamports}"

    print(f"  SOL Balance (lamports): {lamports}")
    print("  sol_balance_lamports: PASSED")


def test_balance_by_symbol(client):
    """Test getting balance by token symbol"""
    print("Testing balance by symbol...")

    # Test SOL (should work for any wallet)
    sol_balance = client.wallet.balance("SOL")
    assert isinstance(sol_balance, Decimal), f"Expected Decimal, got {type(sol_balance)}"
    print(f"  SOL via symbol: {sol_balance}")

    # Test USDC (may be 0 if wallet doesn't hold USDC)
    usdc_balance = client.wallet.balance("USDC")
    assert isinstance(usdc_balance, Decimal), f"Expected Decimal, got {type(usdc_balance)}"
    print(f"  USDC via symbol: {usdc_balance}")

    print("  balance by symbol: PASSED")


def test_balance_by_mint(client):
    """Test getting balance by mint address"""
    print("Testing balance by mint...")

    # USDC mint address
    usdc_mint = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    balance = client.wallet.balance(usdc_mint)

    assert isinstance(balance, Decimal), f"Expected Decimal, got {type(balance)}"
    print(f"  USDC by mint: {balance}")
    print("  balance by mint: PASSED")


def test_balance_raw(client):
    """Test getting raw balance (smallest units)"""
    print("Testing balance_raw...")

    # Test SOL
    sol_raw = client.wallet.balance_raw("SOL")
    assert isinstance(sol_raw, int), f"Expected int, got {type(sol_raw)}"
    print(f"  SOL raw: {sol_raw}")

    # Test USDC
    usdc_raw = client.wallet.balance_raw("USDC")
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


def test_wallet_address(client):
    """Test wallet address property"""
    print("Testing wallet_address...")

    address = client.wallet.address

    assert isinstance(address, str), f"Expected str, got {type(address)}"
    assert len(address) > 30, f"Address seems too short: {address}"

    print(f"  Wallet address: {address}")
    print("  wallet_address: PASSED")


def main():
    """Run all wallet module tests"""
    print("=" * 60)
    print("Wallet Module Integration Tests")
    print("=" * 60)

    # Check if configuration is available
    skip_msg = skip_if_no_config()
    if skip_msg:
        print(f"\nSKIPPED: {skip_msg}")
        return True  # Not a failure, just skipped

    # Create real client with live RPC and wallet
    print("\nCreating DexClient with real RPC and wallet...")
    client = create_client()
    print(f"  Wallet: {client.wallet.address}")
    print()

    tests = [
        test_sol_balance,
        test_sol_balance_lamports,
        test_balance_by_symbol,
        test_balance_by_mint,
        test_balance_raw,
        test_balances,
        test_token_accounts,
        test_get_token_account,
        test_has_token_account,
        test_wallet_address,
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
