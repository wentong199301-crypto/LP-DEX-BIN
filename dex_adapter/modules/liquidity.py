"""
Liquidity Module

Provides LP position operations.
"""

import logging
from decimal import Decimal
from typing import List, Optional, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from ..client import DexClient

from ..types import Pool, Position, PriceRange, TxResult
from ..protocols import ProtocolRegistry
from ..errors import PositionNotFound, ConfigurationError
from ..config import config

logger = logging.getLogger(__name__)


class LiquidityModule:
    """
    Liquidity operations module

    Provides LP position management:
    - Open positions
    - Close positions
    - Add/remove liquidity
    - Claim fees/rewards
    - Query positions

    Usage:
        client = DexClient(rpc_url, keypair)

        # Open position
        position = client.lp.open(
            pool="pool_address...",
            price_range=PriceRange.percent(0.01),  # +/-1%
            amount_usd=Decimal("1000"),
        )

        # Close position
        result = client.lp.close(position)

        # Claim fees
        result = client.lp.claim(position)

        # List positions
        positions = client.lp.positions()
    """

    def __init__(self, client: "DexClient"):
        """
        Initialize liquidity module

        Args:
            client: DexClient instance
        """
        self._client = client
        self._rpc = client.rpc
        self._tx_builder = client.tx_builder

    @property
    def owner(self) -> str:
        """Owner wallet address"""
        return self._client.pubkey

    def open(
        self,
        pool: Union[Pool, str],
        price_range: PriceRange,
        amount0: Optional[Decimal] = None,
        amount1: Optional[Decimal] = None,
        amount_usd: Optional[Decimal] = None,
        slippage_bps: int = 50,
    ) -> TxResult:
        """
        Open new LP position

        Args:
            pool: Pool object or address
            price_range: Price range specification
            amount0: Token0 amount (optional)
            amount1: Token1 amount (optional)
            amount_usd: USD value to deposit (optional)
            slippage_bps: Slippage tolerance

        Returns:
            TxResult with transaction signature on success

        Note:
            The position ID (NFT mint for Raydium, address for Meteora) is not
            returned directly. Use positions() to list created positions.
        """
        # Resolve pool
        if isinstance(pool, str):
            pool = self._client.market.pool(pool)

        # Get adapter
        adapter = ProtocolRegistry.get(pool.dex, self._rpc)

        # Calculate amounts if not provided
        if amount0 is None or amount1 is None:
            if amount_usd is None:
                raise ConfigurationError.missing("amount0/amount1 or amount_usd")

            amount0, amount1 = adapter.calculate_amounts_for_range(
                pool, price_range, amount_usd
            )

        # Build instructions (returns tuple of instructions and additional signers)
        instructions, additional_signers = adapter.build_open_position(
            pool=pool,
            price_range=price_range,
            amount0=amount0,
            amount1=amount1,
            owner=self.owner,
            slippage_bps=slippage_bps,
        )

        # Execute with additional signers (e.g., NFT mint for Raydium)
        # Use LP-specific compute budget (configurable via TX_LP_COMPUTE_UNITS/TX_LP_COMPUTE_UNIT_PRICE)
        return self._tx_builder.build_and_send(
            instructions,
            additional_signers=additional_signers,
            compute_units=config.tx.lp_compute_units,
            compute_unit_price=config.tx.lp_compute_unit_price,
        )

    def close(
        self,
        position: Union[Position, str],
    ) -> TxResult:
        """
        Close position (remove all liquidity)

        For Raydium: Uses multi-step close to avoid error 101 (ClosePositionErr).
        Step 1: Remove all liquidity
        Step 2: Claim fees/rewards
        Step 3: Close the position (burn NFT)

        Args:
            position: Position object or ID

        Returns:
            TxResult
        """
        # Resolve position
        if isinstance(position, str):
            position = self.get_position(position)

        # Get adapter
        adapter = ProtocolRegistry.get(position.pool.dex, self._rpc)

        # For Raydium, use multi-step close via adapter's generator
        if position.pool.dex == "raydium" and hasattr(adapter, "generate_close_position_steps"):
            return self._execute_multi_step_close(position, adapter)

        # For other DEXes (Meteora), use single transaction
        instructions = adapter.build_close_position(
            position=position,
            owner=self.owner,
        )

        # Execute with LP-specific compute budget
        return self._tx_builder.build_and_send(
            instructions,
            compute_units=config.tx.lp_compute_units,
            compute_unit_price=config.tx.lp_compute_unit_price,
        )

    def _execute_multi_step_close(
        self,
        position: Position,
        adapter,
    ) -> TxResult:
        """
        Execute multi-step close using adapter's generator.

        Args:
            position: Position to close
            adapter: Protocol adapter with generate_close_position_steps method

        Returns:
            TxResult from the final close transaction
        """
        last_result = TxResult.skipped("No close steps generated")

        for instructions, step_desc, is_final in adapter.generate_close_position_steps(
            position=position,
            owner=self.owner,
        ):
            logger.debug(f"Executing close step: {step_desc}")
            result = self._tx_builder.build_and_send(
                instructions,
                compute_units=config.tx.lp_compute_units,
                compute_unit_price=config.tx.lp_compute_unit_price,
            )

            if is_final:
                return result

            # For intermediate steps, log but continue on failure
            if not result.is_success:
                logger.debug(f"Step {step_desc} returned: {result.error}")
            else:
                logger.debug(f"Step {step_desc} completed: {result.signature}")

            last_result = result

        return last_result

    def add(
        self,
        position: Union[Position, str],
        amount0: Decimal,
        amount1: Decimal,
        slippage_bps: int = 50,
    ) -> TxResult:
        """
        Add liquidity to existing position

        Args:
            position: Position object or ID
            amount0: Token0 amount to add
            amount1: Token1 amount to add
            slippage_bps: Slippage tolerance

        Returns:
            TxResult
        """
        if isinstance(position, str):
            position = self.get_position(position)

        adapter = ProtocolRegistry.get(position.pool.dex, self._rpc)

        instructions = adapter.build_add_liquidity(
            position=position,
            amount0=amount0,
            amount1=amount1,
            owner=self.owner,
            slippage_bps=slippage_bps,
        )

        if not instructions:
            return TxResult.skipped("No liquidity to add (zero amounts or missing position data)")

        return self._tx_builder.build_and_send(
            instructions,
            compute_units=config.tx.lp_compute_units,
            compute_unit_price=config.tx.lp_compute_unit_price,
        )

    def remove(
        self,
        position: Union[Position, str],
        percent: float = 100.0,
        slippage_bps: int = 50,
    ) -> TxResult:
        """
        Remove liquidity from position

        Args:
            position: Position object or ID
            percent: Percentage to remove (0-100)
            slippage_bps: Slippage tolerance

        Returns:
            TxResult
        """
        if isinstance(position, str):
            position = self.get_position(position)

        adapter = ProtocolRegistry.get(position.pool.dex, self._rpc)

        instructions = adapter.build_remove_liquidity(
            position=position,
            liquidity_percent=percent,
            owner=self.owner,
            slippage_bps=slippage_bps,
        )

        if not instructions:
            return TxResult.skipped("No liquidity to remove (zero liquidity or missing position data)")

        return self._tx_builder.build_and_send(
            instructions,
            compute_units=config.tx.lp_compute_units,
            compute_unit_price=config.tx.lp_compute_unit_price,
        )

    def claim(
        self,
        position: Union[Position, str],
    ) -> TxResult:
        """
        Claim accumulated fees and rewards

        Args:
            position: Position object or ID

        Returns:
            TxResult
        """
        if isinstance(position, str):
            position = self.get_position(position)

        adapter = ProtocolRegistry.get(position.pool.dex, self._rpc)

        instructions = adapter.build_claim_fees(
            position=position,
            owner=self.owner,
        )

        # Add reward claim if supported
        reward_instructions = adapter.build_claim_rewards(
            position=position,
            owner=self.owner,
        )
        instructions.extend(reward_instructions)

        if not instructions:
            return TxResult.skipped("Nothing to claim")

        return self._tx_builder.build_and_send(
            instructions,
            compute_units=config.tx.lp_compute_units,
            compute_unit_price=config.tx.lp_compute_unit_price,
        )

    def positions(
        self,
        owner: Optional[str] = None,
        pool: Optional[str] = None,
        dex: Optional[str] = None,
    ) -> List[Position]:
        """
        List LP positions

        Args:
            owner: Owner address (defaults to wallet owner)
            pool: Filter by pool address
            dex: Filter by protocol

        Returns:
            List of positions
        """
        owner = owner or self.owner
        positions: List[Position] = []

        protocols = [dex] if dex else ProtocolRegistry.list()

        for protocol in protocols:
            try:
                adapter = ProtocolRegistry.get(protocol, self._rpc)
                protocol_positions = adapter.get_positions(owner, pool)
                positions.extend(protocol_positions)
            except Exception as e:
                logger.debug(f"Failed to query positions from {protocol}: {e}", exc_info=True)
                continue

        return positions

    def get_position(
        self,
        position_id: str,
        dex: Optional[str] = None,
    ) -> Position:
        """
        Get single position by ID

        Args:
            position_id: Position ID (NFT mint for Raydium, address for Meteora)
            dex: Protocol (auto-detected if not provided)

        Returns:
            Position

        Raises:
            PositionNotFound: If position doesn't exist
        """
        protocols = [dex] if dex else ProtocolRegistry.list()

        for protocol in protocols:
            try:
                adapter = ProtocolRegistry.get(protocol, self._rpc)
                return adapter.get_position(position_id)
            except PositionNotFound:
                # Expected when trying protocols that don't have this position
                continue
            except Exception as e:
                logger.debug(f"Failed to get position from {protocol}: {e}", exc_info=True)
                continue

        raise PositionNotFound.not_found(position_id)

    def is_in_range(
        self,
        position: Union[Position, str],
    ) -> bool:
        """
        Check if position is in range

        Args:
            position: Position object or ID

        Returns:
            True if current price is within position range
        """
        if isinstance(position, str):
            position = self.get_position(position)

        adapter = ProtocolRegistry.get(position.pool.dex, self._rpc)
        return adapter.is_in_range(position)

    def calculate_amounts(
        self,
        pool: Union[Pool, str],
        price_range: PriceRange,
        amount_usd: Decimal,
    ) -> tuple[Decimal, Decimal]:
        """
        Calculate token amounts for a given range and USD value

        Args:
            pool: Pool object or address
            price_range: Price range specification
            amount_usd: Target USD value

        Returns:
            (amount0, amount1) tuple
        """
        if isinstance(pool, str):
            pool = self._client.market.pool(pool)

        adapter = ProtocolRegistry.get(pool.dex, self._rpc)
        return adapter.calculate_amounts_for_range(pool, price_range, amount_usd)
