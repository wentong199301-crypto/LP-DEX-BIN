"""
Test Infrastructure Module

Tests for dex_adapter_universal.infra package (RPC, Signer, TxBuilder).
"""

import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_rpc_config():
    """Test RpcClientConfig dataclass"""
    from dex_adapter_universal.infra import RpcClientConfig

    print("Testing RpcClientConfig...")

    # Default config
    config1 = RpcClientConfig()
    assert config1.timeout_seconds == 30.0
    assert config1.max_retries == 3
    assert config1.commitment == "confirmed"

    # Custom config
    config2 = RpcClientConfig(
        timeout_seconds=60.0,
        max_retries=5,
        commitment="finalized",
    )
    assert config2.timeout_seconds == 60.0
    assert config2.max_retries == 5

    print("  RpcClientConfig: PASSED")


def test_rpc_client_init():
    """Test RpcClient initialization"""
    from dex_adapter_universal.infra import RpcClient, RpcClientConfig

    print("Testing RpcClient Init...")

    # Single endpoint
    client1 = RpcClient("https://api.mainnet-beta.solana.com")
    assert len(client1._endpoints) == 1

    # Multiple endpoints
    client2 = RpcClient([
        "https://api.mainnet-beta.solana.com",
        "https://api.devnet.solana.com",
    ])
    assert len(client2._endpoints) == 2

    # With config
    config = RpcClientConfig(timeout_seconds=60)
    client3 = RpcClient("https://api.mainnet-beta.solana.com", config)
    assert client3._config.timeout_seconds == 60

    print("  RpcClient Init: PASSED")


def test_signer_protocol():
    """Test Signer protocol"""
    from dex_adapter_universal.infra import Signer

    print("Testing Signer Protocol...")

    # Check protocol has required methods
    assert hasattr(Signer, "pubkey")
    assert hasattr(Signer, "sign")
    assert hasattr(Signer, "sign_transaction")

    print("  Signer Protocol: PASSED")


def test_local_signer():
    """Test LocalSigner"""
    from dex_adapter_universal.infra import LocalSigner

    print("Testing LocalSigner...")

    # Create with random keypair (for testing)
    try:
        from solders.keypair import Keypair
        keypair = Keypair()
        signer = LocalSigner(keypair)

        assert len(signer.pubkey) > 0
        assert signer._keypair == keypair

        print("  LocalSigner: PASSED")
    except ImportError:
        print("  LocalSigner: SKIPPED (solders not installed)")


def test_create_signer():
    """Test create_signer factory"""
    from dex_adapter_universal.infra import create_signer, LocalSigner

    print("Testing create_signer...")

    # Local signer (requires solders)
    try:
        from solders.keypair import Keypair
        keypair = Keypair()
        signer = create_signer(keypair=keypair)
        assert isinstance(signer, LocalSigner)
        assert len(signer.pubkey) > 0
        print("  create_signer: PASSED")
    except ImportError:
        print("  create_signer: SKIPPED (solders not installed)")


def test_tx_builder_init():
    """Test TxBuilder initialization"""
    from dex_adapter_universal.infra import TxBuilder, RpcClient

    print("Testing TxBuilder Init...")

    # Create mock components
    rpc = RpcClient("https://api.mainnet-beta.solana.com")

    # Create signer
    try:
        from solders.keypair import Keypair
        from dex_adapter_universal.infra import LocalSigner
        signer = LocalSigner(Keypair())

        builder = TxBuilder(rpc, signer)
        assert builder._rpc == rpc
        assert builder._signer == signer

        print("  TxBuilder Init: PASSED")
    except ImportError:
        print("  TxBuilder Init: SKIPPED (solders not installed)")


def test_tx_config():
    """Test TxBuilderConfig dataclass"""
    from dex_adapter_universal.infra import TxBuilderConfig

    print("Testing TxBuilderConfig...")

    # Default - values come from environment/config, just verify they exist and are the right type
    config1 = TxBuilderConfig()
    assert isinstance(config1.compute_units, int), "compute_units should be int"
    assert isinstance(config1.compute_unit_price, int), "compute_unit_price should be int"
    assert config1.compute_units > 0, "compute_units should be positive"
    assert config1.compute_unit_price >= 0, "compute_unit_price should be non-negative"

    # Custom - verify overrides work
    config2 = TxBuilderConfig(
        compute_units=400000,
        compute_unit_price=50000,
        skip_preflight=True,
    )
    assert config2.compute_units == 400000, "Custom compute_units should work"
    assert config2.compute_unit_price == 50000, "Custom compute_unit_price should work"
    assert config2.skip_preflight == True, "Custom skip_preflight should work"

    print("  TxBuilderConfig: PASSED")


def main():
    """Run all infrastructure tests"""
    print("=" * 60)
    print("DEX Adapter Infrastructure Tests")
    print("=" * 60)

    tests = [
        test_rpc_config,
        test_rpc_client_init,
        test_signer_protocol,
        test_local_signer,
        test_create_signer,
        test_tx_builder_init,
        test_tx_config,
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
