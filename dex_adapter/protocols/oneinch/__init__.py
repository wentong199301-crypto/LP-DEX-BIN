"""
1inch Swap Protocol Adapter

Provides swap functionality via 1inch aggregator for ETH and BSC chains.

Usage:
    from dex_adapter.protocols.oneinch import OneInchAdapter, OneInchAPI
    from dex_adapter.infra.evm_signer import EVMSigner

    # Create signer
    signer = EVMSigner.from_env()

    # Create adapter for Ethereum
    adapter = OneInchAdapter(chain_id=1, signer=signer)

    # Get quote
    quote = adapter.quote("ETH", "USDC", Decimal("1.0"))

    # Execute swap
    result = adapter.swap("ETH", "USDC", Decimal("1.0"))
"""

from .adapter import OneInchAdapter
from .api import OneInchAPI

__all__ = [
    "OneInchAdapter",
    "OneInchAPI",
]
