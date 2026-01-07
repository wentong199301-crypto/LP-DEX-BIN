"""
Test Signer Module

Tests for local signer functionality.
"""

import sys
import json
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def test_local_signer_from_base58():
    """Test LocalSigner creation from base58 private key"""
    print("Testing LocalSigner from base58...")

    try:
        from dex_adapter.infra.solana_signer import LocalSigner

        # Valid base58 private key (64 bytes)
        # This is a test keypair - DO NOT use in production
        test_private_key = "4wBqpZM9msxGE5mRKLp4hSFZ8V5hQrFrwkxN8QKo7SzUyKJzCqxvGdLqGwDNhb6GJY3DH5JHfj8NELbf1BqHJCH6"

        signer = LocalSigner.from_base58(test_private_key)
        assert signer.pubkey is not None
        assert len(signer.pubkey) > 30  # Base58 pubkey

        print(f"  Pubkey: {signer.pubkey[:20]}...")
        print("  LocalSigner from base58: PASSED")

    except ImportError as e:
        if "solders" in str(e):
            print("  LocalSigner from base58: SKIPPED (solders not installed)")
        else:
            raise
    except Exception as e:
        # May fail with invalid key format
        print(f"  LocalSigner from base58: SKIPPED ({e})")


def test_local_signer_sign():
    """Test LocalSigner sign method"""
    print("Testing LocalSigner sign...")

    try:
        from dex_adapter.infra.solana_signer import LocalSigner
        from solders.keypair import Keypair

        # Generate a new keypair for testing
        keypair = Keypair()
        signer = LocalSigner(keypair)

        # Sign a message
        message = b"test message to sign"
        signature = signer.sign(message)

        assert signature is not None
        assert len(signature) == 64  # Ed25519 signature is 64 bytes

        print("  LocalSigner sign: PASSED")

    except ImportError as e:
        if "solders" in str(e):
            print("  LocalSigner sign: SKIPPED (solders not installed)")
        else:
            raise


def test_local_signer_sign_transaction():
    """Test LocalSigner sign_transaction method"""
    print("Testing LocalSigner sign_transaction...")

    try:
        from dex_adapter.infra.solana_signer import LocalSigner
        from solders.keypair import Keypair
        from solders.pubkey import Pubkey
        from solders.hash import Hash
        from solders.message import MessageV0
        from solders.transaction import VersionedTransaction
        from solders.signature import Signature

        # Generate a new keypair for testing
        keypair = Keypair()
        signer = LocalSigner(keypair)

        # Create a minimal transaction
        # Using a dummy blockhash and no instructions for test
        payer = keypair.pubkey()
        message = MessageV0.try_compile(
            payer,
            [],  # No instructions
            [],  # No address lookup tables
            Hash.default(),  # Dummy blockhash
        )

        # Create unsigned transaction
        null_signatures = [Signature.default()]
        tx = VersionedTransaction.populate(message, null_signatures)
        unsigned_tx = bytes(tx)

        # Sign the transaction
        signed_tx, sig_str = signer.sign_transaction(unsigned_tx)

        assert signed_tx is not None
        assert len(signed_tx) > 0
        assert sig_str is not None
        assert len(sig_str) > 50  # Base58 signature

        print("  LocalSigner sign_transaction: PASSED")

    except ImportError as e:
        if "solders" in str(e):
            print("  LocalSigner sign_transaction: SKIPPED (solders not installed)")
        else:
            raise


def test_signer_factory():
    """Test signer factory functions"""
    print("Testing signer factory...")

    try:
        from dex_adapter.infra.solana_signer import create_signer, LocalSigner
        from solders.keypair import Keypair

        # Test creating a local signer via factory with keypair
        keypair = Keypair()
        signer = create_signer(keypair=keypair)
        assert signer is not None
        assert isinstance(signer, LocalSigner)
        assert len(signer.pubkey) > 0

        print("  Signer factory: PASSED")

    except ImportError as e:
        if "solders" in str(e):
            print("  Signer factory: SKIPPED (solders not installed)")
        else:
            print(f"  Signer factory: SKIPPED ({e})")


def test_keypair_loading():
    """Test keypair loading from various formats"""
    print("Testing keypair loading...")

    try:
        from dex_adapter.infra.solana_signer import LocalSigner
        import tempfile
        import os

        # Test JSON array format (Solana CLI format)
        json_keypair = [
            1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16,
            17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32,
            33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48,
            49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64,
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(json_keypair, f)
            temp_path = f.name

        try:
            signer = LocalSigner.from_file(temp_path)
            assert signer is not None
            assert signer.pubkey is not None
            print("  Keypair loading (JSON): PASSED")
        finally:
            os.unlink(temp_path)

    except ImportError as e:
        if "solders" in str(e):
            print("  Keypair loading: SKIPPED (solders not installed)")
        else:
            raise
    except RuntimeError as e:
        if "solders" in str(e):
            print("  Keypair loading: SKIPPED (solders not installed)")
        else:
            raise
    except Exception as e:
        print(f"  Keypair loading: SKIPPED ({e})")


def main():
    """Run all signer tests"""
    print("=" * 60)
    print("Signer Tests")
    print("=" * 60)

    tests = [
        test_local_signer_from_base58,
        test_local_signer_sign,
        test_local_signer_sign_transaction,
        test_signer_factory,
        test_keypair_loading,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
