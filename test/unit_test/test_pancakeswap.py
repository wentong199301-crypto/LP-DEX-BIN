"""
Unit tests for PancakeSwap V3 liquidity adapter (no external dependencies)

Tests configuration, imports, and type definitions
without requiring network access.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def test_pancakeswap_config():
    """Test PancakeSwapConfig dataclass"""
    print("Testing PancakeSwapConfig...")

    from dex_adapter.config import PancakeSwapConfig

    config = PancakeSwapConfig()

    # Test defaults (BSC only)
    assert config.gas_limit_multiplier == 1.2
    assert config.bsc_chain_id == 56

    # Test RPC URLs have values
    assert config.bsc_rpc_url is not None

    print("  PancakeSwapConfig: PASSED")


def test_config_has_pancakeswap():
    """Test global config includes PancakeSwapConfig"""
    print("Testing global config...")

    from dex_adapter.config import config

    assert hasattr(config, "pancakeswap")
    assert config.pancakeswap.bsc_chain_id == 56
    assert config.pancakeswap.gas_limit_multiplier == 1.2

    print("  global config: PASSED")


def test_v3_contract_addresses():
    """Test PancakeSwap V3 contract addresses (BSC only)"""
    print("Testing V3 contract addresses...")

    from dex_adapter.protocols.pancakeswap.api import (
        PANCAKESWAP_POSITION_MANAGER_ADDRESSES,
        PANCAKESWAP_FACTORY_ADDRESSES,
        PANCAKESWAP_SUPPORTED_CHAINS,
    )

    # BSC only
    assert PANCAKESWAP_SUPPORTED_CHAINS == [56]
    assert 56 in PANCAKESWAP_POSITION_MANAGER_ADDRESSES
    assert len(PANCAKESWAP_POSITION_MANAGER_ADDRESSES) == 1

    for chain_id, addr in PANCAKESWAP_POSITION_MANAGER_ADDRESSES.items():
        assert addr.startswith("0x"), f"Invalid PM address for chain {chain_id}"
        assert len(addr) == 42, f"Invalid PM address length for chain {chain_id}"

    # Factory addresses (BSC only)
    assert 56 in PANCAKESWAP_FACTORY_ADDRESSES
    assert len(PANCAKESWAP_FACTORY_ADDRESSES) == 1

    for chain_id, addr in PANCAKESWAP_FACTORY_ADDRESSES.items():
        assert addr.startswith("0x"), f"Invalid factory address for chain {chain_id}"
        assert len(addr) == 42, f"Invalid factory address length for chain {chain_id}"

    print("  V3 contract addresses: PASSED")


def test_fee_tiers():
    """Test PancakeSwap V3 fee tiers"""
    print("Testing fee tiers...")

    from dex_adapter.protocols.pancakeswap.api import (
        PANCAKESWAP_FEE_TIERS,
        TICK_SPACING_BY_FEE,
    )

    # Fee tiers
    expected_fees = [100, 500, 2500, 10000]
    for fee in expected_fees:
        assert fee in PANCAKESWAP_FEE_TIERS, f"Missing fee tier: {fee}"

    # Tick spacing
    assert TICK_SPACING_BY_FEE[100] == 1
    assert TICK_SPACING_BY_FEE[500] == 10
    assert TICK_SPACING_BY_FEE[2500] == 50
    assert TICK_SPACING_BY_FEE[10000] == 200

    print("  fee tiers: PASSED")


def test_pancakeswap_adapter_import():
    """Test PancakeSwapAdapter can be imported"""
    print("Testing PancakeSwapAdapter import...")

    from dex_adapter.protocols.pancakeswap import PancakeSwapAdapter

    # Test class exists and has expected attributes
    assert PancakeSwapAdapter is not None
    assert hasattr(PancakeSwapAdapter, 'get_balance')
    assert hasattr(PancakeSwapAdapter, 'get_native_balance')
    assert hasattr(PancakeSwapAdapter, 'close')

    # Check adapter name
    assert PancakeSwapAdapter.name == "pancakeswap"

    print("  PancakeSwapAdapter import: PASSED")


def test_main_package_exports():
    """Test main package exports PancakeSwap"""
    print("Testing main package exports...")

    from dex_adapter import PancakeSwapAdapter

    assert PancakeSwapAdapter is not None
    assert PancakeSwapAdapter.name == "pancakeswap"

    print("  main package exports: PASSED")


def test_bsc_token_resolution():
    """Test BSC token resolution (used by PancakeSwap)"""
    print("Testing BSC token resolution for PancakeSwap...")

    from dex_adapter.types.evm_tokens import (
        resolve_token_address,
        get_token_decimals,
        NATIVE_TOKEN_ADDRESS,
    )

    # BSC tokens commonly used with PancakeSwap
    assert resolve_token_address("BNB", 56) == NATIVE_TOKEN_ADDRESS
    assert resolve_token_address("WBNB", 56) == "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"
    assert resolve_token_address("CAKE", 56) == "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82"
    assert resolve_token_address("USDT", 56) == "0x55d398326f99059fF775485246999027B3197955"
    assert resolve_token_address("BUSD", 56) == "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56"

    # Decimals
    assert get_token_decimals("BNB", 56) == 18
    assert get_token_decimals("CAKE", 56) == 18
    assert get_token_decimals("USDT", 56) == 18

    print("  BSC token resolution: PASSED")


def test_erc20_abi_defined():
    """Test ERC20 ABI is defined in adapter"""
    print("Testing ERC20 ABI...")

    from dex_adapter.protocols.pancakeswap.adapter import ERC20_ABI

    assert ERC20_ABI is not None
    assert len(ERC20_ABI) >= 2

    # Check for approve and allowance functions
    function_names = [f.get("name") for f in ERC20_ABI]
    assert "approve" in function_names
    assert "allowance" in function_names

    print("  ERC20 ABI: PASSED")


def test_v3_abis_defined():
    """Test V3 ABIs are defined in adapter"""
    print("Testing V3 ABIs...")

    from dex_adapter.protocols.pancakeswap.adapter import (
        POSITION_MANAGER_ABI,
        FACTORY_ABI,
        POOL_ABI,
    )

    assert POSITION_MANAGER_ABI is not None
    assert FACTORY_ABI is not None
    assert POOL_ABI is not None

    # Check Position Manager has expected functions
    pm_functions = [f.get("name") for f in POSITION_MANAGER_ABI]
    assert "positions" in pm_functions
    assert "mint" in pm_functions
    assert "increaseLiquidity" in pm_functions
    assert "decreaseLiquidity" in pm_functions
    assert "collect" in pm_functions
    assert "burn" in pm_functions

    # Check Factory has getPool
    factory_functions = [f.get("name") for f in FACTORY_ABI]
    assert "getPool" in factory_functions

    # Check Pool has expected functions
    pool_functions = [f.get("name") for f in POOL_ABI]
    assert "slot0" in pool_functions
    assert "token0" in pool_functions
    assert "token1" in pool_functions

    print("  V3 ABIs: PASSED")


def test_chain_name_property():
    """Test chain name resolution"""
    print("Testing chain name resolution...")

    from dex_adapter.protocols.pancakeswap.adapter import PancakeSwapAdapter

    assert hasattr(PancakeSwapAdapter, 'chain_name')

    print("  chain name property: PASSED")


def test_protocol_module_structure():
    """Test PancakeSwap module has correct structure"""
    print("Testing module structure...")

    from dex_adapter.protocols import pancakeswap

    # Check __all__ exports
    assert hasattr(pancakeswap, '__all__')
    assert 'PancakeSwapAdapter' in pancakeswap.__all__
    assert 'PANCAKESWAP_POSITION_MANAGER_ADDRESSES' in pancakeswap.__all__
    assert 'PANCAKESWAP_FACTORY_ADDRESSES' in pancakeswap.__all__
    assert 'PANCAKESWAP_SUPPORTED_CHAINS' in pancakeswap.__all__
    assert 'CHAIN_NAMES' in pancakeswap.__all__
    assert 'PANCAKESWAP_FEE_TIERS' in pancakeswap.__all__
    assert 'TICK_SPACING_BY_FEE' in pancakeswap.__all__

    print("  module structure: PASSED")


def test_adapter_properties():
    """Test adapter has required properties"""
    print("Testing adapter properties...")

    from dex_adapter.protocols.pancakeswap import PancakeSwapAdapter

    # Check class has required properties
    properties = [
        'chain_id', 'chain_name', 'address', 'pubkey', 'web3',
        'position_manager_address', 'factory_address',
    ]

    for prop in properties:
        assert hasattr(PancakeSwapAdapter, prop), f"Missing property: {prop}"

    print("  adapter properties: PASSED")


def test_adapter_liquidity_methods():
    """Test adapter has liquidity methods"""
    print("Testing adapter liquidity methods...")

    from dex_adapter.protocols.pancakeswap import PancakeSwapAdapter

    # Check class has liquidity methods
    methods = [
        'get_pool', 'get_pool_by_address',
        'get_positions', 'get_position',
        'open_position', 'add_liquidity', 'remove_liquidity',
        'claim_fees', 'close_position',
    ]

    for method in methods:
        assert hasattr(PancakeSwapAdapter, method), f"Missing method: {method}"

    print("  adapter liquidity methods: PASSED")


def test_adapter_math_methods():
    """Test adapter has V3 math methods"""
    print("Testing adapter math methods...")

    from dex_adapter.protocols.pancakeswap import PancakeSwapAdapter

    # Check class has math methods
    methods = [
        'tick_to_price', 'price_to_tick',
        'sqrt_price_x96_to_price', 'price_to_sqrt_price_x96',
    ]

    for method in methods:
        assert hasattr(PancakeSwapAdapter, method), f"Missing method: {method}"

    print("  adapter math methods: PASSED")


def test_adapter_balance_methods():
    """Test adapter has balance methods"""
    print("Testing adapter balance methods...")

    from dex_adapter.protocols.pancakeswap import PancakeSwapAdapter

    # Check class has balance methods
    methods = ['get_balance', 'get_native_balance', 'get_token_balance']

    for method in methods:
        assert hasattr(PancakeSwapAdapter, method), f"Missing method: {method}"

    print("  adapter balance methods: PASSED")


def main():
    """Run all unit tests"""
    print("=" * 60)
    print("PancakeSwap V3 Liquidity Adapter Unit Tests")
    print("=" * 60)
    print()

    tests = [
        test_pancakeswap_config,
        test_config_has_pancakeswap,
        test_v3_contract_addresses,
        test_fee_tiers,
        test_pancakeswap_adapter_import,
        test_main_package_exports,
        test_bsc_token_resolution,
        test_erc20_abi_defined,
        test_v3_abis_defined,
        test_chain_name_property,
        test_protocol_module_structure,
        test_adapter_properties,
        test_adapter_liquidity_methods,
        test_adapter_math_methods,
        test_adapter_balance_methods,
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
