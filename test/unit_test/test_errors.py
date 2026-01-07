"""
Test Errors Module

Tests for dex_adapter_universal.errors package.
"""

import sys
from decimal import Decimal
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_error_code():
    """Test ErrorCode enum"""
    from dex_adapter_universal.errors import ErrorCode

    print("Testing ErrorCode...")

    # Check codes exist
    assert ErrorCode.RPC_CONNECTION_FAILED.value == "1001"
    assert ErrorCode.SLIPPAGE_EXCEEDED.value == "3001"
    assert ErrorCode.POSITION_NOT_FOUND.value == "5001"

    print("  ErrorCode: PASSED")


def test_dex_adapter_error():
    """Test DexAdapterError base class"""
    from dex_adapter_universal.errors import DexAdapterError, ErrorCode

    print("Testing DexAdapterError...")

    error = DexAdapterError(
        message="Test error",
        code=ErrorCode.RPC_CONNECTION_FAILED,
        recoverable=True,
    )

    # __str__ returns "[code] message" format
    assert "[1001] Test error" == str(error)
    assert error.code == ErrorCode.RPC_CONNECTION_FAILED
    assert error.recoverable == True

    print("  DexAdapterError: PASSED")


def test_rpc_error():
    """Test RpcError exception"""
    from dex_adapter_universal.errors import RpcError, ErrorCode

    print("Testing RpcError...")

    # Connection failed
    error1 = RpcError.connection_failed("https://rpc.example.com")
    assert error1.code == ErrorCode.RPC_CONNECTION_FAILED
    assert error1.recoverable == True
    assert error1.endpoint == "https://rpc.example.com"

    # Timeout
    error2 = RpcError.timeout("https://rpc.example.com", 30.0)
    assert error2.code == ErrorCode.RPC_TIMEOUT
    assert error2.recoverable == True

    # Rate limited
    error3 = RpcError.rate_limited("https://rpc.example.com")
    assert error3.code == ErrorCode.RPC_RATE_LIMITED
    assert error3.recoverable == True

    print("  RpcError: PASSED")


def test_slippage_exceeded():
    """Test SlippageExceeded exception"""
    from dex_adapter_universal.errors import SlippageExceeded

    print("Testing SlippageExceeded...")

    error = SlippageExceeded(
        message="Slippage too high",
        expected=Decimal("100"),
        actual=Decimal("95"),
    )

    assert error.recoverable == True
    assert error.expected == Decimal("100")
    assert error.actual == Decimal("95")

    print("  SlippageExceeded: PASSED")


def test_pool_unavailable():
    """Test PoolUnavailable exception"""
    from dex_adapter_universal.errors import PoolUnavailable

    print("Testing PoolUnavailable...")

    # Not found
    error1 = PoolUnavailable.not_found("pool123")
    assert error1.recoverable == False
    assert error1.pool_address == "pool123"

    # Invalid state
    error2 = PoolUnavailable.invalid_state("pool456", "Pool is paused")
    assert error2.recoverable == False

    print("  PoolUnavailable: PASSED")


def test_insufficient_funds():
    """Test InsufficientFunds exception"""
    from dex_adapter_universal.errors import InsufficientFunds

    print("Testing InsufficientFunds...")

    error = InsufficientFunds.token_balance(
        token="SOL",
        required=Decimal("10"),
        available=Decimal("5"),
    )

    assert error.recoverable == False
    assert error.required == Decimal("10")
    assert error.available == Decimal("5")
    assert error.token == "SOL"

    print("  InsufficientFunds: PASSED")


def test_position_not_found():
    """Test PositionNotFound exception"""
    from dex_adapter_universal.errors import PositionNotFound

    print("Testing PositionNotFound...")

    error = PositionNotFound.not_found("pos123")

    assert error.recoverable == False
    assert error.position_id == "pos123"

    print("  PositionNotFound: PASSED")


def test_error_inheritance():
    """Test error class inheritance"""
    from dex_adapter_universal.errors import (
        DexAdapterError,
        RpcError,
        SlippageExceeded,
        PoolUnavailable,
        InsufficientFunds,
        PositionNotFound,
    )

    print("Testing Error Inheritance...")

    assert issubclass(RpcError, DexAdapterError)
    assert issubclass(SlippageExceeded, DexAdapterError)
    assert issubclass(PoolUnavailable, DexAdapterError)
    assert issubclass(InsufficientFunds, DexAdapterError)
    assert issubclass(PositionNotFound, DexAdapterError)

    # All should be catchable as DexAdapterError
    try:
        raise RpcError.connection_failed("test")
    except DexAdapterError:
        pass  # Expected

    print("  Error Inheritance: PASSED")


def main():
    """Run all error tests"""
    print("=" * 60)
    print("DEX Adapter Errors Tests")
    print("=" * 60)

    tests = [
        test_error_code,
        test_dex_adapter_error,
        test_rpc_error,
        test_slippage_exceeded,
        test_pool_unavailable,
        test_insufficient_funds,
        test_position_not_found,
        test_error_inheritance,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  FAILED: {e}")
            failed += 1

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
