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
from decimal import Decimal
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
    from dex_adapter_universal import DexClient

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


def skip_if_no_evm_config():
    """Check if EVM config is available, return skip message if not"""
    if not os.getenv("EVM_PRIVATE_KEY"):
        return "Missing EVM_PRIVATE_KEY environment variable"
    try:
        from web3 import Web3
    except ImportError:
        return "web3 not installed. Install with: pip install web3"
    return None


def get_evm_balance(adapter, token: str):
    """
    Get EVM token balance using WalletModule.

    This test helper uses WalletModule for balance queries.

    Args:
        adapter: EVM adapter with _chain_id, _signer, _web3 attributes
        token: Token symbol or address

    Returns:
        Balance in UI units (Decimal)
    """
    from dex_adapter_universal.types.evm_tokens import resolve_token_address, get_token_decimals, get_native_symbol

    web3 = adapter._web3
    address = adapter._signer.address
    chain_id = adapter._chain_id

    # Check if native token (ETH, BNB)
    native_symbol = get_native_symbol(chain_id)
    if token.upper() == native_symbol.upper():
        balance_wei = web3.eth.get_balance(address)
        return Decimal(balance_wei) / Decimal(10 ** 18)

    # ERC20 token
    token_address = resolve_token_address(token, chain_id)
    decimals = get_token_decimals(token, chain_id)

    # Minimal ERC20 ABI for balanceOf
    erc20_abi = [{"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"}]

    contract = web3.eth.contract(address=web3.to_checksum_address(token_address), abi=erc20_abi)
    balance = contract.functions.balanceOf(address).call()
    return Decimal(balance) / Decimal(10 ** decimals)


def get_native_balance(adapter):
    """Get native token balance (ETH/BNB) for an adapter using WalletModule"""
    from dex_adapter_universal.types.evm_tokens import get_native_symbol
    return get_evm_balance(adapter, get_native_symbol(adapter._chain_id))


def get_token_balance(adapter, token: str):
    """Get ERC20 token balance for an adapter using WalletModule"""
    return get_evm_balance(adapter, token)


@pytest.fixture(scope="module")
def pancakeswap_adapter():
    """Create PancakeSwapAdapter fixture for tests (BSC)"""
    skip_msg = skip_if_no_evm_config()
    if skip_msg:
        pytest.skip(skip_msg)

    from dex_adapter_universal.protocols.pancakeswap import PancakeSwapAdapter
    from dex_adapter_universal.infra.evm_signer import EVMSigner

    signer = EVMSigner.from_env()
    return PancakeSwapAdapter(chain_id=56, signer=signer)


@pytest.fixture(scope="module")
def uniswap_adapter():
    """Create UniswapAdapter fixture for tests (Ethereum)"""
    skip_msg = skip_if_no_evm_config()
    if skip_msg:
        pytest.skip(skip_msg)

    from dex_adapter_universal.protocols.uniswap import UniswapAdapter
    from dex_adapter_universal.infra.evm_signer import EVMSigner

    signer = EVMSigner.from_env()
    return UniswapAdapter(chain_id=1, signer=signer)


# Alias for backwards compatibility with test files using 'adapter' parameter
@pytest.fixture(scope="module")
def adapter(request):
    """
    Generic adapter fixture that selects based on test file name.
    - test_liquidity_pancakeswap.py -> PancakeSwapAdapter
    - test_liquidity_uniswap.py -> UniswapAdapter
    """
    test_file = request.fspath.basename

    if "pancakeswap" in test_file:
        skip_msg = skip_if_no_evm_config()
        if skip_msg:
            pytest.skip(skip_msg)

        from dex_adapter_universal.protocols.pancakeswap import PancakeSwapAdapter
        from dex_adapter_universal.infra.evm_signer import EVMSigner

        signer = EVMSigner.from_env()
        return PancakeSwapAdapter(chain_id=56, signer=signer)

    elif "uniswap" in test_file:
        skip_msg = skip_if_no_evm_config()
        if skip_msg:
            pytest.skip(skip_msg)

        from dex_adapter_universal.protocols.uniswap import UniswapAdapter
        from dex_adapter_universal.infra.evm_signer import EVMSigner

        signer = EVMSigner.from_env()
        return UniswapAdapter(chain_id=1, signer=signer)

    else:
        pytest.skip(f"No adapter configured for {test_file}")
