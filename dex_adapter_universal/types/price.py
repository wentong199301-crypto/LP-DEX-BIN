"""
Price and range type definitions
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    pass

from ..errors import OperationNotSupported


class RangeMode(Enum):
    """
    Price range specification mode

    PERCENT: Relative percentage around current price (e.g., -0.01, 0.01 = +/-1%)
    BPS: Basis points around current price (e.g., -100, 100 = +/-1%)
    ABSOLUTE: Absolute price values (e.g., 95.0, 105.0)
    ONE_TICK: Single tick range (Raydium CLMM)
    ONE_BIN: Single bin range (Meteora DLMM)
    TICK_RANGE: Explicit tick range (Raydium)
    BIN_RANGE: Explicit bin range (Meteora)
    """
    PERCENT = "percent"
    BPS = "bps"
    ABSOLUTE = "absolute"
    ONE_TICK = "one_tick"
    ONE_BIN = "one_bin"
    TICK_RANGE = "tick_range"
    BIN_RANGE = "bin_range"


@dataclass
class PriceRange:
    """
    Price range specification for LP positions

    Usage:
        # Single tick/bin (maximum concentration)
        PriceRange.one_tick()
        PriceRange.one_bin()

        # Symmetric percentage range (+/- 1%)
        PriceRange.percent(0.01)

        # Symmetric basis points range (+/- 100 bps = 1%)
        PriceRange.bps(100)

        # Asymmetric range (-0.5% to +1.5%)
        PriceRange(Decimal("-0.005"), Decimal("0.015"), RangeMode.PERCENT)

        # Absolute price range
        PriceRange.absolute(95.0, 105.0)

        # Explicit tick range (Raydium)
        PriceRange.ticks(-100, 100)

        # Explicit bin range (Meteora)
        PriceRange.bins(-10, 10)
    """
    lower: Decimal
    upper: Decimal
    mode: RangeMode = RangeMode.PERCENT

    def __post_init__(self):
        # Convert to Decimal if needed (direct assignment - class is not frozen)
        if not isinstance(self.lower, Decimal):
            self.lower = Decimal(str(self.lower))
        if not isinstance(self.upper, Decimal):
            self.upper = Decimal(str(self.upper))

    @classmethod
    def one_tick(cls) -> "PriceRange":
        """Create single tick range (Raydium CLMM)"""
        return cls(Decimal(0), Decimal(0), RangeMode.ONE_TICK)

    @classmethod
    def one_bin(cls) -> "PriceRange":
        """Create single bin range (Meteora DLMM)"""
        return cls(Decimal(0), Decimal(0), RangeMode.ONE_BIN)

    @classmethod
    def percent(cls, pct: float) -> "PriceRange":
        """
        Create symmetric percentage range

        Args:
            pct: Percentage as decimal (0.01 = 1%)

        Returns:
            PriceRange with +/- pct around current price
        """
        return cls(Decimal(str(-pct)), Decimal(str(pct)), RangeMode.PERCENT)

    @classmethod
    def percent_asymmetric(cls, lower_pct: float, upper_pct: float) -> "PriceRange":
        """
        Create asymmetric percentage range

        Args:
            lower_pct: Lower bound percentage (negative for below current price)
            upper_pct: Upper bound percentage (positive for above current price)
        """
        return cls(Decimal(str(lower_pct)), Decimal(str(upper_pct)), RangeMode.PERCENT)

    @classmethod
    def bps(cls, basis_points: int) -> "PriceRange":
        """
        Create symmetric basis points range

        Args:
            basis_points: Number of basis points (100 = 1%)
        """
        pct = Decimal(basis_points) / Decimal(10000)
        return cls(-pct, pct, RangeMode.BPS)

    @classmethod
    def bps_asymmetric(cls, lower_bps: int, upper_bps: int) -> "PriceRange":
        """
        Create asymmetric basis points range

        Args:
            lower_bps: Lower bound in basis points (negative for below)
            upper_bps: Upper bound in basis points (positive for above)
        """
        return cls(
            Decimal(lower_bps) / Decimal(10000),
            Decimal(upper_bps) / Decimal(10000),
            RangeMode.BPS
        )

    @classmethod
    def absolute(cls, lower: float, upper: float) -> "PriceRange":
        """
        Create absolute price range

        Args:
            lower: Lower price bound
            upper: Upper price bound
        """
        return cls(Decimal(str(lower)), Decimal(str(upper)), RangeMode.ABSOLUTE)

    @classmethod
    def ticks(cls, lower_tick: int, upper_tick: int) -> "PriceRange":
        """
        Create explicit tick range (Raydium)

        Args:
            lower_tick: Lower tick index
            upper_tick: Upper tick index
        """
        return cls(Decimal(lower_tick), Decimal(upper_tick), RangeMode.TICK_RANGE)

    @classmethod
    def bins(cls, lower_offset: int, upper_offset: int) -> "PriceRange":
        """
        Create bin offset range (Meteora)

        Args:
            lower_offset: Offset from active bin for lower bound
            upper_offset: Offset from active bin for upper bound
        """
        return cls(Decimal(lower_offset), Decimal(upper_offset), RangeMode.BIN_RANGE)

    @property
    def is_single_unit(self) -> bool:
        """Check if this is a single tick/bin range"""
        return self.mode in (RangeMode.ONE_TICK, RangeMode.ONE_BIN)

    @property
    def is_relative(self) -> bool:
        """Check if range is relative to current price"""
        return self.mode in (RangeMode.PERCENT, RangeMode.BPS, RangeMode.ONE_TICK, RangeMode.ONE_BIN)

    @property
    def is_absolute(self) -> bool:
        """Check if range uses absolute prices"""
        return self.mode == RangeMode.ABSOLUTE

    def to_absolute(self, current_price: Decimal) -> tuple[Decimal, Decimal]:
        """
        Convert range to absolute prices

        Args:
            current_price: Current market price

        Returns:
            (lower_price, upper_price) tuple

        Raises:
            ValueError: If current_price is zero or negative for relative modes
        """
        if self.mode == RangeMode.ABSOLUTE:
            return (self.lower, self.upper)

        if self.mode in (RangeMode.PERCENT, RangeMode.BPS):
            if current_price <= Decimal(0):
                raise ValueError(
                    f"Cannot convert relative price range to absolute with "
                    f"current_price={current_price}. Price must be positive."
                )
            lower_price = current_price * (Decimal(1) + self.lower)
            upper_price = current_price * (Decimal(1) + self.upper)
            return (lower_price, upper_price)

        # ONE_TICK, ONE_BIN, TICK_RANGE, BIN_RANGE need protocol-specific conversion
        raise OperationNotSupported(
            f"Cannot convert {self.mode} to absolute without protocol context",
            operation="to_absolute",
        )

    def width_percent(self) -> Optional[float]:
        """
        Get total width as percentage (for relative modes)

        Returns:
            Width as a percentage (e.g., 2.0 for 2%), or None for non-relative modes
        """
        if self.mode in (RangeMode.PERCENT, RangeMode.BPS):
            # upper - lower gives the fractional width, multiply by 100 for percentage
            return float(self.upper - self.lower) * 100
        return None

    def width_fraction(self) -> Optional[float]:
        """
        Get total width as a fraction (for relative modes)

        Returns:
            Width as a fraction (e.g., 0.02 for 2%), or None for non-relative modes
        """
        if self.mode in (RangeMode.PERCENT, RangeMode.BPS):
            return float(self.upper - self.lower)
        return None

    def __str__(self) -> str:
        if self.mode == RangeMode.ONE_TICK:
            return "OneTick"
        if self.mode == RangeMode.ONE_BIN:
            return "OneBin"
        if self.mode == RangeMode.PERCENT:
            return f"Percent({float(self.lower)*100:.2f}%, {float(self.upper)*100:.2f}%)"
        if self.mode == RangeMode.BPS:
            return f"BPS({int(self.lower*10000)}, {int(self.upper*10000)})"
        if self.mode == RangeMode.ABSOLUTE:
            return f"Absolute({self.lower}, {self.upper})"
        return f"{self.mode.value}({self.lower}, {self.upper})"
