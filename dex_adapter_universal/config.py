"""
Configuration management for DEX Adapter

Loads settings from environment variables and .env file.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Try to load dotenv for .env file support
try:
    from dotenv import load_dotenv
    _HAS_DOTENV = True
except ImportError:
    _HAS_DOTENV = False


def _load_env_file():
    """Load .env file from project root"""
    if not _HAS_DOTENV:
        return

    # Look for .env in common locations
    current = Path(__file__).parent.parent  # dex_adapter_universal package parent
    env_file = current / ".env"

    if env_file.exists():
        load_dotenv(env_file)


# Load .env on module import
_load_env_file()


def _get_env(key: str, default: Optional[str] = "") -> Optional[str]:
    """Get environment variable with default"""
    value = os.getenv(key)
    if value is None:
        return default
    return value


def _get_env_float(key: str, default: float) -> float:
    """Get environment variable as float"""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        import logging
        logging.getLogger(__name__).warning(
            f"Invalid float value for {key}='{value}', using default={default}"
        )
        return default


def _get_env_int(key: str, default: int) -> int:
    """Get environment variable as int"""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        import logging
        logging.getLogger(__name__).warning(
            f"Invalid int value for {key}='{value}', using default={default}"
        )
        return default


def _get_env_bool(key: str, default: bool) -> bool:
    """Get environment variable as bool"""
    value = os.getenv(key)
    if value is None:
        return default
    return value.lower() in ("true", "1", "yes", "on")


@dataclass
class RpcConfig:
    """RPC client configuration"""
    url: str = field(default_factory=lambda: _get_env("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com"))
    timeout_seconds: float = field(default_factory=lambda: _get_env_float("RPC_TIMEOUT_SECONDS", 30.0))
    max_retries: int = field(default_factory=lambda: _get_env_int("RPC_MAX_RETRIES", 3))
    retry_delay_seconds: float = field(default_factory=lambda: _get_env_float("RPC_RETRY_DELAY_SECONDS", 1.0))
    commitment: str = field(default_factory=lambda: _get_env("RPC_COMMITMENT", "confirmed"))


@dataclass
class SignerConfig:
    """Signer configuration for local keypair signing"""
    keypair_path: str = field(default_factory=lambda: _get_env("SOLANA_KEYPAIR_PATH", ""))


@dataclass
class TxConfig:
    """Transaction configuration"""
    compute_units: int = field(default_factory=lambda: _get_env_int("TX_COMPUTE_UNITS", 200_000))
    compute_unit_price: int = field(default_factory=lambda: _get_env_int("TX_COMPUTE_UNIT_PRICE", 10_000))
    # LP operations need higher compute budget (Meteora needs 500K+ CUs for wide ranges)
    lp_compute_units: int = field(default_factory=lambda: _get_env_int("TX_LP_COMPUTE_UNITS", 600_000))
    # LP operations use higher priority fee for faster confirmation during congestion
    lp_compute_unit_price: int = field(default_factory=lambda: _get_env_int("TX_LP_COMPUTE_UNIT_PRICE", 500_000))
    # Increase default timeout to 90s for better handling of network congestion
    confirmation_timeout: float = field(default_factory=lambda: _get_env_float("TX_CONFIRMATION_TIMEOUT", 90.0))
    max_retries: int = field(default_factory=lambda: _get_env_int("TX_MAX_RETRIES", 3))
    retry_delay: float = field(default_factory=lambda: _get_env_float("TX_RETRY_DELAY", 2.0))
    skip_preflight: bool = field(default_factory=lambda: _get_env_bool("TX_SKIP_PREFLIGHT", False))
    preflight_commitment: str = field(default_factory=lambda: _get_env("TX_PREFLIGHT_COMMITMENT", "confirmed"))


@dataclass
class JupiterConfig:
    """Jupiter API configuration"""
    # Using public.jupiterapi.com as fallback since quote-api.jup.ag may have DNS issues
    # Note: public.jupiterapi.com has a 0.2% platform fee
    quote_url: str = field(default_factory=lambda: _get_env("JUPITER_QUOTE_URL", "https://public.jupiterapi.com/quote"))
    swap_url: str = field(default_factory=lambda: _get_env("JUPITER_SWAP_URL", "https://public.jupiterapi.com/swap"))
    token_list_url: str = field(default_factory=lambda: _get_env("JUPITER_TOKEN_LIST_URL", "https://tokens.jup.ag/tokens?tags=verified"))
    timeout: float = field(default_factory=lambda: _get_env_float("JUPITER_TIMEOUT", 30.0))
    max_retries: int = field(default_factory=lambda: _get_env_int("JUPITER_MAX_RETRIES", 3))


@dataclass
class OneInchConfig:
    """1inch API configuration for EVM chains (ETH/BSC)"""
    # API settings
    base_url: str = field(default_factory=lambda: _get_env("ONEINCH_BASE_URL", "https://api.1inch.dev/swap/v6.0"))
    api_key: Optional[str] = field(default_factory=lambda: _get_env("ONEINCH_API_KEY", None))
    timeout: float = field(default_factory=lambda: _get_env_float("ONEINCH_TIMEOUT", 30.0))
    max_retries: int = field(default_factory=lambda: _get_env_int("ONEINCH_MAX_RETRIES", 3))

    # Chain-specific RPC URLs
    eth_rpc_url: str = field(default_factory=lambda: _get_env("ETH_RPC_URL", "https://eth.llamarpc.com"))
    bsc_rpc_url: str = field(default_factory=lambda: _get_env("BSC_RPC_URL", "https://bsc-dataseed.binance.org"))

    # Chain IDs (constants)
    eth_chain_id: int = 1
    bsc_chain_id: int = 56

    # Gas settings
    # Multiplier for gas limit estimates (not gas price) to provide buffer
    gas_limit_multiplier: float = field(default_factory=lambda: _get_env_float("ONEINCH_GAS_LIMIT_MULTIPLIER", 1.1))


@dataclass
class PancakeSwapConfig:
    """PancakeSwap API configuration for BSC only"""
    # API settings - PancakeSwap has public APIs
    base_url: str = field(default_factory=lambda: _get_env("PANCAKESWAP_BASE_URL", "https://pancakeswap.finance/api/v0"))
    timeout: float = field(default_factory=lambda: _get_env_float("PANCAKESWAP_TIMEOUT", 30.0))
    max_retries: int = field(default_factory=lambda: _get_env_int("PANCAKESWAP_MAX_RETRIES", 3))

    # BSC RPC URL
    bsc_rpc_url: str = field(default_factory=lambda: _get_env("BSC_RPC_URL", "https://bsc-dataseed.binance.org"))

    # Chain ID (BSC only)
    bsc_chain_id: int = 56

    # Gas settings
    gas_limit_multiplier: float = field(default_factory=lambda: _get_env_float("PANCAKESWAP_GAS_LIMIT_MULTIPLIER", 1.2))


@dataclass
class UniswapConfig:
    """Uniswap V3/V4 configuration for Ethereum only"""
    # Timeout settings
    timeout: float = field(default_factory=lambda: _get_env_float("UNISWAP_TIMEOUT", 30.0))
    max_retries: int = field(default_factory=lambda: _get_env_int("UNISWAP_MAX_RETRIES", 3))

    # Ethereum RPC URL
    eth_rpc_url: str = field(default_factory=lambda: _get_env("ETH_RPC_URL", "https://eth.llamarpc.com"))

    # Chain ID (Ethereum only)
    eth_chain_id: int = 1

    # Gas settings
    gas_limit_multiplier: float = field(default_factory=lambda: _get_env_float("UNISWAP_GAS_LIMIT_MULTIPLIER", 1.2))


@dataclass
class TradingConfig:
    """Default trading parameters"""
    default_slippage_bps: int = field(default_factory=lambda: _get_env_int("DEFAULT_SLIPPAGE_BPS", 50))


@dataclass
class Config:
    """
    Main configuration container

    Loads all settings from environment variables and .env file.

    Usage:
        from dex_adapter_universal.config import config

        print(config.rpc.url)
        print(config.jupiter.quote_url)
    """
    rpc: RpcConfig = field(default_factory=RpcConfig)
    signer: SignerConfig = field(default_factory=SignerConfig)
    tx: TxConfig = field(default_factory=TxConfig)
    jupiter: JupiterConfig = field(default_factory=JupiterConfig)
    oneinch: OneInchConfig = field(default_factory=OneInchConfig)
    pancakeswap: PancakeSwapConfig = field(default_factory=PancakeSwapConfig)
    uniswap: UniswapConfig = field(default_factory=UniswapConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)

    @classmethod
    def reload(cls) -> "Config":
        """Reload configuration from environment"""
        _load_env_file()
        return cls()


# Global config instance
config = Config()


def get_config() -> Config:
    """Get global configuration instance"""
    return config


def reload_config() -> Config:
    """Reload and return new configuration"""
    global config
    config = Config.reload()
    return config
