"""
Wallet Module Unit Tests

Tests wallet module logic without network dependencies.
Tests the multi-chain WalletModule API (Solana, ETH, BSC).
"""

import sys
from pathlib import Path
from decimal import Decimal
from unittest.mock import Mock, MagicMock, patch

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dex_adapter_universal.modules.wallet import WalletModule, TokenAccount, Chain
from dex_adapter_universal.types.solana_tokens import SOLANA_TOKEN_MINTS


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
        from dex_adapter_universal.errors import ConfigurationError
        with pytest.raises(ConfigurationError):
            Chain.from_string("invalid")

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
        """Test TokenAccount creation with all required fields"""
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

    def test_token_account_with_zero_balance(self):
        """Test TokenAccount with zero balance"""
        acc = TokenAccount(
            address="addr",
            mint="mint",
            owner="owner",
            balance=Decimal(0),
            decimals=6,
        )

        assert acc.balance == Decimal(0)
        assert acc.decimals == 6

    def test_token_account_high_precision(self):
        """Test TokenAccount handles high precision decimals"""
        acc = TokenAccount(
            address="addr",
            mint="mint",
            owner="owner",
            balance=Decimal("0.000000001"),
            decimals=9,
        )

        assert acc.balance == Decimal("0.000000001")


class TestWalletModuleSolana:
    """Tests for WalletModule Solana operations"""

    @pytest.fixture
    def mock_client(self):
        """Create mock DexClient with mock rpc and pubkey"""
        client = Mock()
        client.pubkey = "SolanaWalletAddress123"
        client.rpc = Mock()
        return client

    @pytest.fixture
    def wallet(self, mock_client):
        """Create WalletModule with mocked client"""
        return WalletModule(mock_client)

    def test_address_property(self, wallet, mock_client):
        """Test wallet.address returns client.pubkey"""
        assert wallet.address == "SolanaWalletAddress123"

    def test_balance_sol(self, wallet, mock_client):
        """Test balance('SOL', chain='sol') returns native SOL balance"""
        mock_client.rpc.get_balance.return_value = 2_000_000_000

        balance = wallet.balance("SOL", chain="sol")

        assert balance == Decimal("2")
        mock_client.rpc.get_balance.assert_called_once_with("SolanaWalletAddress123")

    def test_balance_sol_case_insensitive(self, wallet, mock_client):
        """Test balance('sol', chain='sol') is case insensitive"""
        mock_client.rpc.get_balance.return_value = 2_000_000_000

        balance = wallet.balance("sol", chain="sol")

        assert balance == Decimal("2")

    def test_balance_token(self, wallet, mock_client):
        """Test balance for SPL token"""
        mock_client.rpc.get_token_accounts_by_owner.return_value = [
            {
                "pubkey": "TokenAccountAddr",
                "account": {
                    "data": {
                        "parsed": {
                            "info": {
                                "mint": SOLANA_TOKEN_MINTS["USDC"],
                                "tokenAmount": {
                                    "amount": "1000000",
                                    "decimals": 6,
                                }
                            }
                        }
                    }
                }
            }
        ]

        balance = wallet.balance("USDC", chain="sol")

        assert balance == Decimal("1")

    def test_balance_token_not_found(self, wallet, mock_client):
        """Test balance returns 0 when token account doesn't exist"""
        mock_client.rpc.get_token_accounts_by_owner.return_value = []

        balance = wallet.balance("USDC", chain="sol")

        assert balance == Decimal(0)

    def test_balance_multiple_accounts(self, wallet, mock_client):
        """Test balance sums multiple token accounts"""
        mock_client.rpc.get_token_accounts_by_owner.return_value = [
            {
                "pubkey": "TokenAccount1",
                "account": {
                    "data": {
                        "parsed": {
                            "info": {
                                "mint": SOLANA_TOKEN_MINTS["USDC"],
                                "tokenAmount": {
                                    "amount": "1000000",
                                    "decimals": 6,
                                }
                            }
                        }
                    }
                }
            },
            {
                "pubkey": "TokenAccount2",
                "account": {
                    "data": {
                        "parsed": {
                            "info": {
                                "mint": SOLANA_TOKEN_MINTS["USDC"],
                                "tokenAmount": {
                                    "amount": "2000000",
                                    "decimals": 6,
                                }
                            }
                        }
                    }
                }
            }
        ]

        balance = wallet.balance("USDC", chain="sol")

        assert balance == Decimal("3")

    def test_balance_raw_sol(self, wallet, mock_client):
        """Test balance_raw('SOL', chain='sol') returns lamports"""
        mock_client.rpc.get_balance.return_value = 1_500_000_000

        balance = wallet.balance_raw("SOL", chain="sol")

        assert balance == 1_500_000_000

    def test_balance_raw_token(self, wallet, mock_client):
        """Test balance_raw for SPL token returns raw amount"""
        mock_client.rpc.get_token_accounts_by_owner.return_value = [
            {
                "pubkey": "TokenAccountAddr",
                "account": {
                    "data": {
                        "parsed": {
                            "info": {
                                "mint": SOLANA_TOKEN_MINTS["USDC"],
                                "tokenAmount": {
                                    "amount": "1500000",
                                    "decimals": 6,
                                }
                            }
                        }
                    }
                }
            }
        ]

        balance = wallet.balance_raw("USDC", chain="sol")

        assert balance == 1500000

    def test_balances(self, wallet, mock_client):
        """Test balances returns all token balances"""
        mock_client.rpc.get_balance.return_value = 1_000_000_000
        mock_client.rpc.get_token_accounts_by_owner.return_value = [
            {
                "pubkey": "TokenAccount1",
                "account": {
                    "data": {
                        "parsed": {
                            "info": {
                                "mint": SOLANA_TOKEN_MINTS["USDC"],
                                "owner": "SolanaWalletAddress123",
                                "tokenAmount": {
                                    "amount": "5000000",
                                    "decimals": 6,
                                }
                            }
                        }
                    }
                }
            }
        ]

        balances = wallet.balances()

        assert WalletModule.WRAPPED_SOL in balances
        assert balances[WalletModule.WRAPPED_SOL] == Decimal("1")
        assert SOLANA_TOKEN_MINTS["USDC"] in balances
        assert balances[SOLANA_TOKEN_MINTS["USDC"]] == Decimal("5")

    def test_token_accounts(self, wallet, mock_client):
        """Test token_accounts returns list of TokenAccount objects"""
        mock_client.rpc.get_token_accounts_by_owner.return_value = [
            {
                "pubkey": "TokenAccountAddr",
                "account": {
                    "data": {
                        "parsed": {
                            "info": {
                                "mint": "MintAddr123",
                                "owner": "SolanaWalletAddress123",
                                "tokenAmount": {
                                    "amount": "1000000",
                                    "decimals": 6,
                                }
                            }
                        }
                    }
                }
            }
        ]

        accounts = wallet.token_accounts()

        assert len(accounts) == 1
        acc = accounts[0]
        assert isinstance(acc, TokenAccount)
        assert acc.address == "TokenAccountAddr"
        assert acc.mint == "MintAddr123"
        assert acc.owner == "SolanaWalletAddress123"
        assert acc.balance == Decimal("1")
        assert acc.decimals == 6

    def test_token_accounts_empty(self, wallet, mock_client):
        """Test token_accounts returns empty list when no accounts"""
        mock_client.rpc.get_token_accounts_by_owner.return_value = []

        accounts = wallet.token_accounts()

        assert accounts == []

    def test_get_token_account(self, wallet, mock_client):
        """Test get_token_account returns account address"""
        mock_client.rpc.get_token_accounts_by_owner.return_value = [
            {"pubkey": "TokenAccountAddr"}
        ]

        account = wallet.get_token_account("USDC")

        assert account == "TokenAccountAddr"

    def test_get_token_account_not_found(self, wallet, mock_client):
        """Test get_token_account returns None when not found"""
        mock_client.rpc.get_token_accounts_by_owner.return_value = []

        account = wallet.get_token_account("USDC")

        assert account is None

    def test_has_token_account_true(self, wallet, mock_client):
        """Test has_token_account returns True when account exists"""
        mock_client.rpc.get_token_accounts_by_owner.return_value = [
            {"pubkey": "TokenAccountAddr"}
        ]

        result = wallet.has_token_account("USDC")

        assert result is True

    def test_has_token_account_false(self, wallet, mock_client):
        """Test has_token_account returns False when no account"""
        mock_client.rpc.get_token_accounts_by_owner.return_value = []

        result = wallet.has_token_account("USDC")

        assert result is False


