"""
Wallet Module Unit Tests

Tests wallet module logic without network dependencies.
"""

import sys
from pathlib import Path
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dex_adapter_universal.modules.wallet import WalletModule, Chain, TokenAccount
from dex_adapter_universal.errors import ConfigurationError


class TestChainEnum:
    """Tests for Chain enum"""

    def test_chain_values(self):
        """Test Chain enum values"""
        assert Chain.SOLANA.value == "solana"
        assert Chain.ETH.value == "eth"
        assert Chain.BSC.value == "bsc"

    def test_from_string_solana(self):
        """Test Chain.from_string for Solana"""
        assert Chain.from_string("solana") == Chain.SOLANA
        assert Chain.from_string("SOLANA") == Chain.SOLANA
        assert Chain.from_string("sol") == Chain.SOLANA
        assert Chain.from_string("SOL") == Chain.SOLANA

    def test_from_string_eth(self):
        """Test Chain.from_string for Ethereum"""
        assert Chain.from_string("eth") == Chain.ETH
        assert Chain.from_string("ETH") == Chain.ETH
        assert Chain.from_string("ethereum") == Chain.ETH
        assert Chain.from_string("1") == Chain.ETH

    def test_from_string_bsc(self):
        """Test Chain.from_string for BSC"""
        assert Chain.from_string("bsc") == Chain.BSC
        assert Chain.from_string("BSC") == Chain.BSC
        assert Chain.from_string("bnb") == Chain.BSC
        assert Chain.from_string("56") == Chain.BSC

    def test_from_string_invalid(self):
        """Test Chain.from_string with invalid input"""
        try:
            Chain.from_string("invalid")
            assert False, "Should have raised ConfigurationError"
        except ConfigurationError as e:
            assert "Unknown chain" in str(e)

    def test_chain_id(self):
        """Test chain_id property"""
        assert Chain.SOLANA.chain_id is None
        assert Chain.ETH.chain_id == 1
        assert Chain.BSC.chain_id == 56

    def test_is_evm(self):
        """Test is_evm property"""
        assert Chain.SOLANA.is_evm is False
        assert Chain.ETH.is_evm is True
        assert Chain.BSC.is_evm is True

    def test_native_token(self):
        """Test native_token property"""
        assert Chain.SOLANA.native_token == "SOL"
        assert Chain.ETH.native_token == "ETH"
        assert Chain.BSC.native_token == "BNB"


class TestTokenAccount:
    """Tests for TokenAccount dataclass"""

    def test_token_account_creation(self):
        """Test TokenAccount creation"""
        acc = TokenAccount(
            address="abc123",
            mint="mint123",
            owner="owner123",
            balance=Decimal("100.5"),
            decimals=9,
        )

        assert acc.address == "abc123"
        assert acc.mint == "mint123"
        assert acc.owner == "owner123"
        assert acc.balance == Decimal("100.5")
        assert acc.decimals == 9
        assert acc.chain == "solana"  # default

    def test_token_account_with_chain(self):
        """Test TokenAccount with explicit chain"""
        acc = TokenAccount(
            address="0x123",
            mint="0x456",
            owner="0x789",
            balance=Decimal("50"),
            decimals=18,
            chain="eth",
        )

        assert acc.chain == "eth"


class TestWalletModuleInit:
    """Tests for WalletModule initialization"""

    def test_init_empty(self):
        """Test initialization without any config"""
        wallet = WalletModule()

        assert wallet._client is None
        assert wallet._rpc is None
        assert wallet._evm_address is None
        assert wallet._eth_rpc_url is None
        assert wallet._bsc_rpc_url is None

    def test_init_with_evm_config(self):
        """Test initialization with EVM config"""
        wallet = WalletModule(
            evm_address="0x1234567890123456789012345678901234567890",
            eth_rpc_url="https://eth.example.com",
            bsc_rpc_url="https://bsc.example.com",
        )

        assert wallet._evm_address == "0x1234567890123456789012345678901234567890"
        assert wallet._eth_rpc_url == "https://eth.example.com"
        assert wallet._bsc_rpc_url == "https://bsc.example.com"

    def test_set_evm_address(self):
        """Test set_evm_address method"""
        wallet = WalletModule()
        wallet.set_evm_address("0xabcd")

        assert wallet.evm_address == "0xabcd"

    def test_set_eth_rpc(self):
        """Test set_eth_rpc method"""
        wallet = WalletModule()
        wallet.set_eth_rpc("https://new-eth.example.com")

        assert wallet._eth_rpc_url == "https://new-eth.example.com"

    def test_set_bsc_rpc(self):
        """Test set_bsc_rpc method"""
        wallet = WalletModule()
        wallet.set_bsc_rpc("https://new-bsc.example.com")

        assert wallet._bsc_rpc_url == "https://new-bsc.example.com"


