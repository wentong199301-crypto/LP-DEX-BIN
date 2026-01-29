"""
Test script for wallet balance queries across chains.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from test.module_test.conftest import create_client
from dex_adapter_universal.infra.evm_signer import EVMSigner


def main():
    print("=" * 60)
    print("Wallet Balance Test")
    print("=" * 60)

    # Create DexClient
    client = create_client()

    print(f"\nSolana Address: {client.wallet.address}")

    # Test 1: SOL balance on Solana
    print("\n--- Test 1: SOL balance on Solana ---")
    sol_sol_balance = client.wallet.balance("SOL", chain="sol")
    print(f"SOL on sol Balance: {sol_sol_balance}")

    usd1_sol_balance = client.wallet.balance("USD1", chain="sol")
    print(f"USD1 on sol Balance: {usd1_sol_balance}")

    # Test 2: USDC balance on BSC
    # Get EVM address from private key
    evm_signer = EVMSigner.from_env()
    client.wallet.set_evm_address(evm_signer.address)

    usdc_eth_balance = client.wallet.balance("USDT", chain="bsc")
    print(f"USDT Balance (bsc): {usdc_eth_balance}")

    # Test 3: ETH and USDC balance on Ethereum
    print("\n--- Test 3: ETH and USDC balance on Ethereum ---")
    eth_balance = client.wallet.balance("ETH", chain="eth")
    print(f"ETH Balance (eth): {eth_balance}")

    usdc_eth_balance = client.wallet.balance("USDC", chain="eth")
    print(f"USDC Balance (eth): {usdc_eth_balance}")

    print("\n" + "=" * 60)
    print("Done")
    print("=" * 60)


if __name__ == "__main__":
    main()