class TestWalletModuleEVM:
    """Tests for WalletModule EVM operations"""

    @pytest.fixture
    def mock_client(self):
        """Create mock DexClient"""
        client = Mock()
        client.pubkey = "SolanaWalletAddress123"
        client.rpc = Mock()
        return client

    @pytest.fixture
    def wallet(self, mock_client):
        """Create WalletModule with mocked client"""
        w = WalletModule(mock_client)
        w.set_evm_address("0x1234567890123456789012345678901234567890")
        return w

    def test_set_evm_address(self, mock_client):
        """Test set_evm_address stores address"""
        wallet = WalletModule(mock_client)
        wallet.set_evm_address("0xABCD")

        assert wallet.evm_address == "0xABCD"

    def test_get_address_solana(self, wallet):
        """Test get_address for Solana"""
        assert wallet.get_address(chain="sol") == "SolanaWalletAddress123"
        assert wallet.get_address(chain="solana") == "SolanaWalletAddress123"

    def test_get_address_evm(self, wallet):
        """Test get_address for EVM chains"""
        assert wallet.get_address(chain="eth") == "0x1234567890123456789012345678901234567890"
        assert wallet.get_address(chain="bsc") == "0x1234567890123456789012345678901234567890"

    def test_get_address_evm_without_address(self, mock_client):
        """Test get_address raises error when EVM address not set"""
        from dex_adapter_universal.errors import ConfigurationError
        wallet = WalletModule(mock_client)

        with pytest.raises(ConfigurationError):
            wallet.get_address(chain="eth")

    def test_balance_eth(self, wallet):
        """Test balance('ETH', chain='eth')"""
        mock_web3 = Mock()

        with patch.object(wallet, '_get_web3', return_value=mock_web3):
            with patch('dex_adapter_universal.infra.evm_signer.get_balance') as mock_get_balance:
                mock_get_balance.return_value = 1_500_000_000_000_000_000  # 1.5 ETH in wei

                balance = wallet.balance("ETH", chain="eth")

                assert balance == Decimal("1.5")
                mock_get_balance.assert_called_once()

    def test_balance_bnb(self, wallet):
        """Test balance('BNB', chain='bsc')"""
        mock_web3 = Mock()

        with patch.object(wallet, '_get_web3', return_value=mock_web3):
            with patch('dex_adapter_universal.infra.evm_signer.get_balance') as mock_get_balance:
                mock_get_balance.return_value = 2_000_000_000_000_000_000  # 2 BNB in wei

                balance = wallet.balance("BNB", chain="bsc")

                assert balance == Decimal("2")

    def test_balance_usdc_eth(self, wallet):
        """Test balance('USDC', chain='eth') - 6 decimals"""
        mock_web3 = Mock()

        with patch.object(wallet, '_get_web3', return_value=mock_web3):
            with patch('dex_adapter_universal.infra.evm_signer.get_balance') as mock_get_balance:
                mock_get_balance.return_value = 1_000_000  # 1 USDC (6 decimals)

                balance = wallet.balance("USDC", chain="eth")

                assert balance == Decimal("1")

    def test_balance_usdc_bsc(self, wallet):
        """Test balance('USDC', chain='bsc') - 18 decimals on BSC"""
        mock_web3 = Mock()

        with patch.object(wallet, '_get_web3', return_value=mock_web3):
            with patch('dex_adapter_universal.infra.evm_signer.get_balance') as mock_get_balance:
                mock_get_balance.return_value = 1_000_000_000_000_000_000  # 1 USDC (18 decimals on BSC)

                balance = wallet.balance("USDC", chain="bsc")

                assert balance == Decimal("1")

    def test_balance_raw_eth(self, wallet):
        """Test balance_raw('ETH', chain='eth') returns wei"""
        mock_web3 = Mock()

        with patch.object(wallet, '_get_web3', return_value=mock_web3):
            with patch('dex_adapter_universal.infra.evm_signer.get_balance') as mock_get_balance:
                mock_get_balance.return_value = 1_500_000_000_000_000_000

                balance = wallet.balance_raw("ETH", chain="eth")

                assert balance == 1_500_000_000_000_000_000

    def test_balance_evm_without_address(self, mock_client):
        """Test balance raises error when EVM address not set"""
        from dex_adapter_universal.errors import ConfigurationError
        wallet = WalletModule(mock_client)
        mock_web3 = Mock()

        with patch.object(wallet, '_get_web3', return_value=mock_web3):
            with pytest.raises(ConfigurationError):
                wallet.balance("ETH", chain="eth")


