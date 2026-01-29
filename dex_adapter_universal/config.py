"""
Configuration management for DEX Adapter

Loads settings from environment variables and .env file.
Includes logging configuration with file output and correlation ID support.
"""

import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List

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
    url: str = field(default_factory=lambda: _get_env("SOLANA_RPC_URL", ""))
    timeout_seconds: float = field(default_factory=lambda: _get_env_float("RPC_TIMEOUT_SECONDS", 30.0))
    max_retries: int = field(default_factory=lambda: _get_env_int("RPC_MAX_RETRIES", 3))
    commitment: str = field(default_factory=lambda: _get_env("RPC_COMMITMENT", "confirmed"))


@dataclass
class SignerConfig:
    """Signer configuration for local keypair signing"""
    keypair_path: str = field(default_factory=lambda: _get_env("SOLANA_KEYPAIR_PATH", ""))


@dataclass
class TxConfig:
    """Transaction configuration"""
    compute_units: int = field(default_factory=lambda: _get_env_int("TX_COMPUTE_UNITS", 200_000))
    # Minimum viable priority fee for swap operations (1000 microlamports/CU)
    compute_unit_price: int = field(default_factory=lambda: _get_env_int("TX_COMPUTE_UNIT_PRICE", 1_000))
    # LP operations need higher compute budget (Meteora needs 500K+ CUs for wide ranges)
    lp_compute_units: int = field(default_factory=lambda: _get_env_int("TX_LP_COMPUTE_UNITS", 600_000))
    # Minimum viable priority fee for LP operations (1000 microlamports/CU)
    # Note: May need to increase during high network congestion
    lp_compute_unit_price: int = field(default_factory=lambda: _get_env_int("TX_LP_COMPUTE_UNIT_PRICE", 1_000))
    confirmation_timeout: float = field(default_factory=lambda: _get_env_float("TX_CONFIRMATION_TIMEOUT", 30.0))
    # Retry settings - separate for swap and LP operations
    swap_max_retries: int = field(default_factory=lambda: _get_env_int("TX_SWAP_MAX_RETRIES", 5))
    lp_max_retries: int = field(default_factory=lambda: _get_env_int("TX_LP_MAX_RETRIES", 3))
    retry_delay: float = field(default_factory=lambda: _get_env_float("TX_RETRY_DELAY", 2.0))
    skip_preflight: bool = field(default_factory=lambda: _get_env_bool("TX_SKIP_PREFLIGHT", False))
    preflight_commitment: str = field(default_factory=lambda: _get_env("TX_PREFLIGHT_COMMITMENT", "confirmed"))


@dataclass
class JupiterConfig:
    """Jupiter API configuration (URLs must be configured in .env)"""
    quote_url: str = field(default_factory=lambda: _get_env("JUPITER_QUOTE_URL", ""))
    swap_url: str = field(default_factory=lambda: _get_env("JUPITER_SWAP_URL", ""))
    token_list_url: str = field(default_factory=lambda: _get_env("JUPITER_TOKEN_LIST_URL", ""))
    timeout: float = field(default_factory=lambda: _get_env_float("JUPITER_TIMEOUT", 30.0))
    # Note: Retry uses global config.tx.swap_max_retries and config.tx.retry_delay


@dataclass
class OneInchConfig:
    """1inch API configuration for EVM chains (ETH/BSC) - URLs must be configured in .env"""
    # API settings
    base_url: str = field(default_factory=lambda: _get_env("ONEINCH_BASE_URL", ""))
    api_key: Optional[str] = field(default_factory=lambda: _get_env("ONEINCH_API_KEY", None))
    timeout: float = field(default_factory=lambda: _get_env_float("ONEINCH_TIMEOUT", 30.0))
    # Note: Retry uses global config.tx.swap_max_retries and config.tx.retry_delay

    # Chain-specific RPC URLs (must be configured in .env)
    eth_rpc_url: str = field(default_factory=lambda: _get_env("ETH_RPC_URL", ""))
    bsc_rpc_url: str = field(default_factory=lambda: _get_env("BSC_RPC_URL", ""))

    # Chain IDs (constants)
    eth_chain_id: int = 1
    bsc_chain_id: int = 56

    # Gas settings
    # Multiplier for gas limit estimates (not gas price) to provide buffer
    gas_limit_multiplier: float = field(default_factory=lambda: _get_env_float("ONEINCH_GAS_LIMIT_MULTIPLIER", 1.1))
    # Priority fee (tip) in gwei for ETH - minimum viable value (BSC uses chain gas price)
    priority_fee_gwei: float = field(default_factory=lambda: _get_env_float("ONEINCH_PRIORITY_FEE_GWEI", 0.1))
    # Base fee multiplier for maxFeePerGas (1.0 = no markup, use exact base fee)
    base_fee_multiplier: float = field(default_factory=lambda: _get_env_float("ONEINCH_BASE_FEE_MULTIPLIER", 1.0))
    # Gas price multiplier for BSC legacy transactions (1.0 = use network suggested price)
    bsc_gas_price_multiplier: float = field(default_factory=lambda: _get_env_float("ONEINCH_BSC_GAS_PRICE_MULTIPLIER", 1.0))