class TestWalletModuleChainResolution:
    """Tests for chain resolution"""

    def test_resolve_chain_none(self):
        """Test _resolve_chain with None (default to Solana)"""
        wallet = WalletModule()

        result = wallet._resolve_chain(None)
        assert result == Chain.SOLANA

    def test_resolve_chain_enum(self):
        """Test _resolve_chain with Chain enum"""
        wallet = WalletModule()

        assert wallet._resolve_chain(Chain.ETH) == Chain.ETH
        assert wallet._resolve_chain(Chain.BSC) == Chain.BSC
        assert wallet._resolve_chain(Chain.SOLANA) == Chain.SOLANA

    def test_resolve_chain_string(self):
        """Test _resolve_chain with string"""
        wallet = WalletModule()

        assert wallet._resolve_chain("eth") == Chain.ETH
        assert wallet._resolve_chain("bsc") == Chain.BSC
        assert wallet._resolve_chain("solana") == Chain.SOLANA


class TestWalletModuleErrors:
    """Tests for error handling"""

    def test_sol_balance_without_client(self):
        """Test sol_balance without Solana client"""
        wallet = WalletModule()

        try:
            wallet.sol_balance()
            assert False, "Should have raised ConfigurationError"
        except ConfigurationError as e:
            assert "Solana client required" in str(e)

    def test_address_without_client(self):
        """Test address property without client"""
        wallet = WalletModule()

        try:
            _ = wallet.address
            assert False, "Should have raised ConfigurationError"
        except ConfigurationError as e:
            assert "Solana client required" in str(e)

    def test_evm_balance_without_address(self):
        """Test EVM balance without address"""
        wallet = WalletModule(eth_rpc_url="https://eth.example.com")

        try:
            wallet._require_evm_address()
            assert False, "Should have raised ConfigurationError"
        except ConfigurationError as e:
            assert "EVM address required" in str(e)

    def test_eth_balance_without_rpc(self):
        """Test ETH balance without RPC URL"""
        wallet = WalletModule(evm_address="0x1234567890123456789012345678901234567890")

        try:
            wallet._get_web3(1)
            assert False, "Should have raised ConfigurationError"
        except ConfigurationError as e:
            assert "Ethereum RPC URL required" in str(e)

    def test_bsc_balance_without_rpc(self):
        """Test BSC balance without RPC URL"""
        wallet = WalletModule(evm_address="0x1234567890123456789012345678901234567890")

        try:
            wallet._get_web3(56)
            assert False, "Should have raised ConfigurationError"
        except ConfigurationError as e:
            assert "BSC RPC URL required" in str(e)

    def test_unsupported_chain_id(self):
        """Test unsupported chain ID"""
        wallet = WalletModule()

        try:
            wallet._get_web3(999)
            assert False, "Should have raised ConfigurationError"
        except ConfigurationError as e:
            assert "Unsupported chain ID" in str(e)


class TestWalletModuleGetAddress:
    """Tests for get_address method"""

    def test_get_address_solana(self):
        """Test get_address for Solana"""
        mock_client = Mock()
        mock_client.pubkey = "SolanaAddress123"

        wallet = WalletModule(client=mock_client)

        address = wallet.get_address(chain="solana")
        assert address == "SolanaAddress123"

    def test_get_address_evm(self):
        """Test get_address for EVM"""
        wallet = WalletModule(evm_address="0xEvmAddress123")

        address = wallet.get_address(chain="eth")
        assert address == "0xEvmAddress123"


class TestWalletModuleClose:
    """Tests for close method"""

    def test_close_clears_web3_instances(self):
        """Test that close clears Web3 instances"""
        wallet = WalletModule()
        wallet._web3_instances = {1: Mock(), 56: Mock()}

        wallet.close()

        assert len(wallet._web3_instances) == 0

    def test_context_manager(self):
        """Test context manager protocol"""
        wallet = WalletModule()
        wallet._web3_instances = {1: Mock()}

        with wallet as w:
            assert w is wallet
            assert len(w._web3_instances) == 1

        assert len(wallet._web3_instances) == 0


def run_tests():
    """Run all unit tests"""
    import traceback

    test_classes = [
        TestChainEnum,
        TestTokenAccount,
        TestWalletModuleInit,
        TestWalletModuleChainResolution,
        TestWalletModuleErrors,
        TestWalletModuleGetAddress,
        TestWalletModuleClose,
    ]

    passed = 0
    failed = 0

    for test_class in test_classes:
        print(f"\n{test_class.__name__}")
        print("-" * len(test_class.__name__))

        instance = test_class()
        for method_name in dir(instance):
            if method_name.startswith("test_"):
                method = getattr(instance, method_name)
                try:
                    method()
                    print(f"  {method_name}: PASSED")
                    passed += 1
                except Exception as e:
                    print(f"  {method_name}: FAILED - {e}")
                    traceback.print_exc()
                    failed += 1

    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
