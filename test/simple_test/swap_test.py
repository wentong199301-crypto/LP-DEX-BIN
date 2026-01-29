"""
Test script for round-trip swap operations across chains.

WARNING: These tests execute REAL swaps and spend REAL tokens!

Runs round-trip swaps (swap and swap back):
- test_swap_sol: SOL -> USDC -> SOL (Solana via Jupiter)
- test_swap_eth: ETH -> USDC -> ETH (Ethereum via 1inch)
- test_swap_bsc: BNB -> USDT -> BNB (BSC via 1inch)
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(project_root / ".env")
except ImportError:
    pass

# Import swap tests
from test.module_test.test_swap import (
    test_swap_sol,
    test_swap_eth,
    test_swap_bsc,
)


def main():
    print("=" * 70)
    print("Round-Trip Swap Integration Tests")
    print("=" * 70)
    print()
    print("WARNING: These tests execute REAL swaps and spend REAL tokens!")
    print()
    print("Round-trip swaps:")
    print("  - Solana: SOL -> USDC -> SOL (Jupiter)")
    print("  - Ethereum: USDC -> ETH -> USDC (1inch)")
    print("  - BSC: BNB -> USDT -> BNB (1inch)")
    print()

    swap_tests = [
        # ("test_swap_sol", test_swap_sol),
        ("test_swap_eth", test_swap_eth),
        # ("test_swap_bsc", test_swap_bsc),
    ]

    passed = 0
    failed = 0
    skipped = 0

    import pytest

    for name, test_func in swap_tests:
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
