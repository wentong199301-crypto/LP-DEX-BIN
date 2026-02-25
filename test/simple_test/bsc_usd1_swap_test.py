"""
BSC USD1 -> USDT Swap Test

WARNING: This executes REAL transactions and spends REAL tokens!
Chain: BSC (Chain ID 56)
"""

import sys
import os
import time
from decimal import Decimal
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(project_root / ".env")
except ImportError:
    pass

# Set default ONEINCH_BASE_URL if not set
if not os.getenv("ONEINCH_BASE_URL"):
    os.environ["ONEINCH_BASE_URL"] = "https://api.1inch.dev/swap/v6.0"

from dex_adapter_universal.modules.swap import SwapModule
from dex_adapter_universal.infra.evm_signer import EVMSigner, create_web3
from dex_adapter_universal.types.evm_tokens import BSC_TOKEN_ADDRESSES, BSC_TOKEN_DECIMALS
from dex_adapter_universal.config import config

# Update config if base_url is empty
if not config.oneinch.base_url:
    config.oneinch.base_url = "https://api.1inch.dev/swap/v6.0"


def get_token_balance(web3, address: str, token_address: str, decimals: int) -> Decimal:
    """Get token balance"""
    if token_address.lower() == "native":
        # Native BNB balance
        balance_raw = web3.eth.get_balance(address)
        return Decimal(balance_raw) / Decimal(10 ** 18)
    
    # ERC20 token balance
    erc20_abi = [{
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    }]
    
    contract = web3.eth.contract(
        address=web3.to_checksum_address(token_address),
        abi=erc20_abi
    )
    balance_raw = contract.functions.balanceOf(web3.to_checksum_address(address)).call()
    return Decimal(balance_raw) / Decimal(10 ** decimals)