class TestWalletModuleChainResolution:
    """Tests for chain resolution"""

    @pytest.fixture
    def mock_client(self):
        client = Mock()
        client.pubkey = "SolanaWalletAddress123"
        client.rpc = Mock()
        return client

    @pytest.fixture
    def wallet(self, mock_client):
        return WalletModule(mock_client)

    def test_resolve_chain_enum(self, wallet):
        """Test _resolve_chain with Chain enum"""
        assert wallet._resolve_chain(Chain.ETH) == Chain.ETH
        assert wallet._resolve_chain(Chain.BSC) == Chain.BSC
        assert wallet._resolve_chain(Chain.SOLANA) == Chain.SOLANA

    def test_resolve_chain_string(self, wallet):
        """Test _resolve_chain with string"""
        assert wallet._resolve_chain("eth") == Chain.ETH
        assert wallet._resolve_chain("bsc") == Chain.BSC
        assert wallet._resolve_chain("solana") == Chain.SOLANA
        assert wallet._resolve_chain("sol") == Chain.SOLANA


class TestWalletModuleConstants:
    """Tests for WalletModule class constants"""

    def test_wrapped_sol_constant(self):
        """Test WRAPPED_SOL constant is defined"""
        assert hasattr(WalletModule, 'WRAPPED_SOL')
        assert isinstance(WalletModule.WRAPPED_SOL, str)

    def test_usdc_constant(self):
        """Test USDC constant is defined"""
        assert hasattr(WalletModule, 'USDC')
        assert isinstance(WalletModule.USDC, str)

    def test_usdt_constant(self):
        """Test USDT constant is defined"""
        assert hasattr(WalletModule, 'USDT')
        assert isinstance(WalletModule.USDT, str)


