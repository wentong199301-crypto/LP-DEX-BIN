"""
Protocol adapter registry

Provides centralized registration and lookup for protocol adapters.
"""

from typing import Dict, Optional, Type, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from .base import ProtocolAdapter
    from ..infra import RpcClient

from ..errors import ConfigurationError

logger = logging.getLogger(__name__)


class ProtocolRegistry:
    """
    Registry for protocol adapters

    Manages adapter registration and instantiation.
    Supports lazy loading of adapters.

    Usage:
        # Register adapter class
        ProtocolRegistry.register("raydium", RaydiumAdapter)

        # Get adapter instance (creates new instance each time)
        adapter = ProtocolRegistry.get("raydium", rpc_client)

        # List available protocols
        protocols = ProtocolRegistry.list()
    """

    # Registered adapter classes
    _adapters: Dict[str, Type["ProtocolAdapter"]] = {}

    @classmethod
    def register(cls, name: str, adapter_class: Type["ProtocolAdapter"]):
        """
        Register a protocol adapter class

        Args:
            name: Protocol name (e.g., "raydium", "meteora")
            adapter_class: Adapter class (not instance)
        """
        cls._adapters[name.lower()] = adapter_class
        logger.debug(f"Registered protocol adapter: {name}")

    @classmethod
    def get(
        cls,
        name: str,
        rpc: "RpcClient",
    ) -> "ProtocolAdapter":
        """
        Get adapter instance for protocol (creates new instance each time)

        Args:
            name: Protocol name
            rpc: RPC client

        Returns:
            Protocol adapter instance

        Raises:
            ValueError: If protocol not registered
        """
        name_lower = name.lower()

        if name_lower not in cls._adapters:
            # Try lazy loading
            cls._try_load_adapter(name_lower)

        if name_lower not in cls._adapters:
            available = ", ".join(cls._adapters.keys()) or "none"
            raise ConfigurationError.invalid(
                "protocol", f"Unknown protocol: {name}. Available protocols: {available}"
            )

        # Create new instance
        adapter_class = cls._adapters[name_lower]
        return adapter_class(rpc)

    @classmethod
    def list(cls) -> list[str]:
        """List registered protocol names"""
        # Ensure adapters are loaded
        cls._ensure_loaded()
        return list(cls._adapters.keys())

    @classmethod
    def is_registered(cls, name: str) -> bool:
        """Check if protocol is registered"""
        return name.lower() in cls._adapters

    @classmethod
    def _try_load_adapter(cls, name: str):
        """Try to lazy load an adapter module"""
        try:
            if name == "raydium":
                from .raydium import RaydiumAdapter
                cls.register("raydium", RaydiumAdapter)
            elif name == "meteora":
                from .meteora import MeteoraAdapter
                cls.register("meteora", MeteoraAdapter)
            # Note: Jupiter is not registered here because it's a swap aggregator,
            # not a liquidity protocol. It doesn't implement ProtocolAdapter.
            # Access Jupiter via SwapModule instead.
        except ImportError as e:
            logger.warning(f"Failed to load adapter '{name}': {e}")
        except Exception as e:
            # Catch runtime errors during import (syntax errors, missing dependencies, etc.)
            logger.error(f"Error loading adapter '{name}': {type(e).__name__}: {e}")

    @classmethod
    def _ensure_loaded(cls):
        """Ensure all available adapters are loaded"""
        # Only load LP protocol adapters (not Jupiter - it's a swap aggregator)
        for name in ["raydium", "meteora"]:
            if name not in cls._adapters:
                cls._try_load_adapter(name)


def get_adapter(name: str, rpc: "RpcClient") -> "ProtocolAdapter":
    """
    Convenience function to get adapter

    Args:
        name: Protocol name
        rpc: RPC client

    Returns:
        Protocol adapter instance
    """
    return ProtocolRegistry.get(name, rpc)


def register_adapter(name: str, adapter_class: Type["ProtocolAdapter"]):
    """
    Convenience function to register adapter

    Args:
        name: Protocol name
        adapter_class: Adapter class
    """
    ProtocolRegistry.register(name, adapter_class)
