"""
PancakeSwap V3 Liquidity Adapter

Provides liquidity management functionality via PancakeSwap V3 for BSC only.
Note: Swap operations should use 1inch adapter instead.

Usage:
    from dex_adapter.protocols.pancakeswap import PancakeSwapAdapter
    from dex_adapter.infra.evm_signer import EVMSigner
    from dex_adapter.types.price import PriceRange

    # Create signer
    signer = EVMSigner.from_env()

    # Create adapter for BSC
    adapter = PancakeSwapAdapter(chain_id=56, signer=signer)

    # Get pool
    pool = adapter.get_pool("WBNB", "USDT", fee=2500)

    # Open position
    result = adapter.open_position(
        pool=pool,
        price_range=PriceRange.percent(Decimal("0.05")),
        amount0=Decimal("1.0"),
    )

    # List positions
    positions = adapter.get_positions()

    # Close position
    result = adapter.close_position(position)
"""

from .adapter import PancakeSwapAdapter
from .api import (
    PANCAKESWAP_POSITION_MANAGER_ADDRESSES,
    PANCAKESWAP_FACTORY_ADDRESSES,
    PANCAKESWAP_SUPPORTED_CHAINS,
    CHAIN_NAMES,
    PANCAKESWAP_FEE_TIERS,
    TICK_SPACING_BY_FEE,
)

__all__ = [
    "PancakeSwapAdapter",
    "PANCAKESWAP_POSITION_MANAGER_ADDRESSES",
    "PANCAKESWAP_FACTORY_ADDRESSES",
    "PANCAKESWAP_SUPPORTED_CHAINS",
    "CHAIN_NAMES",
    "PANCAKESWAP_FEE_TIERS",
    "TICK_SPACING_BY_FEE",
]
