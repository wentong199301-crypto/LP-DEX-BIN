"""
Position type definitions
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, List

from .pool import Pool


@dataclass
class Position:
    """
    LP position information

    Attributes:
        id: Position identifier (NFT mint for Raydium, position address for Meteora)
        pool: Associated pool
        owner: Position owner address
        price_lower: Lower price bound
        price_upper: Upper price bound
        amount0: Token0 amount in position
        amount1: Token1 amount in position
        liquidity: Liquidity amount
        value_usd: Current value in USD
        unclaimed_fees: Unclaimed trading fees by token mint
        unclaimed_rewards: Unclaimed rewards by token mint
        is_in_range: Whether current price is within position range
        created_at: Position creation timestamp

        # Raydium specific
        nft_mint: Position NFT mint address
        tick_lower: Lower tick index
        tick_upper: Upper tick index

        # Meteora specific
        lower_bin_id: Lower bin ID
        upper_bin_id: Upper bin ID
    """
    id: str
    pool: Pool
    owner: str
    price_lower: Decimal
    price_upper: Decimal
    amount0: Decimal
    amount1: Decimal
    liquidity: int
    value_usd: Decimal = Decimal(0)
    unclaimed_fees: Dict[str, Decimal] = field(default_factory=dict)
    unclaimed_rewards: Dict[str, Decimal] = field(default_factory=dict)
    is_in_range: bool = True
    created_at: Optional[datetime] = None

    # Raydium CLMM specific
    nft_mint: Optional[str] = None
    tick_lower: Optional[int] = None
    tick_upper: Optional[int] = None

    # Meteora DLMM specific
    lower_bin_id: Optional[int] = None
    upper_bin_id: Optional[int] = None
    position_address: Optional[str] = None
    bin_ids: List[int] = field(default_factory=list)  # List of bin IDs with liquidity

    # Additional metadata
    metadata: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return f"Position({self.pool.symbol}, {self.price_lower:.4f}-{self.price_upper:.4f})"

    def __repr__(self) -> str:
        return f"Position(id={self.id[:8]}..., pool={self.pool.symbol})"

    @property
    def dex(self) -> str:
        """DEX name (convenience property, delegates to pool.dex)"""
        return self.pool.dex

    @property
    def range_width_percent(self) -> float:
        """Calculate range width as percentage of lower price"""
        if self.price_lower == 0:
            return 0
        return float((self.price_upper - self.price_lower) / self.price_lower * 100)

    @property
    def mid_price(self) -> Decimal:
        """Get midpoint price of the range"""
        return (self.price_lower + self.price_upper) / 2

    @property
    def total_unclaimed_fees(self) -> Decimal:
        """
        Sum of all unclaimed fees (raw amounts, not USD-converted)

        Note: This sums raw token amounts across different tokens.
        For accurate USD value, convert each token amount individually.
        """
        return sum(self.unclaimed_fees.values(), Decimal(0))

    @property
    def total_unclaimed_rewards(self) -> Decimal:
        """
        Sum of all unclaimed rewards (raw amounts, not USD-converted)

        Note: This sums raw token amounts across different tokens.
        For accurate USD value, convert each token amount individually.
        """
        return sum(self.unclaimed_rewards.values(), Decimal(0))

    def check_in_range(self, current_price: Decimal) -> bool:
        """Check if given price is within position range"""
        return self.price_lower <= current_price <= self.price_upper

    def price_position_ratio(self, current_price: Decimal) -> float:
        """
        Calculate where current price is within the range

        Returns:
            0.0 = at lower bound
            0.5 = at midpoint
            1.0 = at upper bound
            <0 or >1 = out of range
        """
        if self.price_upper == self.price_lower:
            return 0.5 if current_price == self.price_lower else (1.0 if current_price > self.price_lower else 0.0)

        return float((current_price - self.price_lower) / (self.price_upper - self.price_lower))

    def distance_to_boundary(self, current_price: Decimal) -> float:
        """
        Calculate distance to nearest boundary as percentage of range width

        Returns:
            0.0 = at boundary
            0.5 = at center
        """
        ratio = self.price_position_ratio(current_price)
        return min(ratio, 1 - ratio) if 0 <= ratio <= 1 else 0.0

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dictionary"""
        return {
            "id": self.id,
            "pool": self.pool.to_dict() if hasattr(self.pool, 'to_dict') else str(self.pool),
            "owner": self.owner,
            "price_lower": str(self.price_lower),
            "price_upper": str(self.price_upper),
            "amount0": str(self.amount0),
            "amount1": str(self.amount1),
            "liquidity": self.liquidity,
            "value_usd": str(self.value_usd),
            "unclaimed_fees": {k: str(v) for k, v in self.unclaimed_fees.items()},
            "unclaimed_rewards": {k: str(v) for k, v in self.unclaimed_rewards.items()},
            "is_in_range": self.is_in_range,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "nft_mint": self.nft_mint,
            "tick_lower": self.tick_lower,
            "tick_upper": self.tick_upper,
            "lower_bin_id": self.lower_bin_id,
            "upper_bin_id": self.upper_bin_id,
            "position_address": self.position_address,
            "bin_ids": self.bin_ids,
            "dex": self.dex,
        }
