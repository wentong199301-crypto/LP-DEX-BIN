"""
Market Module Unit Tests

Tests market module structure and logic without network dependencies.
Tests multi-chain MarketModule API (Solana, ETH, BSC).
"""

import sys
from pathlib import Path
from decimal import Decimal
from unittest.mock import Mock, MagicMock, patch

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dex_adapter_universal.modules.market import (
    MarketModule,
    Chain,
    DEFAULT_DEX_BY_CHAIN,
    VALID_DEX_BY_CHAIN,
)
from dex_adapter_universal.types.pool import KNOWN_POOLS


class TestChainImport:
    """Tests that Chain enum is properly imported from swap module"""

    def test_chain_values(self):
        """Test Chain enum values"""
        assert Chain.SOLANA.value == "solana"
        assert Chain.ETH.value == "eth"
        assert Chain.BSC.value == "bsc"

    def test_chain_is_evm(self):
        """Test is_evm property"""
        assert Chain.SOLANA.is_evm is False
        assert Chain.ETH.is_evm is True
        assert Chain.BSC.is_evm is True

    def test_chain_id(self):
        """Test chain_id property"""
        assert Chain.SOLANA.chain_id is None
        assert Chain.ETH.chain_id == 1
        assert Chain.BSC.chain_id == 56


class TestKnownPoolsStructure:
    """Tests for KNOWN_POOLS dict structure"""

    def test_raydium_pools_exist(self):
        """Test that raydium pools are present"""
        assert "raydium" in KNOWN_POOLS
        assert "SOL/USDC" in KNOWN_POOLS["raydium"]
        assert "SOL/USDT" in KNOWN_POOLS["raydium"]
        assert "SOL/USD1" in KNOWN_POOLS["raydium"]

    def test_meteora_pools_exist(self):
        """Test that meteora pools are present"""
        assert "meteora" in KNOWN_POOLS
        assert "SOL/USDC" in KNOWN_POOLS["meteora"]

    def test_uniswap_pools_exist(self):
        """Test that uniswap pools are present"""
        assert "uniswap" in KNOWN_POOLS
        assert "WETH/USDT" in KNOWN_POOLS["uniswap"]

    def test_pancakeswap_pools_exist(self):
        """Test that pancakeswap pools are present"""
        assert "pancakeswap" in KNOWN_POOLS
        assert "USDT/WBNB" in KNOWN_POOLS["pancakeswap"]
        assert "USDC/WBNB" in KNOWN_POOLS["pancakeswap"]

    def test_uniswap_pool_addresses_format(self):
        """Test that Uniswap pool addresses are valid EVM addresses"""
        for symbol, address in KNOWN_POOLS["uniswap"].items():
            assert address.startswith("0x"), f"Uniswap pool {symbol} should be 0x prefixed"
            assert len(address) == 42, f"Uniswap pool {symbol} should be 42 chars"

    def test_pancakeswap_pool_addresses_format(self):
        """Test that PancakeSwap pool addresses are valid EVM addresses"""
        for symbol, address in KNOWN_POOLS["pancakeswap"].items():
            assert address.startswith("0x"), f"PancakeSwap pool {symbol} should be 0x prefixed"
            assert len(address) == 42, f"PancakeSwap pool {symbol} should be 42 chars"


class TestDefaultDexMapping:
    """Tests for DEFAULT_DEX_BY_CHAIN mapping"""

    def test_solana_default_dex(self):
        """Test Solana default dex is raydium"""
        assert DEFAULT_DEX_BY_CHAIN[Chain.SOLANA] == "raydium"

    def test_eth_default_dex(self):
        """Test ETH default dex is uniswap"""
        assert DEFAULT_DEX_BY_CHAIN[Chain.ETH] == "uniswap"

    def test_bsc_default_dex(self):
        """Test BSC default dex is pancakeswap"""
        assert DEFAULT_DEX_BY_CHAIN[Chain.BSC] == "pancakeswap"


class TestValidDexByChain:
    """Tests for VALID_DEX_BY_CHAIN mapping"""

    def test_solana_valid_dexes(self):
        """Test Solana valid dexes"""
        assert "raydium" in VALID_DEX_BY_CHAIN[Chain.SOLANA]
        assert "meteora" in VALID_DEX_BY_CHAIN[Chain.SOLANA]

    def test_eth_valid_dexes(self):
        """Test ETH valid dexes"""
        assert "uniswap" in VALID_DEX_BY_CHAIN[Chain.ETH]

    def test_bsc_valid_dexes(self):
        """Test BSC valid dexes"""
        assert "pancakeswap" in VALID_DEX_BY_CHAIN[Chain.BSC]


class TestMarketModuleInit:
    """Tests for MarketModule initialization"""

    def test_has_chain_param_in_pool(self):
        """Test that pool method has chain parameter"""
        import inspect
        sig = inspect.signature(MarketModule.pool)
        assert "chain" in sig.parameters

    def test_has_chain_param_in_pool_by_symbol(self):
        """Test that pool_by_symbol method has chain parameter"""
        import inspect
        sig = inspect.signature(MarketModule.pool_by_symbol)
        assert "chain" in sig.parameters

    def test_has_chain_param_in_price(self):
        """Test that price method has chain parameter"""
        import inspect
        sig = inspect.signature(MarketModule.price)
        assert "chain" in sig.parameters

    def test_has_chain_param_in_price_usd(self):
        """Test that price_usd method has chain parameter"""
        import inspect
        sig = inspect.signature(MarketModule.price_usd)
        assert "chain" in sig.parameters

    def test_has_chain_param_in_pools(self):
        """Test that pools method has chain parameter"""
        import inspect
        sig = inspect.signature(MarketModule.pools)
        assert "chain" in sig.parameters

    def test_has_fee_param_in_pool_by_symbol(self):
        """Test that pool_by_symbol has fee parameter for EVM pools"""
        import inspect
        sig = inspect.signature(MarketModule.pool_by_symbol)
        assert "fee" in sig.parameters


