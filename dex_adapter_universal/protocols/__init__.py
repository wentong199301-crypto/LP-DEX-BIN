"""
Protocol adapters for different DEXes

Each protocol adapter implements the ProtocolAdapter interface
to provide unified access to different DEX protocols.
"""

from .base import ProtocolAdapter
from .registry import ProtocolRegistry, get_adapter, register_adapter

__all__ = [
    "ProtocolAdapter",
    "ProtocolRegistry",
    "get_adapter",
    "register_adapter",
]