class TestWalletModuleClose:
    """Tests for close method"""

    @pytest.fixture
    def mock_client(self):
        client = Mock()
        client.pubkey = "SolanaWalletAddress123"
        client.rpc = Mock()
        return client

    def test_close_no_error(self, mock_client):
        """Test that close can be called without error"""
        wallet = WalletModule(mock_client)
        wallet.close()  # Should not raise

    def test_context_manager(self, mock_client):
        """Test context manager protocol"""
        wallet = WalletModule(mock_client)

        with wallet as w:
            assert w is wallet

        # Context manager should exit cleanly


def run_tests():
    """Run all unit tests"""
    import traceback

    test_classes = [
        TestChainEnum,
        TestTokenAccount,
        TestWalletModuleSolana,
        TestWalletModuleEVM,
        TestWalletModuleChainResolution,
        TestWalletModuleConstants,
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
                    # Create fixtures for tests that need them
                    if test_class in (TestWalletModuleSolana, TestWalletModuleEVM,
                                      TestWalletModuleChainResolution, TestWalletModuleClose):
                        mock_client = Mock()
                        mock_client.pubkey = "SolanaWalletAddress123"
                        mock_client.rpc = Mock()
                        wallet = WalletModule(mock_client)
                        if test_class == TestWalletModuleEVM:
                            wallet.set_evm_address("0x1234567890123456789012345678901234567890")
                        method(wallet, mock_client)
                    else:
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
