"""
Common type definitions
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Union


@dataclass(frozen=True)
class Token:
    """
    Token information

    Attributes:
        mint: Token mint address (base58)
        symbol: Token symbol (e.g., "SOL", "USDC")
        decimals: Number of decimal places
        name: Full token name (optional)
    """
    mint: str
    symbol: str
    decimals: int
    name: str = ""

    def __str__(self) -> str:
        return self.symbol

    def __repr__(self) -> str:
        return f"Token({self.symbol}, {self.mint[:8]}...)"

    @property
    def is_native_sol(self) -> bool:
        """Check if this is native SOL (wrapped)"""
        return self.mint == "So11111111111111111111111111111111111111112"

    def ui_amount(self, raw_amount: int) -> Decimal:
        """
        Convert raw amount to UI amount with full precision

        Args:
            raw_amount: Raw token amount (smallest units)

        Returns:
            UI amount as Decimal for precision
        """
        return Decimal(raw_amount) / Decimal(10 ** self.decimals)

    def raw_amount(self, ui_amount: Union[Decimal, float, int, str]) -> int:
        """
        Convert UI amount to raw amount

        Args:
            ui_amount: UI amount (can be Decimal, float, int, or str)

        Returns:
            Raw token amount (smallest units)
        """
        # Convert to Decimal for precision if not already
        if not isinstance(ui_amount, Decimal):
            ui_amount = Decimal(str(ui_amount))
        return int(ui_amount * Decimal(10 ** self.decimals))


# Common token constants
WRAPPED_SOL = Token(
    mint="So11111111111111111111111111111111111111112",
    symbol="SOL",
    decimals=9,
    name="Wrapped SOL"
)

USDC = Token(
    mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    symbol="USDC",
    decimals=6,
    name="USD Coin"
)

USDT = Token(
    mint="Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    symbol="USDT",
    decimals=6,
    name="Tether USD"
)
