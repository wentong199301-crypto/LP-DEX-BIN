"""
Uniswap Unified Liquidity Adapter

Provides liquidity management functionality via Uniswap V3 and V4.
Automatically detects pool version and routes calls accordingly.

Note: Swap operations should use 1inch adapter instead.

Usage:
    from dex_adapter.protocols.uniswap import UniswapAdapter
    from dex_adapter.infra.evm_signer import EVMSigner
    from dex_adapter.types.price import PriceRange

    # Create signer
    signer = EVMSigner.from_env()

    # Create adapter for Ethereum
    adapter = UniswapAdapter(chain_id=1, signer=signer)

    # Get pool (auto-detects V3/V4, defaults to V3)
    pool = adapter.get_pool("WETH", "USDC", fee=3000)

    # Or specify version explicitly
    pool_v4 = adapter.get_pool("ETH", "USDC", fee=3000, version="v4")

    # Open position
    result = adapter.open_position(
        pool=pool,
        price_range=PriceRange.percent(Decimal("0.05")),
        amount0=Decimal("1.0"),
    )

    # List positions (can filter by version)
    all_positions = adapter.get_positions()
    v3_positions = adapter.get_positions(version="v3")

    # Close position
    result = adapter.close_position(position)
"""

from .adapter import UniswapAdapter, PoolVersion
from .api import (
    UNISWAP_V3_POSITION_MANAGER_ADDRESSES,
    UNISWAP_V3_FACTORY_ADDRESSES,
    UNISWAP_V4_POOL_MANAGER_ADDRESSES,
    UNISWAP_V4_POSITION_MANAGER_ADDRESSES,
    UNISWAP_FEE_TIERS,
    TICK_SPACING_BY_FEE,
    UNISWAP_SUPPORTED_CHAINS,
    CHAIN_NAMES,
    NATIVE_ETH_ADDRESS,
    NO_HOOKS_ADDRESS,
)

__all__ = [
    "UniswapAdapter",
    "PoolVersion",
    "UNISWAP_V3_POSITION_MANAGER_ADDRESSES",
    "UNISWAP_V3_FACTORY_ADDRESSES",
    "UNISWAP_V4_POOL_MANAGER_ADDRESSES",
    "UNISWAP_V4_POSITION_MANAGER_ADDRESSES",
    "UNISWAP_FEE_TIERS",
    "TICK_SPACING_BY_FEE",
    "UNISWAP_SUPPORTED_CHAINS",
    "CHAIN_NAMES",
    "NATIVE_ETH_ADDRESS",
    "NO_HOOKS_ADDRESS",
]