@dataclass
class PancakeSwapConfig:
    """PancakeSwap API configuration for BSC only - URLs must be configured in .env"""
    # API settings
    base_url: str = field(default_factory=lambda: _get_env("PANCAKESWAP_BASE_URL", ""))
    timeout: float = field(default_factory=lambda: _get_env_float("PANCAKESWAP_TIMEOUT", 30.0))
    # Note: LP retry uses global config.tx.lp_max_retries (default: 3)

    # BSC RPC URL (must be configured in .env)
    bsc_rpc_url: str = field(default_factory=lambda: _get_env("BSC_RPC_URL", ""))

    # Chain ID (BSC only)
    bsc_chain_id: int = 56

    # Gas settings
    gas_limit_multiplier: float = field(default_factory=lambda: _get_env_float("PANCAKESWAP_GAS_LIMIT_MULTIPLIER", 1.2))
    # Priority fee (tip) in gwei for ETH - minimum viable value (BSC uses chain gas price)
    priority_fee_gwei: float = field(default_factory=lambda: _get_env_float("PANCAKESWAP_PRIORITY_FEE_GWEI", 0.1))
    # Base fee multiplier for maxFeePerGas (1.0 = no markup)
    base_fee_multiplier: float = field(default_factory=lambda: _get_env_float("PANCAKESWAP_BASE_FEE_MULTIPLIER", 1.0))


@dataclass
class UniswapConfig:
    """Uniswap V3/V4 configuration for Ethereum only"""
    # Timeout settings
    timeout: float = field(default_factory=lambda: _get_env_float("UNISWAP_TIMEOUT", 30.0))
    # Note: LP retry uses global config.tx.lp_max_retries (default: 3)

    # Ethereum RPC URL (must be configured in .env)
    eth_rpc_url: str = field(default_factory=lambda: _get_env("ETH_RPC_URL", ""))

    # Chain ID (Ethereum only)
    eth_chain_id: int = 1

    # Gas settings
    gas_limit_multiplier: float = field(default_factory=lambda: _get_env_float("UNISWAP_GAS_LIMIT_MULTIPLIER", 1.2))
    # Priority fee (tip) in gwei - minimum viable value
    priority_fee_gwei: float = field(default_factory=lambda: _get_env_float("UNISWAP_PRIORITY_FEE_GWEI", 0.1))
    # Base fee multiplier for maxFeePerGas (1.0 = no markup)
    base_fee_multiplier: float = field(default_factory=lambda: _get_env_float("UNISWAP_BASE_FEE_MULTIPLIER", 1.0))


@dataclass
class SolanaConfig:
    """Solana-specific configuration"""
    # WSOL wrap safety buffer in lamports (covers rent-exempt minimum and rounding)
    wsol_wrap_buffer: int = field(default_factory=lambda: _get_env_int("SOLANA_WSOL_WRAP_BUFFER", 10_000))


@dataclass
class EVMConfig:
    """EVM-specific configuration (shared by Uniswap, PancakeSwap, 1inch)"""
    # Transaction deadline in seconds (default: 20 minutes)
    tx_deadline_seconds: int = field(default_factory=lambda: _get_env_int("EVM_TX_DEADLINE_SECONDS", 1200))
    # Default gas limit for LP operations
    lp_gas_limit: int = field(default_factory=lambda: _get_env_int("EVM_LP_GAS_LIMIT", 500_000))


def _get_default_log_path() -> str:
    """Get default log file path under dex_adapter_universal/log/ with UTC timestamp"""
    from datetime import datetime, timezone
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_dir = Path(__file__).parent / "log"
    return str(log_dir / f"dex_adapter_{timestamp}.log")


@dataclass
class LoggingConfig:
    """
    Logging configuration with file output and correlation ID support.

    Default log location: dex_adapter_universal/log/dex_adapter.log

    Environment variables:
        LOG_FILE: Path to log file (overrides default)
        LOG_LEVEL: DEBUG, INFO, WARNING, ERROR, CRITICAL (default: INFO)
        LOG_FORMAT: Custom log format string
        LOG_CONSOLE: Enable console output (default: true)
        LOG_MAX_BYTES: Max log file size before rotation (default: 10MB)
        LOG_BACKUP_COUNT: Number of backup files to keep (default: 5)

    Example .env:
        LOG_LEVEL=DEBUG
        LOG_CONSOLE=true
    """
    # Log file path (defaults to dex_adapter_universal/log/dex_adapter.log)
    log_file: str = field(default_factory=lambda: _get_env("LOG_FILE", _get_default_log_path()))

    # Log level
    log_level: str = field(default_factory=lambda: _get_env("LOG_LEVEL", "INFO"))

    # Log format with correlation ID support
    # Available placeholders: %(correlation_id)s, %(asctime)s, %(name)s, %(levelname)s, %(message)s
    log_format: str = field(default_factory=lambda: _get_env(
        "LOG_FORMAT",
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    ))

    # Console output (in addition to file)
    console_output: bool = field(default_factory=lambda: _get_env_bool("LOG_CONSOLE", True))

    # File rotation settings
    max_bytes: int = field(default_factory=lambda: _get_env_int("LOG_MAX_BYTES", 10 * 1024 * 1024))  # 10MB
    backup_count: int = field(default_factory=lambda: _get_env_int("LOG_BACKUP_COUNT", 5))

    @property
    def level(self) -> int:
        """Get numeric log level"""
        return getattr(logging, self.log_level.upper(), logging.INFO)


