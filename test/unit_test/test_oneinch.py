"""
Unit tests for 1inch adapter (no external dependencies)

Tests token resolution, configuration, and type definitions
without requiring network access or API keys.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dex_adapter_universal.types.evm_tokens import ETH_TOKEN_ADDRESSES, BSC_TOKEN_ADDRESSES


def test_evm_chain_enum():
    """Test EVMChain enum values"""
    print("Testing EVMChain enum...")

    from dex_adapter_universal.types.evm_tokens import EVMChain

    assert EVMChain.ETH.value == 1
    assert EVMChain.BSC.value == 56

    print("  EVMChain enum: PASSED")


def test_native_token_address():
    """Test native token address constant"""
    print("Testing native token address...")

    from dex_adapter_universal.types.evm_tokens import NATIVE_TOKEN_ADDRESS

    # 1inch uses this address for native tokens (ETH/BNB)
    assert NATIVE_TOKEN_ADDRESS == "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"

    print("  native token address: PASSED")


def test_eth_token_resolution():
    """Test Ethereum token address resolution"""
    print("Testing ETH token resolution...")

    from dex_adapter_universal.types.evm_tokens import (
        resolve_token_address,
        get_token_address,
        NATIVE_TOKEN_ADDRESS,
        ETH_TOKEN_ADDRESSES,
    )

    # Test symbol resolution
    assert resolve_token_address("ETH", 1) == NATIVE_TOKEN_ADDRESS
    assert resolve_token_address("WETH", 1) == ETH_TOKEN_ADDRESSES["WETH"]
    assert resolve_token_address("USDC", 1) == ETH_TOKEN_ADDRESSES["USDC"]
    assert resolve_token_address("USDT", 1) == ETH_TOKEN_ADDRESSES["USDT"]
    assert resolve_token_address("USD1", 1) == ETH_TOKEN_ADDRESSES["USD1"]

    # Test case-insensitive
    assert resolve_token_address("eth", 1) == NATIVE_TOKEN_ADDRESS
    assert resolve_token_address("Usdc", 1) == ETH_TOKEN_ADDRESSES["USDC"]

    # Test get_token_address (returns None for unknown)
    assert get_token_address("UNKNOWN_TOKEN", 1) is None

    print("  ETH token resolution: PASSED")


def test_bsc_token_resolution():
    """Test BSC token address resolution"""
    print("Testing BSC token resolution...")

    from dex_adapter_universal.types.evm_tokens import (
        resolve_token_address,
        NATIVE_TOKEN_ADDRESS,
        BSC_TOKEN_ADDRESSES,
    )

    # Test symbol resolution
    assert resolve_token_address("BNB", 56) == NATIVE_TOKEN_ADDRESS
    assert resolve_token_address("WBNB", 56) == BSC_TOKEN_ADDRESSES["WBNB"]
    assert resolve_token_address("USDC", 56) == BSC_TOKEN_ADDRESSES["USDC"]
    assert resolve_token_address("BUSD", 56) == BSC_TOKEN_ADDRESSES["BUSD"]
    assert resolve_token_address("CAKE", 56) == BSC_TOKEN_ADDRESSES["CAKE"]
    assert resolve_token_address("USD1", 56) == BSC_TOKEN_ADDRESSES["USD1"]

    print("  BSC token resolution: PASSED")


def test_address_passthrough():
    """Test that addresses are passed through unchanged"""
    print("Testing address passthrough...")

    from dex_adapter_universal.types.evm_tokens import resolve_token_address

    # Valid addresses should be returned as-is
    addr = "0x1234567890123456789012345678901234567890"
    assert resolve_token_address(addr, 1) == addr
    assert resolve_token_address(addr, 56) == addr

    # Mixed case should also work
    addr_mixed = "0xAbCdEf1234567890123456789012345678901234"
    assert resolve_token_address(addr_mixed, 1) == addr_mixed

    print("  address passthrough: PASSED")


def test_unknown_token_raises():
    """Test that unknown tokens raise ConfigurationError"""
    print("Testing unknown token error...")

    from dex_adapter_universal.types.evm_tokens import resolve_token_address
    from dex_adapter_universal.errors import ConfigurationError

    try:
        resolve_token_address("UNKNOWN_TOKEN_XYZ", 1)
        assert False, "Should have raised ConfigurationError"
    except ConfigurationError as e:
        assert "Unknown token" in str(e)

    try:
        resolve_token_address("FAKE_TOKEN", 56)
        assert False, "Should have raised ConfigurationError"
    except ConfigurationError:
        pass

    print("  unknown token error: PASSED")


def test_token_decimals():
    """Test token decimals lookup"""
    print("Testing token decimals...")

    from dex_adapter_universal.types.evm_tokens import get_token_decimals

    # ETH tokens
    assert get_token_decimals("ETH", 1) == 18
    assert get_token_decimals("WETH", 1) == 18
    assert get_token_decimals("USDC", 1) == 6  # ETH USDC has 6 decimals
    assert get_token_decimals("USDT", 1) == 6  # ETH USDT has 6 decimals
    assert get_token_decimals("WBTC", 1) == 8

    # BSC tokens
    assert get_token_decimals("BNB", 56) == 18
    assert get_token_decimals("USDC", 56) == 18  # BSC USDC has 18 decimals
    assert get_token_decimals("USDT", 56) == 18  # BSC USDT has 18 decimals
    assert get_token_decimals("BUSD", 56) == 18

    # Unknown token defaults to 18
    assert get_token_decimals("UNKNOWN", 1) == 18

    print("  token decimals: PASSED")


def test_is_native_token():
    """Test native token detection"""
    print("Testing is_native_token...")

    from dex_adapter_universal.types.evm_tokens import is_native_token, NATIVE_TOKEN_ADDRESS

    assert is_native_token(NATIVE_TOKEN_ADDRESS) is True
    assert is_native_token(NATIVE_TOKEN_ADDRESS.lower()) is True
    assert is_native_token(ETH_TOKEN_ADDRESSES["WETH"]) is False
    # Dummy test address (not a real token)
    assert is_native_token("0x1234567890123456789012345678901234567890") is False

    print("  is_native_token: PASSED")


def test_get_native_symbol():
    """Test native symbol lookup"""
    print("Testing get_native_symbol...")

    from dex_adapter_universal.types.evm_tokens import get_native_symbol

    assert get_native_symbol(1) == "ETH"
    assert get_native_symbol(56) == "BNB"
    assert get_native_symbol(999) == "ETH"  # Default to ETH for unknown chains

    print("  get_native_symbol: PASSED")


def test_evm_token_dataclass():
    """Test EVMToken dataclass"""
    print("Testing EVMToken dataclass...")

    from dex_adapter_universal.types.evm_tokens import EVMToken

    token = EVMToken(
        address=ETH_TOKEN_ADDRESSES["USDC"],
        symbol="USDC",
        decimals=6,
        name="USD Coin",
        chain_id=1,
    )

    assert token.address == ETH_TOKEN_ADDRESSES["USDC"]
    assert token.symbol == "USDC"
    assert token.decimals == 6
    assert token.name == "USD Coin"
    assert token.chain_id == 1
    assert str(token) == "USDC"

    # Test frozen (immutable)
    try:
        token.symbol = "FAKE"
        assert False, "Should have raised FrozenInstanceError"
    except Exception:
        pass

    print("  EVMToken dataclass: PASSED")


def test_oneinch_config():
    """Test OneInchConfig dataclass"""
    print("Testing OneInchConfig...")

    from dex_adapter_universal.config import OneInchConfig

    config = OneInchConfig()

    assert config.base_url == "https://api.1inch.dev/swap/v6.0"
    assert config.eth_chain_id == 1
    assert config.bsc_chain_id == 56
    assert config.timeout == 30.0
    # Note: max_retries was removed - now uses global config.tx.max_retries (default: 10)
    assert config.gas_limit_multiplier == 1.1

    print("  OneInchConfig: PASSED")


def test_config_has_oneinch():
    """Test global config includes OneInchConfig"""
    print("Testing global config...")

    from dex_adapter_universal.config import config

    assert hasattr(config, "oneinch")
    assert config.oneinch.eth_chain_id == 1
    assert config.oneinch.bsc_chain_id == 56

    print("  global config: PASSED")


def test_imports():
    """Test that all new modules can be imported"""
    print("Testing imports...")

    # Types
    from dex_adapter_universal.types.evm_tokens import (
        EVMChain,
        EVMToken,
        NATIVE_TOKEN_ADDRESS,
        ETH_TOKEN_ADDRESSES,
        BSC_TOKEN_ADDRESSES,
        resolve_token_address,
        get_token_decimals,
    )

    # Config
    from dex_adapter_universal.config import OneInchConfig, config

    print("  imports: PASSED")


def test_main_package_exports():
    """Test main package exports"""
    print("Testing main package exports...")

    from dex_adapter_universal import (
        EVMChain,
        EVMToken,
        NATIVE_TOKEN_ADDRESS,
    )

    assert EVMChain.ETH.value == 1
    assert EVMChain.BSC.value == 56
    assert NATIVE_TOKEN_ADDRESS is not None

    print("  main package exports: PASSED")


def main():
    """Run all unit tests"""
    print("=" * 60)
    print("1inch Adapter Unit Tests")
    print("=" * 60)
    print()

    tests = [
        test_evm_chain_enum,
        test_native_token_address,
        test_eth_token_resolution,
        test_bsc_token_resolution,
        test_address_passthrough,
        test_unknown_token_raises,
        test_token_decimals,
        test_is_native_token,
        test_get_native_symbol,
        test_evm_token_dataclass,
        test_oneinch_config,
        test_config_has_oneinch,
        test_imports,
        test_main_package_exports,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            import traceback
            print(f"  FAILED: {e}")
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