class TestResolveTokenMethod:
    """Tests for resolve_token method"""

    def test_resolve_token_exists(self):
        """Test that resolve_token method exists"""
        assert hasattr(MarketModule, "resolve_token")

    def test_resolve_token_has_chain_param(self):
        """Test that resolve_token has chain parameter"""
        import inspect
        sig = inspect.signature(MarketModule.resolve_token)
        assert "chain" in sig.parameters

    def test_resolve_token_mint_has_chain_param(self):
        """Test that resolve_token_mint has chain parameter (backwards compat)"""
        import inspect
        sig = inspect.signature(MarketModule.resolve_token_mint)
        assert "chain" in sig.parameters


class TestEVMAdapterProperties:
    """Tests for EVM adapter properties"""

    def test_has_uniswap_adapter_getter(self):
        """Test that _get_uniswap_adapter method exists"""
        assert hasattr(MarketModule, "_get_uniswap_adapter")

    def test_has_pancakeswap_adapter_getter(self):
        """Test that _get_pancakeswap_adapter method exists"""
        assert hasattr(MarketModule, "_get_pancakeswap_adapter")

    def test_has_close_method(self):
        """Test that close method exists for cleanup"""
        assert hasattr(MarketModule, "close")

    def test_has_context_manager(self):
        """Test that MarketModule supports context manager"""
        assert hasattr(MarketModule, "__enter__")
        assert hasattr(MarketModule, "__exit__")


class TestHelperMethods:
    """Tests for helper methods"""

    def test_has_resolve_chain(self):
        """Test that _resolve_chain method exists"""
        assert hasattr(MarketModule, "_resolve_chain")

    def test_has_get_default_dex(self):
        """Test that _get_default_dex method exists"""
        assert hasattr(MarketModule, "_get_default_dex")

    def test_has_validate_chain_dex(self):
        """Test that _validate_chain_dex method exists"""
        assert hasattr(MarketModule, "_validate_chain_dex")


class TestMarketModuleWithMock:
    """Tests with mocked client"""

    @pytest.fixture
    def mock_client(self):
        """Create mock DexClient"""
        client = Mock()
        client.rpc = Mock()
        return client

    @pytest.fixture
    def market_module(self, mock_client):
        """Create MarketModule with mock client"""
        return MarketModule(mock_client)

    def test_evm_adapters_initially_none(self, market_module):
        """Test that EVM adapters are None initially (lazy loading)"""
        assert market_module._uniswap_adapter is None
        assert market_module._pancakeswap_adapter is None

    def test_resolve_chain_with_string(self, market_module):
        """Test _resolve_chain with string input"""
        assert market_module._resolve_chain("solana") == Chain.SOLANA
        assert market_module._resolve_chain("eth") == Chain.ETH
        assert market_module._resolve_chain("bsc") == Chain.BSC

    def test_resolve_chain_with_enum(self, market_module):
        """Test _resolve_chain with Chain enum input"""
        assert market_module._resolve_chain(Chain.SOLANA) == Chain.SOLANA
        assert market_module._resolve_chain(Chain.ETH) == Chain.ETH
        assert market_module._resolve_chain(Chain.BSC) == Chain.BSC

    def test_resolve_chain_with_none(self, market_module):
        """Test _resolve_chain with None defaults to Solana"""
        assert market_module._resolve_chain(None) == Chain.SOLANA

    def test_get_default_dex(self, market_module):
        """Test _get_default_dex returns correct defaults"""
        assert market_module._get_default_dex(Chain.SOLANA) == "raydium"
        assert market_module._get_default_dex(Chain.ETH) == "uniswap"
        assert market_module._get_default_dex(Chain.BSC) == "pancakeswap"

    def test_validate_chain_dex_valid(self, market_module):
        """Test _validate_chain_dex with valid combinations"""
        # Should not raise
        market_module._validate_chain_dex(Chain.SOLANA, "raydium")
        market_module._validate_chain_dex(Chain.SOLANA, "meteora")
        market_module._validate_chain_dex(Chain.ETH, "uniswap")
        market_module._validate_chain_dex(Chain.BSC, "pancakeswap")

    def test_validate_chain_dex_invalid(self, market_module):
        """Test _validate_chain_dex with invalid combinations"""
        from dex_adapter_universal.errors import OperationNotSupported

        with pytest.raises(OperationNotSupported):
            market_module._validate_chain_dex(Chain.ETH, "raydium")

        with pytest.raises(OperationNotSupported):
            market_module._validate_chain_dex(Chain.BSC, "uniswap")

        with pytest.raises(OperationNotSupported):
            market_module._validate_chain_dex(Chain.SOLANA, "pancakeswap")


def main():
    """Run all market module unit tests"""
    print("=" * 60)
    print("Market Module Unit Tests")
    print("=" * 60)

    # Run with pytest
    exit_code = pytest.main([__file__, "-v", "--tb=short"])
    return exit_code == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
