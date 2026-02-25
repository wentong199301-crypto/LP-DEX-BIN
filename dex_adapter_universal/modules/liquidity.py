"""
Liquidity Module - Enhanced for Logging

Provides LP position operations with full result information for structured logging.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from ..client import DexClient

from ..types import Pool, Position, PriceRange, TxResult, OpenPositionResult, ClosePositionResult
from ..protocols import ProtocolRegistry
from ..errors import PositionNotFound, ConfigurationError
from ..config import config
from ..infra.retry import execute_with_retry

logger = logging.getLogger(__name__)


class LiquidityModule:
    """
    Liquidity operations module with enhanced logging support

    Provides LP position management:
    - Open positions (returns full result with deposited amounts)
    - Close positions (returns full result with received amounts and fees)
    - Add/remove liquidity
    - Claim fees/rewards
    - Query positions
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
    ) -> OpenPositionResult:
        """
        Open new LP position with full logging information

        Args:
            pool: Pool object or address
            price_range: Price range specification
            amount0: Token0 amount (optional)
            amount1: Token1 amount (optional)
            amount_usd: USD value to deposit (optional)
            slippage_bps: Slippage tolerance

        Returns:
            OpenPositionResult with transaction result and position details
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

        # Record start time to identify new position
        start_time = datetime.now(timezone.utc)

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
            return self._tx_builder.build_and_send(
                instructions,
                additional_signers=additional_signers,
                compute_units=config.tx.lp_compute_units,
                compute_unit_price=config.tx.lp_compute_unit_price,
            )

        tx_result = execute_with_retry(
            build_and_execute,
            f"open_position({pool.symbol})",
        )

        # Find the newly created position
        new_position = None
        if tx_result.is_success:
            try:
                positions = self.positions(dex=pool.dex)
                # Find position created after start_time
                for pos in positions:
                    if pos.created_at and pos.created_at >= start_time:
                        new_position = pos
                        break
            except Exception as e:
                logger.warning(f"Could not fetch new position: {e}")

        return OpenPositionResult(
            tx_result=tx_result,
            position_id=new_position.id if new_position else "",
            nft_mint=new_position.nft_mint if new_position else None,
            position_address=new_position.position_address if new_position else None,
            amount0_deposited=new_position.amount0 if new_position else amount0,
            amount1_deposited=new_position.amount1 if new_position else amount1,
        )

    def close(
        self,
        position: Optional[Union[Position, str]] = None,
        dex: Optional[str] = None,
    ) -> Union[ClosePositionResult, List[ClosePositionResult]]:
        """
        Close position(s) with full logging information

        Closes position(s) and returns detailed result including:
        - Transaction result
        - Amounts received
        - Fees collected

        Args:
            position: Position object or ID (closes single position)
            dex: DEX name (closes all positions on that DEX if position is None)

        Returns:
            ClosePositionResult for single position, List for multiple positions
        """
        # If position is provided, close single position
        if position is not None:
            if isinstance(position, str):
                position = self.get_position(position)

            adapter = ProtocolRegistry.get(position.pool.dex, self._rpc)

            # Record state before closing
            fees_before = position.unclaimed_fees.copy() if position.unclaimed_fees else {}
            rewards_before = position.unclaimed_rewards.copy() if position.unclaimed_rewards else {}

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

            tx_result = execute_with_retry(
                build_and_execute,
                f"close_position({position.id})",
            )

            # Note: Actual received amounts would need to be calculated from
            # transaction logs or balance changes. Here we use position amounts
            # as approximation, which should be close for successful closes.
            return ClosePositionResult(
                tx_result=tx_result,
                amount0_received=position.amount0 if tx_result.is_success else Decimal(0),
                amount1_received=position.amount1 if tx_result.is_success else Decimal(0),
                fees_collected=fees_before,
                rewards_collected=rewards_before,
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
                    if result.tx_result.is_success:
                        logger.info(f"  Closed: {result.tx_result.signature}")
                    else:
                        logger.warning(f"  Failed: {result.tx_result.error}")
                except Exception as e:
                    logger.error(f"  Error closing position {pos.id}: {e}")
                    # Create failed result
                    results.append(ClosePositionResult(
                        tx_result=TxResult.failed(str(e)),
                        amount0_received=Decimal(0),
                        amount1_received=Decimal(0),
                    ))

            return results

        raise ConfigurationError.missing("position or dex")

    # Keep other methods (add, remove, claim, positions, get_position) as is
    # They can be copied from the original file if needed