@dataclass
class TradingConfig:
    """Default trading parameters"""
    default_slippage_bps: int = field(default_factory=lambda: _get_env_int("DEFAULT_SLIPPAGE_BPS", 30))
    default_lp_slippage_bps: int = field(default_factory=lambda: _get_env_int("DEFAULT_LP_SLIPPAGE_BPS", 100))


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
    solana: SolanaConfig = field(default_factory=SolanaConfig)
    evm: EVMConfig = field(default_factory=EVMConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

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


def setup_logging(
    log_config: Optional[LoggingConfig] = None,
    logger_name: str = "dex_adapter_universal",
) -> logging.Logger:
    """
    Set up logging based on configuration.

    Creates handlers for file and/or console output with optional rotation.
    The log file directory is created automatically if it doesn't exist.

    Args:
        log_config: Logging configuration (uses global config if None)
        logger_name: Name of the logger to configure (default: dex_adapter_universal)

    Returns:
        Configured logger instance

    Example:
        # Using environment variables
        # .env:
        #   LOG_FILE=logs/dex_adapter.log
        #   LOG_LEVEL=DEBUG
        #   LOG_CONSOLE=true

        from dex_adapter_universal.config import setup_logging
        logger = setup_logging()

        # Or with custom config
        from dex_adapter_universal.config import LoggingConfig, setup_logging
        log_config = LoggingConfig(
            log_file="my_app.log",
            log_level="DEBUG",
            console_output=True,
        )
        logger = setup_logging(log_config)

    Log file location:
        - Relative paths are relative to the current working directory
        - Absolute paths are used as-is
        - Parent directories are created automatically
    """
    if log_config is None:
        log_config = config.logging

    # Get or create logger
    logger = logging.getLogger(logger_name)
    logger.setLevel(log_config.level)

    # Close and remove existing handlers to avoid duplicates on reload
    # Must close handlers before removing to flush buffers and release file handles
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)

    # Create formatter
    formatter = logging.Formatter(log_config.log_format)

    handlers: List[logging.Handler] = []

    # File handler with rotation
    if log_config.log_file:
        from logging.handlers import RotatingFileHandler

        # Create log directory if needed
        log_path = Path(log_config.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            log_config.log_file,
            maxBytes=log_config.max_bytes,
            backupCount=log_config.backup_count,
            encoding='utf-8',
        )
        file_handler.setLevel(log_config.level)
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    # Console handler
    if log_config.console_output:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_config.level)
        console_handler.setFormatter(formatter)
        handlers.append(console_handler)

    # Add handlers to logger
    for handler in handlers:
        logger.addHandler(handler)

    # Also configure child loggers (modules)
    # This ensures all dex_adapter_universal.* loggers use the same config
    for name in [
        f"{logger_name}.infra",
        f"{logger_name}.modules",
        f"{logger_name}.protocols",
    ]:
        child_logger = logging.getLogger(name)
        child_logger.setLevel(log_config.level)
        # Child loggers inherit handlers from parent, no need to add again

    # Log initial message if file logging is enabled
    if log_config.log_file:
        logger.info(f"Logging initialized: file={log_config.log_file}, level={log_config.log_level}")

    return logger


# Convenience function for quick setup
def enable_file_logging(
    log_file: Optional[str] = None,
    level: str = "INFO",
    console: bool = True,
) -> logging.Logger:
    """
    Quick setup for file logging.

    Args:
        log_file: Path to log file (defaults to dex_adapter_universal/log/dex_adapter.log)
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        console: Also output to console

    Returns:
        Configured logger

    Example:
        from dex_adapter_universal.config import enable_file_logging

        # Enable file logging with defaults (saves to dex_adapter_universal/log/)
        logger = enable_file_logging()

        # Or customize
        logger = enable_file_logging(
            log_file="my_app.log",
            level="DEBUG",
            console=False
        )
    """
    if log_file is None:
        # Use the global config's log_file to keep consistent timestamp
        log_file = config.logging.log_file

    log_config = LoggingConfig(
        log_file=log_file,
        log_level=level,
        console_output=console,
    )
    return setup_logging(log_config)
