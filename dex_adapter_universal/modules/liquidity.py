"""
Liquidity Module

Provides LP position operations with automatic retry for transient failures.
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
from ..infra.retry import execute_with_retry

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
        slippage_bps: Optional[int] = None,
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

        # Use config default if not specified
        if slippage_bps is None:
            slippage_bps = config.trading.default_lp_slippage_bps

        # Get adapter
        adapter = ProtocolRegistry.get(pool.dex, self._rpc)

        # Calculate amounts if not provided
        if amount0 is None or amount1 is None:
            if amount_usd is None:
                raise ConfigurationError.missing("amount0/amount1 or amount_usd")

            amount0, amount1 = adapter.calculate_amounts_for_range(
                pool, price_range, amount_usd
            )

        def build_and_execute():
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

        return execute_with_retry(
            build_and_execute,
            f"open_position({pool.symbol})",
        )

    def close(
        self,
        position: Optional[Union[Position, str]] = None,
        dex: Optional[str] = None,
    ) -> Union[TxResult, List[TxResult]]:
        """
        Close position(s) (remove all liquidity)

        Closes position(s) in single transaction(s):
        - Remove all liquidity
        - Claim fees/rewards
        - Close the position (burn NFT for Raydium)

        Args:
            position: Position object or ID (closes single position)
            dex: DEX name (closes all positions on that DEX if position is None)

        Returns:
            TxResult for single position, List[TxResult] for multiple positions

        Examples:
            # Close a specific position
            result = client.lp.close(position)

            # Close all positions on a DEX
            results = client.lp.close(dex="raydium")
        """
        # If position is provided, close single position
        if position is not None:
            if isinstance(position, str):
                position = self.get_position(position)

            adapter = ProtocolRegistry.get(position.pool.dex, self._rpc)

            def build_and_execute():
                instructions = adapter.build_close_position(
                    position=position,
                    owner=self.owner,
                )
                return self._tx_builder.build_and_send(
                    instructions,
                    compute_units=config.tx.lp_compute_units,
                    compute_unit_price=config.tx.lp_compute_unit_price,
                )

            return execute_with_retry(
                build_and_execute,
                f"close_position({position.id})",
            )

        # If dex is provided, close all positions on that DEX
        if dex is not None:
            positions = self.positions(dex=dex)

            if not positions:
                logger.info(f"No positions to close on {dex}")
                return []

            results = []
            for pos in positions:
                logger.info(f"Closing position {pos.id[:16]}... on {pos.dex}")
                try:
                    result = self.close(position=pos)
                    results.append(result)
                    if result.is_success:
                        logger.info(f"  Closed: {result.signature}")
                    else:
                        logger.warning(f"  Failed: {result.error}")
                except Exception as e:
                    logger.error(f"  Error closing position {pos.id}: {e}")
                    results.append(TxResult.failed(str(e)))

            return results

        raise ConfigurationError.missing("position or dex")

    def add(
        self,
        position: Union[Position, str],
        amount0: Decimal,
        amount1: Decimal,
        slippage_bps: Optional[int] = None,
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

        # Use config default if not specified
        if slippage_bps is None:
            slippage_bps = config.trading.default_lp_slippage_bps

        adapter = ProtocolRegistry.get(position.pool.dex, self._rpc)

        def build_and_execute():
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

        return execute_with_retry(
            build_and_execute,
            f"add_liquidity({position.id})",
        )

    def remove(
        self,
        position: Union[Position, str],
        percent: float = 100.0,
        slippage_bps: Optional[int] = None,
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

        # Use config default if not specified
        if slippage_bps is None:
            slippage_bps = config.trading.default_lp_slippage_bps

        adapter = ProtocolRegistry.get(position.pool.dex, self._rpc)

        def build_and_execute():
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

        return execute_with_retry(
            build_and_execute,
            f"remove_liquidity({position.id})",
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

        def build_and_execute():
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

        return execute_with_retry(
            build_and_execute,
            f"claim_fees({position.id})",
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