def main():
    print("=" * 60)
    print("BSC USD1 -> USDT Swap Test")
    print("=" * 60)
    print()
    print("WARNING: REAL transactions with REAL tokens!")
    print("Chain: BSC (Chain ID 56)")
    print()

    # Check EVM config
    import os
    if not os.getenv("EVM_PRIVATE_KEY"):
        print("\nERROR: Missing EVM_PRIVATE_KEY environment variable")
        return False

    if not os.getenv("ONEINCH_API_KEY"):
        print("\nERROR: Missing ONEINCH_API_KEY environment variable")
        return False

    try:
        from web3 import Web3
    except ImportError:
        print("\nERROR: web3 not installed")
        return False

    # Create signer
    print("Creating EVMSigner...")
    signer = EVMSigner.from_env()
    wallet_address = signer.address
    print(f"  Wallet: {wallet_address}")
    print()

    # Create swap module
    print("Creating SwapModule...")
    swap = SwapModule(evm_signer=signer)
    print()

    # Create web3 for balance checking
    bsc_rpc = os.getenv("BSC_RPC_URL", "https://bsc-dataseed1.binance.org/")
    web3 = create_web3(bsc_rpc, chain_id=56)

    # Token addresses
    USD1_ADDRESS = BSC_TOKEN_ADDRESSES["USD1"]
    USDT_ADDRESS = BSC_TOKEN_ADDRESSES["USDT"]
    USD1_DECIMALS = BSC_TOKEN_DECIMALS["USD1"]
    USDT_DECIMALS = BSC_TOKEN_DECIMALS["USDT"]

    print(f"Token Addresses:")
    print(f"  USD1: {USD1_ADDRESS}")
    print(f"  USDT: {USDT_ADDRESS}")
    print()

    # Check initial balances
    print("--- WALLET BALANCES (BEFORE) ---")
    bnb_balance = get_token_balance(web3, wallet_address, "native", 18)
    usd1_balance = get_token_balance(web3, wallet_address, USD1_ADDRESS, USD1_DECIMALS)
    usdt_balance = get_token_balance(web3, wallet_address, USDT_ADDRESS, USDT_DECIMALS)
    
    print(f"  BNB:  {bnb_balance:.6f}")
    print(f"  USD1: {usd1_balance:.6f}")
    print(f"  USDT: {usdt_balance:.6f}")
    print()

    # Check if we have enough USD1
    swap_amount = Decimal("2.0")  # 2 USD1
    if usd1_balance < swap_amount:
        print(f"ERROR: Insufficient USD1 balance. Have {usd1_balance}, need {swap_amount}")
        return False

    # Check if we have BNB for gas
    if bnb_balance < Decimal("0.001"):
        print(f"WARNING: Low BNB balance ({bnb_balance:.6f}). May not have enough for gas fees.")
        print("  Continuing anyway...")
        print()

    # Get quote
    print(f"Step 1: Getting quote for {swap_amount} USD1 -> USDT...")
    try:
        quote = swap.quote(
            from_token="USD1",
            to_token="USDT",
            amount=swap_amount,
            chain="bsc"
        )
        
        expected_usdt = Decimal(quote.to_amount) / Decimal(10 ** USDT_DECIMALS)
        print(f"  Quoted: {swap_amount} USD1 -> {expected_usdt:.6f} USDT")
        print(f"  Slippage: {quote.slippage_bps} bps ({quote.slippage_bps / 100}%)")
        if hasattr(quote, 'price_impact_percent'):
            print(f"  Price Impact: {quote.price_impact_percent:.4f}%")
        print()
    except Exception as e:
        print(f"  ERROR: Failed to get quote: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Execute swap
    print(f"Step 2: Executing swap: {swap_amount} USD1 -> USDT...")
    try:
        result = swap.swap(
            from_token="USD1",
            to_token="USDT",
            amount=swap_amount,
            chain="bsc",
            wait_confirmation=True
        )

        print(f"  Status: {result.status.value}")
        print(f"  TX Hash: {result.signature}")
        
        if result.error:
            print(f"  Error: {result.error}")
            if result.recoverable:
                print(f"  Recoverable: {result.recoverable}")
            if result.error_code:
                print(f"  Error Code: {result.error_code}")
        
        if not result.is_success:
            print(f"\nFAILED: Swap failed: {result.error}")
            return False
        
        print()
    except Exception as e:
        print(f"  ERROR: Swap execution failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Wait a bit for balances to update
    print("Waiting for balances to update...")
    time.sleep(5)

    # Check final balances
    print("\n--- WALLET BALANCES (AFTER) ---")
    bnb_balance_after = get_token_balance(web3, wallet_address, "native", 18)
    usd1_balance_after = get_token_balance(web3, wallet_address, USD1_ADDRESS, USD1_DECIMALS)
    usdt_balance_after = get_token_balance(web3, wallet_address, USDT_ADDRESS, USDT_DECIMALS)
    
    print(f"  BNB:  {bnb_balance_after:.6f} (change: {bnb_balance_after - bnb_balance:+.6f})")
    print(f"  USD1: {usd1_balance_after:.6f} (change: {usd1_balance_after - usd1_balance:+.6f})")
    print(f"  USDT: {usdt_balance_after:.6f} (change: {usdt_balance_after - usdt_balance:+.6f})")
    print()

    # Calculate actual received
    usdt_received = usdt_balance_after - usdt_balance
    if expected_usdt > 0:
        actual_slippage = ((expected_usdt - usdt_received) / expected_usdt) * 100
        print(f"  Expected: {expected_usdt:.6f} USDT")
        print(f"  Actual Received: {usdt_received:.6f} USDT")
        print(f"  Actual Slippage: {actual_slippage:.4f}%")
        print()

    # Summary
    print("=" * 60)
    print("SWAP SUMMARY")
    print("=" * 60)
    print(f"  Swapped: {swap_amount} USD1 -> {usdt_received:.6f} USDT")
    print(f"  Transaction: {result.signature}")
    print(f"  BNB Spent (gas): {bnb_balance - bnb_balance_after:.6f} BNB")
    print("=" * 60)
    print()
    print("Swap test: PASSED")
    
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

