"""
Pool type definitions
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from .common import Token


@dataclass
class Pool:
    """
    DEX liquidity pool information

    Attributes:
        address: Pool address (base58)
        dex: DEX protocol name ("raydium" | "meteora")
        symbol: Trading pair symbol (e.g., "SOL/USDC")
        token0: Base token (token X in Meteora)
        token1: Quote token (token Y in Meteora)
        price: Current price of token0 in terms of token1
        tvl_usd: Total value locked in USD
        fee_rate: Trading fee rate (e.g., 0.0025 for 0.25%)
        tick_spacing: CLMM tick spacing (Raydium)
        current_tick: Current tick index (Raydium)
        bin_step: DLMM bin step in basis points (Meteora)
        active_bin_id: Current active bin ID (Meteora)
        sqrt_price_x64: Square root price in X64 format (Raydium)
        protocol_fee_rate: Protocol fee portion
        fund_fee_rate: Fund fee portion (Meteora)
    """
    address: str
    dex: str
    symbol: str
    token0: Token
    token1: Token
    price: Decimal
    tvl_usd: Decimal = Decimal(0)
    fee_rate: Decimal = Decimal("0.0025")

    # Raydium CLMM specific
    tick_spacing: Optional[int] = None
    current_tick: Optional[int] = None
    sqrt_price_x64: Optional[int] = None

    # Meteora DLMM specific
    bin_step: Optional[int] = None
    active_bin_id: Optional[int] = None

    # Fee breakdown
    protocol_fee_rate: Decimal = Decimal(0)
    fund_fee_rate: Decimal = Decimal(0)

    # Additional metadata
    metadata: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.symbol} ({self.dex})"

    def __repr__(self) -> str:
        return f"Pool({self.symbol}, {self.dex}, {self.address[:8]}...)"

    @property
    def is_raydium(self) -> bool:
        return self.dex.lower() == "raydium"

    @property
    def is_meteora(self) -> bool:
        return self.dex.lower() == "meteora"

    @property
    def price_1_per_0(self) -> Decimal:
        """Price of token0 in terms of token1"""
        return self.price

    @property
    def price_0_per_1(self) -> Decimal:
        """Price of token1 in terms of token0"""
        if self.price == 0:
            return Decimal(0)
        return Decimal(1) / self.price

    def get_token_by_mint(self, mint: str) -> Optional[Token]:
        """Get token by mint address"""
        if self.token0.mint == mint:
            return self.token0
        if self.token1.mint == mint:
            return self.token1
        return None

    def is_token0(self, mint: str) -> bool:
        """Check if mint is token0"""
        return self.token0.mint == mint

    def is_token1(self, mint: str) -> bool:
        """Check if mint is token1"""
        return self.token1.mint == mint
