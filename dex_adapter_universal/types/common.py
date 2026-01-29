"""
Common type definitions
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import FrozenSet, Union


# Centralized stablecoin symbols for TVL calculation
# Used across all protocol adapters for consistent stablecoin detection
STABLECOINS: FrozenSet[str] = frozenset({
    "USDT", "USDC", "DAI", "BUSD", "TUSD", "FRAX", "USD1",
})


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
        # Import here to avoid circular import
        from .solana_tokens import SOLANA_TOKEN_MINTS
        return self.mint == SOLANA_TOKEN_MINTS["SOL"]

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
# NOTE: These are duplicated from solana_tokens.py for backwards compatibility
# and to avoid circular imports. The authoritative source is solana_tokens.py.
# For new code, use: from dex_adapter_universal.types.solana_tokens import SOLANA_TOKENS
from .solana_tokens import SOLANA_TOKEN_MINTS, SOLANA_TOKEN_DECIMALS

WRAPPED_SOL = Token(
    mint=SOLANA_TOKEN_MINTS["SOL"],
    symbol="SOL",
    decimals=SOLANA_TOKEN_DECIMALS[SOLANA_TOKEN_MINTS["SOL"]],
    name="Wrapped SOL"
)

USDC = Token(
    mint=SOLANA_TOKEN_MINTS["USDC"],
    symbol="USDC",
    decimals=SOLANA_TOKEN_DECIMALS[SOLANA_TOKEN_MINTS["USDC"]],
    name="USD Coin"
)

USDT = Token(
    mint=SOLANA_TOKEN_MINTS["USDT"],
    symbol="USDT",
    decimals=SOLANA_TOKEN_DECIMALS[SOLANA_TOKEN_MINTS["USDT"]],
    name="Tether USD"
)
