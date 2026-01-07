"""
Shared configuration and fixtures for module integration tests.

WARNING: These tests execute real transactions and spend real tokens!

Environment Variables:
    SOLANA_RPC_URL: RPC endpoint URL (required)
    SOLANA_PRIVATE_KEY: Base58 encoded private key (required if no keypair path)
    SOLANA_KEYPAIR_PATH: Path to keypair JSON file (alternative to private key)
"""

import os
import sys
from pathlib import Path

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Load .env file
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass


def get_env_or_fail(key: str) -> str:
    """Get required environment variable or raise error"""
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(
            f"Missing required environment variable: {key}\n"
            f"Please set {key} in your .env file or environment."
        )
    return value


def get_rpc_url() -> str:
    """Get Solana RPC URL from environment"""
    return get_env_or_fail("SOLANA_RPC_URL")


def get_keypair():
    """
    Get Keypair from environment.

    Tries in order:
    1. SOLANA_PRIVATE_KEY - base58 encoded private key
    2. SOLANA_KEYPAIR_PATH - path to keypair JSON file
    """
    from solders.keypair import Keypair

    # Try private key first
    private_key = os.getenv("SOLANA_PRIVATE_KEY")
    if private_key:
        try:
            # Try base58 decode
            import base58
            key_bytes = base58.b58decode(private_key)
            return Keypair.from_bytes(key_bytes)
        except Exception:
            # Try as raw bytes list (JSON array format)
            try:
                import json
                key_bytes = bytes(json.loads(private_key))
                return Keypair.from_bytes(key_bytes)
            except Exception as e:
                raise ValueError(f"Invalid SOLANA_PRIVATE_KEY format: {e}")

    # Try keypair path
    keypair_path = os.getenv("SOLANA_KEYPAIR_PATH")
    if keypair_path:
        path = Path(keypair_path)
        if not path.exists():
            raise FileNotFoundError(f"Keypair file not found: {keypair_path}")

        import json
        with open(path) as f:
            key_bytes = bytes(json.load(f))
        return Keypair.from_bytes(key_bytes)

    raise EnvironmentError(
        "No wallet configured. Set either:\n"
        "  SOLANA_PRIVATE_KEY - base58 encoded private key\n"
        "  SOLANA_KEYPAIR_PATH - path to keypair JSON file"
    )


def create_client():
    """Create DexClient with live RPC and real wallet"""
    from dex_adapter import DexClient

    rpc_url = get_rpc_url()
    keypair = get_keypair()

    return DexClient(rpc_url=rpc_url, keypair=keypair)


def skip_if_no_config():
    """Check if required config is available, return skip message if not"""
    try:
        get_rpc_url()
        get_keypair()
        return None
    except (EnvironmentError, FileNotFoundError) as e:
        return str(e)


# Pytest fixtures
@pytest.fixture(scope="module")
def client():
    """Create DexClient fixture for tests"""
    skip_msg = skip_if_no_config()
    if skip_msg:
        pytest.skip(skip_msg)
    return create_client()
