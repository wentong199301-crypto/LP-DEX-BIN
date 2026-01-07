"""
Base protocol adapter interface

All DEX protocol adapters must implement this interface to provide
unified access to different protocols (Raydium, Meteora, etc.)
"""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import List, Optional, Any, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from solders.instruction import Instruction
    from solders.keypair import Keypair

from ..types import Pool, Position, PriceRange, Token
from ..infra import RpcClient


class ProtocolAdapter(ABC):
    """
    Abstract base class for DEX protocol adapters

    Each adapter provides:
    - Pool queries
    - Position queries
    - Instruction building for LP operations

    The adapter handles protocol-specific details internally,
    exposing a unified interface to the higher layers.
    """

    # Protocol identifier (e.g., "raydium", "meteora")
    name: str = "base"

    # Program ID
    program_id: str = ""

    def __init__(self, rpc: RpcClient):
        """
        Initialize adapter with RPC client

        Args:
            rpc: RPC client for blockchain queries
        """
        self._rpc = rpc

    @property
    def rpc(self) -> RpcClient:
        """Access to RPC client"""
        return self._rpc

    # ========== Pool Operations ==========

    @abstractmethod
    def get_pool(self, pool_address: str) -> Pool:
        """
        Get pool information by address

        Args:
            pool_address: Pool address (base58)

        Returns:
            Pool information

        Raises:
            PoolUnavailable: If pool not found or invalid
        """
        ...

    def get_pools_by_token(self, token: str) -> List[Pool]:
        """
        Find all pools containing a token

        Args:
            token: Token mint address

        Returns:
            List of pools
        """
        return []  # Optional override

    def get_pool_by_tokens(self, token0: str, token1: str) -> Optional[Pool]:
        """
        Find pool by token pair

        Args:
            token0: First token mint address
            token1: Second token mint address

        Returns:
            Pool if found, None otherwise
        """
        return None  # Optional override - requires protocol-specific indexer

    # ========== Position Operations ==========

    @abstractmethod
    def get_positions(
        self,
        owner: str,
        pool: Optional[str] = None,
    ) -> List[Position]:
        """
        Get positions owned by address

        Args:
            owner: Owner wallet address
            pool: Optional pool filter

        Returns:
            List of positions
        """
        ...

    @abstractmethod
    def get_position(self, position_id: str) -> Position:
        """
        Get single position by ID

        Args:
            position_id: Position identifier (NFT mint for Raydium, address for Meteora)

        Returns:
            Position information

        Raises:
            PositionNotFound: If position doesn't exist
        """
        ...

    def is_in_range(self, position: Position, pool: Optional[Pool] = None) -> bool:
        """
        Check if position is in range

        Args:
            position: Position to check
            pool: Optional pool (fetched if not provided)

        Returns:
            True if current price is within position range
        """
        if pool is None:
            pool = self.get_pool(position.pool.address)
        return position.check_in_range(pool.price)

    # ========== Instruction Building ==========

    @abstractmethod
    def build_open_position(
        self,
        pool: Pool,
        price_range: PriceRange,
        amount0: Decimal,
        amount1: Decimal,
        owner: str,
        slippage_bps: int = 50,
    ) -> Tuple[List["Instruction"], List["Keypair"]]:
        """
        Build instructions to open LP position

        Args:
            pool: Target pool
            price_range: Price range specification
            amount0: Token0 amount to deposit
            amount1: Token1 amount to deposit
            owner: Position owner
            slippage_bps: Slippage tolerance in basis points

        Returns:
            Tuple of (instructions, additional_signers)
            - instructions: List of instructions to execute
            - additional_signers: List of keypairs that must sign (e.g., NFT mint)
        """
        ...

    @abstractmethod
    def build_close_position(
        self,
        position: Position,
        owner: str,
    ) -> List["Instruction"]:
        """
        Build instructions to close position (remove all liquidity)

        Args:
            position: Position to close
            owner: Position owner

        Returns:
            List of instructions
        """
        ...

    @abstractmethod
    def build_add_liquidity(
        self,
        position: Position,
        amount0: Decimal,
        amount1: Decimal,
        owner: str,
        slippage_bps: int = 50,
    ) -> List["Instruction"]:
        """
        Build instructions to add liquidity

        Args:
            position: Target position
            amount0: Token0 amount to add
            amount1: Token1 amount to add
            owner: Position owner
            slippage_bps: Slippage tolerance

        Returns:
            List of instructions
        """
        ...

    @abstractmethod
    def build_remove_liquidity(
        self,
        position: Position,
        liquidity_percent: float,
        owner: str,
        slippage_bps: int = 50,
    ) -> List["Instruction"]:
        """
        Build instructions to remove liquidity

        Args:
            position: Target position
            liquidity_percent: Percentage of liquidity to remove (0-100)
            owner: Position owner
            slippage_bps: Slippage tolerance

        Returns:
            List of instructions
        """
        ...

    @abstractmethod
    def build_claim_fees(
        self,
        position: Position,
        owner: str,
    ) -> List["Instruction"]:
        """
        Build instructions to claim accumulated fees

        Args:
            position: Target position
            owner: Position owner

        Returns:
            List of instructions
        """
        ...

    def build_claim_rewards(
        self,
        position: Position,
        owner: str,
    ) -> List["Instruction"]:
        """
        Build instructions to claim rewards (if applicable)

        Args:
            position: Target position
            owner: Position owner

        Returns:
            List of instructions (empty if no rewards)
        """
        return []  # Optional override

    # ========== Price/Range Calculations ==========

    @abstractmethod
    def calculate_amounts_for_range(
        self,
        pool: Pool,
        price_range: PriceRange,
        target_value_usd: Decimal,
    ) -> tuple[Decimal, Decimal]:
        """
        Calculate token amounts for a given range and value

        Args:
            pool: Target pool
            price_range: Desired price range
            target_value_usd: Target USD value to deposit

        Returns:
            (amount0, amount1) tuple
        """
        ...

    @abstractmethod
    def price_range_to_ticks(
        self,
        pool: Pool,
        price_range: PriceRange,
    ) -> tuple[int, int]:
        """
        Convert price range to protocol-specific ticks/bins

        Args:
            pool: Target pool
            price_range: Price range specification

        Returns:
            (lower_tick, upper_tick) or (lower_bin, upper_bin)
        """
        ...

    @abstractmethod
    def ticks_to_prices(
        self,
        pool: Pool,
        lower_tick: int,
        upper_tick: int,
    ) -> tuple[Decimal, Decimal]:
        """
        Convert ticks/bins to prices

        Args:
            pool: Target pool
            lower_tick: Lower tick/bin
            upper_tick: Upper tick/bin

        Returns:
            (lower_price, upper_price)
        """
        ...

    # ========== Utility Methods ==========

    def get_token_info(self, mint: str) -> Optional[Token]:
        """
        Get token information by mint address

        Args:
            mint: Token mint address

        Returns:
            Token info or None
        """
        # Default implementation fetches from RPC
        account = self._rpc.get_account_info(mint, encoding="jsonParsed")
        if not account:
            return None

        data = account.get("data", {})
        if isinstance(data, dict) and data.get("program") == "spl-token":
            parsed = data.get("parsed", {}).get("info", {})
            return Token(
                mint=mint,
                symbol="",
                decimals=parsed.get("decimals", 0),
            )
        return None

    def estimate_fees(
        self,
        pool: Pool,
        position: Position,
        time_hours: float = 24,
    ) -> dict[str, Decimal]:
        """
        Estimate fee earnings for a position

        Args:
            pool: Pool info
            position: Position info
            time_hours: Time period in hours

        Returns:
            Estimated fees by token
        """
        # Default: return empty (override in subclass)
        return {}
