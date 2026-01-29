"""
Unit tests for Uniswap unified liquidity adapter (no external dependencies)

Tests configuration, imports, and type definitions
without requiring network access.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dex_adapter_universal.types.evm_tokens import ETH_TOKEN_ADDRESSES


def test_uniswap_config():
    """Test UniswapConfig dataclass"""
    print("Testing UniswapConfig...")

    from dex_adapter_universal.config import UniswapConfig

    config = UniswapConfig()

    # Test defaults (Ethereum only)
    assert config.gas_limit_multiplier == 1.2
    assert config.eth_chain_id == 1

    # Test RPC URLs have values
    assert config.eth_rpc_url is not None

    print("  UniswapConfig: PASSED")


def test_config_has_uniswap():
    """Test global config includes UniswapConfig"""
    print("Testing global config...")

    from dex_adapter_universal.config import config

    assert hasattr(config, "uniswap")
    assert config.uniswap.eth_chain_id == 1
    assert config.uniswap.gas_limit_multiplier == 1.2

    print("  global config: PASSED")


def test_v3_contract_addresses():
    """Test Uniswap V3 contract addresses (Ethereum only)"""
    print("Testing V3 contract addresses...")

    from dex_adapter_universal.protocols.uniswap.api import (
        UNISWAP_V3_POSITION_MANAGER_ADDRESSES,
        UNISWAP_V3_FACTORY_ADDRESSES,
    )

    # Position Manager addresses (Ethereum only)
    assert 1 in UNISWAP_V3_POSITION_MANAGER_ADDRESSES
    assert len(UNISWAP_V3_POSITION_MANAGER_ADDRESSES) == 1  # Only Ethereum

    for chain_id, addr in UNISWAP_V3_POSITION_MANAGER_ADDRESSES.items():
        assert addr.startswith("0x"), f"Invalid PM address for chain {chain_id}"
        assert len(addr) == 42, f"Invalid PM address length for chain {chain_id}"

    # Factory addresses (Ethereum only)
    assert 1 in UNISWAP_V3_FACTORY_ADDRESSES
    assert len(UNISWAP_V3_FACTORY_ADDRESSES) == 1

    print("  V3 contract addresses: PASSED")


def test_v4_contract_addresses():
    """Test Uniswap V4 contract addresses (Ethereum only)"""
    print("Testing V4 contract addresses...")

    from dex_adapter_universal.protocols.uniswap.api import (
        UNISWAP_V4_POOL_MANAGER_ADDRESSES,
        UNISWAP_V4_POSITION_MANAGER_ADDRESSES,
    )

    # Pool Manager addresses (Ethereum only)
    assert 1 in UNISWAP_V4_POOL_MANAGER_ADDRESSES
    assert len(UNISWAP_V4_POOL_MANAGER_ADDRESSES) == 1  # Only Ethereum

    for chain_id, addr in UNISWAP_V4_POOL_MANAGER_ADDRESSES.items():
        assert addr.startswith("0x"), f"Invalid PM address for chain {chain_id}"
        assert len(addr) == 42, f"Invalid PM address length for chain {chain_id}"

    # Position Manager addresses (Ethereum only)
    assert 1 in UNISWAP_V4_POSITION_MANAGER_ADDRESSES
    assert len(UNISWAP_V4_POSITION_MANAGER_ADDRESSES) == 1

    print("  V4 contract addresses: PASSED")


def test_fee_tiers():
    """Test Uniswap fee tiers"""
    print("Testing fee tiers...")

    from dex_adapter_universal.protocols.uniswap.api import (
        UNISWAP_FEE_TIERS,
        TICK_SPACING_BY_FEE,
    )

    # Fee tiers
    expected_fees = [100, 500, 3000, 10000]
    for fee in expected_fees:
        assert fee in UNISWAP_FEE_TIERS, f"Missing fee tier: {fee}"

    # Tick spacing
    assert TICK_SPACING_BY_FEE[100] == 1
    assert TICK_SPACING_BY_FEE[500] == 10
    assert TICK_SPACING_BY_FEE[3000] == 60
    assert TICK_SPACING_BY_FEE[10000] == 200

    print("  fee tiers: PASSED")


def test_native_eth_address():
    """Test native ETH address for V4"""
    print("Testing native ETH address...")

    from dex_adapter_universal.protocols.uniswap.api import NATIVE_ETH_ADDRESS

    # V4 uses address(0) for native ETH
    assert NATIVE_ETH_ADDRESS == "0x0000000000000000000000000000000000000000"

    print("  native ETH address: PASSED")


def test_adapter_import():
    """Test UniswapAdapter can be imported"""
    print("Testing UniswapAdapter import...")

    from dex_adapter_universal.protocols.uniswap import UniswapAdapter

    # Test class exists and has expected attributes
    assert UniswapAdapter is not None
    assert hasattr(UniswapAdapter, 'close')

    # Check adapter name
    assert UniswapAdapter.name == "uniswap"

    print("  UniswapAdapter import: PASSED")


def test_main_package_exports():
    """Test main package exports Uniswap"""
    print("Testing main package exports...")

    from dex_adapter_universal import UniswapAdapter

    assert UniswapAdapter is not None
    assert UniswapAdapter.name == "uniswap"

    print("  main package exports: PASSED")


def test_module_structure():
    """Test Uniswap module has correct structure"""
    print("Testing module structure...")

    from dex_adapter_universal.protocols import uniswap

    # Check __all__ exports
    assert hasattr(uniswap, '__all__')
    assert 'UniswapAdapter' in uniswap.__all__
    assert 'UNISWAP_V3_POSITION_MANAGER_ADDRESSES' in uniswap.__all__
    assert 'UNISWAP_V3_FACTORY_ADDRESSES' in uniswap.__all__
    assert 'UNISWAP_V4_POOL_MANAGER_ADDRESSES' in uniswap.__all__
    assert 'UNISWAP_FEE_TIERS' in uniswap.__all__
    assert 'TICK_SPACING_BY_FEE' in uniswap.__all__

    print("  module structure: PASSED")


def test_pool_version_enum():
    """Test PoolVersion enum"""
    print("Testing PoolVersion enum...")

    from dex_adapter_universal.protocols.uniswap import PoolVersion

    assert PoolVersion.V3.value == "v3"
    assert PoolVersion.V4.value == "v4"

    print("  PoolVersion enum: PASSED")


def test_adapter_properties():
    """Test adapter has required properties"""
    print("Testing adapter properties...")

    from dex_adapter_universal.protocols.uniswap import UniswapAdapter

    # Check class has required properties
    properties = [
        'chain_id', 'chain_name', 'address', 'pubkey', 'web3',
        'v3_position_manager_address', 'v3_factory_address',
        'v4_pool_manager_address', 'v4_position_manager_address',
    ]

    for prop in properties:
        assert hasattr(UniswapAdapter, prop), f"Missing property: {prop}"

    print("  adapter properties: PASSED")


def test_adapter_liquidity_methods():
    """Test adapter has liquidity methods"""
    print("Testing adapter liquidity methods...")

    from dex_adapter_universal.protocols.uniswap import UniswapAdapter

    # Check class has liquidity methods
    methods = [
        'get_pool', 'get_pool_by_address',
        'get_positions', 'get_position',
        'open_position', 'add_liquidity', 'remove_liquidity',
        'claim_fees', 'close_position',
        'detect_pool_version',
    ]

    for method in methods:
        assert hasattr(UniswapAdapter, method), f"Missing method: {method}"

    print("  adapter liquidity methods: PASSED")


def test_adapter_math_methods():
    """Test adapter has math methods"""
    print("Testing adapter math methods...")

    from dex_adapter_universal.protocols.uniswap import UniswapAdapter

    # Check class has math methods
    methods = [
        'tick_to_price', 'price_to_tick',
        'sqrt_price_x96_to_price', 'price_to_sqrt_price_x96',
    ]

    for method in methods:
        assert hasattr(UniswapAdapter, method), f"Missing method: {method}"

    print("  adapter math methods: PASSED")


def test_eth_token_resolution():
    """Test ETH token resolution (used by Uniswap)"""
    print("Testing ETH token resolution...")

    from dex_adapter_universal.types.evm_tokens import (
        resolve_token_address,
        get_token_decimals,
        NATIVE_TOKEN_ADDRESS,
        ETH_TOKEN_ADDRESSES,
    )

    # ETH tokens
    assert resolve_token_address("ETH", 1) == NATIVE_TOKEN_ADDRESS
    assert resolve_token_address("WETH", 1) == ETH_TOKEN_ADDRESSES["WETH"]
    assert resolve_token_address("USDC", 1) == ETH_TOKEN_ADDRESSES["USDC"]

    # Decimals
    assert get_token_decimals("ETH", 1) == 18
    assert get_token_decimals("USDC", 1) == 6

    print("  ETH token resolution: PASSED")


def test_supported_chains():
    """Test supported chains (Ethereum only)"""
    print("Testing supported chains...")

    from dex_adapter_universal.protocols.uniswap.api import (
        UNISWAP_SUPPORTED_CHAINS,
        CHAIN_NAMES,
    )

    # Ethereum only
    assert UNISWAP_SUPPORTED_CHAINS == [1]
    assert len(CHAIN_NAMES) == 1
    assert CHAIN_NAMES[1] == "Ethereum"

    print("  supported chains: PASSED")


def test_v4_action_encoder():
    """Test V4ActionEncoder"""
    print("Testing V4ActionEncoder...")

    from dex_adapter_universal.protocols.uniswap.adapter import V4Actions, V4ActionEncoder

    # Test V4Actions constants
    assert V4Actions.INCREASE_LIQUIDITY == 0x00
    assert V4Actions.DECREASE_LIQUIDITY == 0x01
    assert V4Actions.MINT_POSITION == 0x02
    assert V4Actions.BURN_POSITION == 0x03
    assert V4Actions.TAKE_PAIR == 0x14
    assert V4Actions.SETTLE_PAIR == 0x15

    # Test encoding methods exist and return bytes
    settle_pair = V4ActionEncoder.encode_settle_pair(
        ETH_TOKEN_ADDRESSES["WETH"],
        ETH_TOKEN_ADDRESSES["USDC"]
    )
    assert isinstance(settle_pair, bytes)
    assert len(settle_pair) > 0

    # Use dummy address for recipient (test address, not a real token)
    dummy_recipient = "0x1234567890123456789012345678901234567890"
    take_pair = V4ActionEncoder.encode_take_pair(
        ETH_TOKEN_ADDRESSES["WETH"],
        ETH_TOKEN_ADDRESSES["USDC"],
        dummy_recipient
    )
    assert isinstance(take_pair, bytes)
    assert len(take_pair) > 0

    # Test build_unlock_data
    actions = [V4Actions.SETTLE_PAIR]
    params = [settle_pair]
    unlock_data = V4ActionEncoder.build_unlock_data(actions, params)
    assert isinstance(unlock_data, bytes)
    assert len(unlock_data) > 0

    print("  V4ActionEncoder: PASSED")


def test_v4_mutation_methods():
    """Test V4 mutation methods exist"""
    print("Testing V4 mutation methods...")

    from dex_adapter_universal.protocols.uniswap import UniswapAdapter

    # Check private V4 methods exist
    private_methods = [
        '_open_position_v4',
        '_add_liquidity_v4',
        '_remove_liquidity_v4',
        '_claim_fees_v4',
        '_close_position_v4',
    ]

    for method in private_methods:
        assert hasattr(UniswapAdapter, method), f"Missing V4 method: {method}"

    print("  V4 mutation methods: PASSED")


def main():
    """Run all unit tests"""
    print("=" * 60)
    print("Uniswap Unified Adapter Unit Tests")
    print("=" * 60)
    print()

    tests = [
        test_uniswap_config,
        test_config_has_uniswap,
        test_v3_contract_addresses,
        test_v4_contract_addresses,
        test_fee_tiers,
        test_native_eth_address,
        test_adapter_import,
        test_main_package_exports,
        test_module_structure,
        test_pool_version_enum,
        test_adapter_properties,
        test_adapter_liquidity_methods,
        test_adapter_math_methods,
        test_eth_token_resolution,
        test_supported_chains,
        test_v4_action_encoder,
        test_v4_mutation_methods,
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
