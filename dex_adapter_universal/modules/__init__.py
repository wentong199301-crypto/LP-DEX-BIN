"""
Functional modules for DexClient

Provides high-level operations:
- WalletModule: Balance queries, token accounts
- MarketModule: Pool information, prices
- SwapModule: Multi-chain token swaps (Solana/Jupiter, ETH/BSC via 1inch)
- LiquidityModule: LP operations
"""

from .wallet import WalletModule
from .market import MarketModule
from .swap import SwapModule, Chain
from .liquidity import LiquidityModule

__all__ = [
    # Core modules
    "WalletModule",
    "MarketModule",
    "SwapModule",
    "LiquidityModule",
    # Chain enum
    "Chain",
]
