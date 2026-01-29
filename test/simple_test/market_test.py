"""
Test script for market pool and price queries across chains.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from test.module_test.conftest import create_client
from dex_adapter_universal.types.pool import RAYDIUM_POOLS, METEORA_POOLS, UNISWAP_POOLS, PANCAKESWAP_POOLS


def print_pool_info(pool):
    """Print pool information in a formatted way."""
    print(f"  Address: {pool.address}")
    print(f"  Symbol: {pool.symbol}")
    print(f"  Price: {pool.price}")
    print(f"  TVL: ${pool.tvl_usd:,.2f}")
    print(f"  Token0: {pool.token0.symbol} ({pool.token0.mint[:8]}...)")
    print(f"  Token1: {pool.token1.symbol} ({pool.token1.mint[:8]}...)")
    print(f"  Fee Rate: {pool.fee_rate}")


def main():
    print("=" * 60)
    print("Market Pool & Price Test - All Pools")
    print("=" * 60)

    # Create DexClient
    client = create_client()

    print(f"\nSolana Address: {client.wallet.address}")

    # ==========================================================================
    # Solana - Raydium CLMM
    # ==========================================================================
    print("\n" + "=" * 60)
    print("Solana - Raydium CLMM")
    print("=" * 60)

    for symbol, address in RAYDIUM_POOLS.items():
        print(f"\n--- {symbol} ---")
        print(f"Pool Address: {address}")
        try:
            pool = client.market.pool(address, dex="raydium")
            print_pool_info(pool)
            if pool.tick_spacing:
                print(f"  Tick Spacing: {pool.tick_spacing}")
            if pool.current_tick:
                print(f"  Current Tick: {pool.current_tick}")
        except Exception as e:
            print(f"  Error: {e}")

    # ==========================================================================
    # Solana - Meteora DLMM
    # ==========================================================================
    print("\n" + "=" * 60)
    print("Solana - Meteora DLMM")
    print("=" * 60)

    for symbol, address in METEORA_POOLS.items():
        print(f"\n--- {symbol} ---")
        print(f"Pool Address: {address}")
        try:
            pool = client.market.pool(address, dex="meteora")
            print_pool_info(pool)
            if pool.bin_step:
                print(f"  Bin Step: {pool.bin_step}")
            if pool.active_bin_id:
                print(f"  Active Bin ID: {pool.active_bin_id}")
        except Exception as e:
            print(f"  Error: {e}")

    # ==========================================================================
    # Ethereum - Uniswap V3
    # ==========================================================================
    print("\n" + "=" * 60)
    print("Ethereum - Uniswap V3")
    print("=" * 60)

    for symbol, address in UNISWAP_POOLS.items():
        print(f"\n--- {symbol} ---")
        print(f"Pool Address: {address}")
        try:
            pool = client.market.pool(address, chain="eth")
            print_pool_info(pool)
        except Exception as e:
            print(f"  Error: {e}")

    # ==========================================================================
    # BSC - PancakeSwap V3
    # ==========================================================================
    print("\n" + "=" * 60)
    print("BSC - PancakeSwap V3")
    print("=" * 60)

    for symbol, address in PANCAKESWAP_POOLS.items():
        print(f"\n--- {symbol} ---")
        print(f"Pool Address: {address}")
        try:
            pool = client.market.pool(address, chain="bsc")
            print_pool_info(pool)
        except Exception as e:
            print(f"  Error: {e}")

    print("\n" + "=" * 60)
    print("Done")
    print("=" * 60)


if __name__ == "__main__":
    main()
