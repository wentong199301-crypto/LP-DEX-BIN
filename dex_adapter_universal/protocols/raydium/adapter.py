"""
Raydium CLMM Protocol Adapter

Based on raydium_trading reference implementation.

Implements ProtocolAdapter interface for Raydium Concentrated Liquidity with:
- Token-2022 NFT support (open_position_with_token22_nft)
- Multi-variant close position strategy
- Auto-detection of token programs
- Floor-based tick array alignment
- Proper reward handling with manual overrides

Token Naming Convention:
    - token0 / mint_a: The first token in the pool (base token)
    - token1 / mint_b: The second token in the pool (quote token)
    - price: token0 price in terms of token1 (e.g., SOL price in USDC)
"""

import logging
from decimal import Decimal
from typing import List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from solders.instruction import Instruction
    from solders.keypair import Keypair

logger = logging.getLogger(__name__)

from ..base import ProtocolAdapter
from ...types import Pool, Position, PriceRange, RangeMode, Token
from ...infra import RpcClient
from ...errors import PoolUnavailable, PositionNotFound, OperationNotSupported, ConfigurationError

from .constants import CLMM_PROGRAM_ID, WRAPPED_SOL_MINT, TOKEN_2022_PROGRAM_ID, WSOL_WRAP_BUFFER_LAMPORTS
from .math import (
    tick_to_sqrt_price_x64,
    tick_to_price,
    price_to_tick,
    one_tick_range,
    get_amounts_from_liquidity,
    get_liquidity_from_amounts,
)
from .pool_parser import fetch_pool_state, pool_state_to_pool
from .position_parser import (
    fetch_positions_by_owner,
    fetch_position_by_nft,
    position_state_to_position,
)
from .instructions import (
    build_open_position_instructions,
    build_close_position_instructions,
    build_close_position_candidates,
    build_increase_liquidity_instructions,
    build_decrease_liquidity_instructions,
    build_wrap_sol_instructions,
    build_unwrap_wsol_instructions,
    detect_token_program_for_mint,
    get_associated_token_address,
)


class RaydiumAdapter(ProtocolAdapter):
    """
    Raydium CLMM Protocol Adapter

    Provides unified interface for:
    - Pool queries
    - Position management
    - LP operations (open, close, add, remove, claim)

    Key features (based on raydium_trading reference):
    - Uses open_position_with_token22_nft for new positions
    - Auto-detects token programs for Token-2022 support
    - Multi-variant close position strategy
    - Floor-based tick array alignment

    Usage:
        rpc = RpcClient("https://api.mainnet-beta.solana.com")
        adapter = RaydiumAdapter(rpc)

        pool = adapter.get_pool("pool_address...")
        positions = adapter.get_positions("owner_address...")
    """

    name = "raydium"
    program_id = CLMM_PROGRAM_ID

    def __init__(self, rpc: RpcClient):
        super().__init__(rpc)
        self._pool_cache: dict[str, dict] = {}  # Cache pool states

    # ========== Pool Operations ==========

    def get_pool(self, pool_address: str) -> Pool:
        """Get pool information by address"""
        state = self._fetch_pool_state(pool_address)
        return pool_state_to_pool(pool_address, state)

    def _fetch_pool_state(self, pool_address: str, refresh: bool = False) -> dict:
        """Fetch pool state with caching"""
        if not refresh and pool_address in self._pool_cache:
            return self._pool_cache[pool_address]

        state = fetch_pool_state(self._rpc, pool_address)
        self._pool_cache[pool_address] = state
        return state

    # ========== Position Operations ==========

    def get_positions(
        self,
        owner: str,
        pool: Optional[str] = None,
    ) -> List[Position]:
        """Get all positions owned by address"""
        position_states = fetch_positions_by_owner(self._rpc, owner, pool)

        positions = []
        for state in position_states:
            try:
                pool_obj = self.get_pool(state["pool_id"])
                position = position_state_to_position(state, pool_obj, owner)
                positions.append(position)
            except PoolUnavailable as e:
                logger.debug(
                    f"Skipping position {state.get('nft_mint', 'unknown')}: pool unavailable - {e}"
                )
                continue
            except Exception as e:
                logger.warning(
                    f"Failed to process position {state.get('nft_mint', 'unknown')}: {e}",
                    exc_info=True,
                )
                continue

        return positions

    def get_position(self, position_id: str) -> Position:
        """Get single position by NFT mint"""
        state = fetch_position_by_nft(self._rpc, position_id)
        if not state:
            raise PositionNotFound.not_found(position_id)

        pool = self.get_pool(state["pool_id"])

        # Get owner from NFT token account by finding the largest holder
        owner = self._get_nft_owner(position_id)

        return position_state_to_position(state, pool, owner)

    def _get_nft_owner(self, nft_mint: str) -> str:
        """
        Get the owner of an NFT by finding the token account holder.

        Supports both Tokenkeg and Token-2022 NFTs.
        """
        try:
            # Use getTokenLargestAccounts to find the holder
            largest = self._rpc.get_token_largest_accounts(nft_mint)
            if not largest or not isinstance(largest, list):
                return ""

            for account_info in largest:
                amount = account_info.get("amount", "0")
                if amount != "0":
                    token_account = account_info.get("address")
                    if not token_account:
                        continue

                    account_data = self._rpc.get_account_info(
                        token_account, encoding="jsonParsed"
                    )
                    if not account_data:
                        continue

                    data = account_data.get("data", {})
                    if isinstance(data, dict):
                        program = data.get("program")
                        # Support both spl-token and spl-token-2022
                        if program in ("spl-token", "spl-token-2022"):
                            parsed = data.get("parsed", {}).get("info", {})
                            owner = parsed.get("owner", "")
                            if owner:
                                return owner
        except Exception as e:
            logger.debug(f"Failed to get NFT owner for mint {nft_mint}: {e}", exc_info=True)

        return ""

    # ========== Instruction Building ==========

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
        Build instructions to open LP position.

        Uses open_position_with_token22_nft which creates a Token-2022 NFT
        for the position. This is the preferred method for new positions.

        Args:
            pool: Pool to open position in
            price_range: Price range specification
            amount0: Amount of token0 to deposit
            amount1: Amount of token1 to deposit
            owner: Owner wallet address
            slippage_bps: Slippage tolerance in basis points

        Returns:
            Tuple of (instructions, extra_signers)
            - instructions: List of instructions to execute
            - extra_signers: List of keypairs that must sign (includes NFT mint)
        """
        pool_state = self._fetch_pool_state(pool.address)

        # Convert price range to ticks
        tick_lower, tick_upper = self.price_range_to_ticks(pool, price_range)

        # Calculate sqrt prices
        sqrt_price_lower = tick_to_sqrt_price_x64(tick_lower)
        sqrt_price_upper = tick_to_sqrt_price_x64(tick_upper)
        sqrt_price_current = pool_state["sqrt_price_x64"]

        # Convert amounts to raw
        amount0_raw = int(amount0 * Decimal(10 ** pool.token0.decimals))
        amount1_raw = int(amount1 * Decimal(10 ** pool.token1.decimals))

        # Calculate liquidity
        liquidity = get_liquidity_from_amounts(
            amount0_raw,
            amount1_raw,
            sqrt_price_current,
            sqrt_price_lower,
            sqrt_price_upper,
        )

        # Apply slippage for max amounts
        slippage_factor = Decimal(1) + Decimal(slippage_bps) / Decimal(10000)
        amount0_max = int(Decimal(amount0_raw) * slippage_factor)
        amount1_max = int(Decimal(amount1_raw) * slippage_factor)

        # Build wrap SOL instructions if needed (prepended to transaction)
        # See WSOL_WRAP_BUFFER_LAMPORTS for buffer documentation
        wrap_instructions = []
        if pool.token0.mint == WRAPPED_SOL_MINT and amount0_max > 0:
            wrap_amount = amount0_max + WSOL_WRAP_BUFFER_LAMPORTS
            wrap_instructions.extend(build_wrap_sol_instructions(owner, wrap_amount))
        if pool.token1.mint == WRAPPED_SOL_MINT and amount1_max > 0:
            wrap_amount = amount1_max + WSOL_WRAP_BUFFER_LAMPORTS
            wrap_instructions.extend(build_wrap_sol_instructions(owner, wrap_amount))

        # Build open position instructions with Token-2022 NFT
        instructions, nft_mint = build_open_position_instructions(
            pool_address=pool.address,
            pool_state=pool_state,
            owner=owner,
            tick_lower=tick_lower,
            tick_upper=tick_upper,
            liquidity=liquidity,
            amount_0_max=amount0_max,
            amount_1_max=amount1_max,
            with_metadata=True,
            rpc=self._rpc,  # Pass RPC for token program detection
        )

        # Prepend wrap instructions
        all_instructions = wrap_instructions + instructions

        return all_instructions, [nft_mint]

    def build_close_position(
        self,
        position: Position,
        owner: str,
    ) -> List["Instruction"]:
        """
        Build instructions to close position.

        This will:
        1. Decrease all liquidity (if any)
        2. Close the position (burn NFT)
        3. Optionally unwrap WSOL

        Args:
            position: Position to close
            owner: Owner wallet address

        Returns:
            List of instructions to execute
        """
        # Fetch fresh states
        pool_state = self._fetch_pool_state(position.pool.address, refresh=True)
        position_state = fetch_position_by_nft(self._rpc, position.nft_mint)

        if not position_state:
            raise PositionNotFound.not_found(position.id)

        instructions = []

        # First decrease all liquidity AND collect fees/rewards
        # IMPORTANT: Even if liquidity is 0, we must call decrease_liquidity
        # with delta=0 to collect any pending fees and rewards.
        # Raydium's close_position requires all fees/rewards to be claimed first.
        # Error 101 (ClosePositionErr) occurs if fees/rewards remain uncollected.
        liquidity_delta = position_state["liquidity"]
        decrease_ixs = build_decrease_liquidity_instructions(
            position_state=position_state,
            pool_state=pool_state,
            owner=owner,
            liquidity_delta=liquidity_delta,  # Can be 0 to just collect fees
            amount_0_min=0,
            amount_1_min=0,
            rpc=self._rpc,  # Pass RPC for token program detection
        )
        instructions.extend(decrease_ixs)

        # Then close the position
        close_ixs = build_close_position_instructions(
            position_state=position_state,
            pool_state=pool_state,
            owner=owner,
            rpc=self._rpc,
        )
        instructions.extend(close_ixs)

        # Optionally add WSOL unwrap if pool contains WSOL
        if pool_state["mint_a"] == WRAPPED_SOL_MINT or pool_state["mint_b"] == WRAPPED_SOL_MINT:
            unwrap_ixs = build_unwrap_wsol_instructions(owner, rpc=self._rpc)
            instructions.extend(unwrap_ixs)

        return instructions

    def generate_close_position_steps(
        self,
        position: Position,
        owner: str,
    ):
        """
        Generate multi-step close position instructions.

        Raydium's close_position requires the position to have:
        - 0 liquidity
        - 0 unclaimed fees
        - 0 unclaimed rewards

        This generator yields instruction sets for each step:
        1. Remove ALL liquidity (if any)
        2. Claim remaining fees/rewards (decrease_liquidity with delta=0)
        3. Close position (burn NFT)

        Yields:
            Tuple of (instructions, step_description, is_final)

        Usage:
            for instructions, desc, is_final in adapter.generate_close_position_steps(pos, owner):
                result = tx_builder.build_and_send(instructions, ...)
                if not result.is_success and is_final:
                    return result
        """
        import logging
        logger = logging.getLogger(__name__)

        logger.debug(f"Closing Raydium position {position.nft_mint}")

        # Step 1: Remove all liquidity
        pool_state = self._fetch_pool_state(position.pool.address, refresh=True)
        position_state = fetch_position_by_nft(self._rpc, position.nft_mint)

        if not position_state:
            return  # Position already closed

        current_liquidity = position_state.get("liquidity", 0)
        logger.debug(f"Position liquidity: {current_liquidity}")

        if current_liquidity > 0:
            remove_instructions = build_decrease_liquidity_instructions(
                position_state=position_state,
                pool_state=pool_state,
                owner=owner,
                liquidity_delta=current_liquidity,
                amount_0_min=0,
                amount_1_min=0,
                rpc=self._rpc,
            )
            if remove_instructions:
                yield (remove_instructions, "remove_liquidity", False)

        # Step 2: Claim remaining fees/rewards
        pool_state = self._fetch_pool_state(position.pool.address, refresh=True)
        position_state = fetch_position_by_nft(self._rpc, position.nft_mint)

        if not position_state:
            return  # Position closed during liquidity removal

        claim_instructions = build_decrease_liquidity_instructions(
            position_state=position_state,
            pool_state=pool_state,
            owner=owner,
            liquidity_delta=0,  # 0 = just collect fees/rewards
            amount_0_min=0,
            amount_1_min=0,
            rpc=self._rpc,
        )
        if claim_instructions:
            yield (claim_instructions, "claim_fees", False)

        # Step 3: Close position
        pool_state = self._fetch_pool_state(position.pool.address, refresh=True)
        position_state = fetch_position_by_nft(self._rpc, position.nft_mint)

        if not position_state:
            return  # Position closed during claim

        close_instructions = build_close_position_instructions(
            position_state=position_state,
            pool_state=pool_state,
            owner=owner,
            rpc=self._rpc,
        )

        # Add WSOL unwrap if needed
        if pool_state["mint_a"] == WRAPPED_SOL_MINT or pool_state["mint_b"] == WRAPPED_SOL_MINT:
            close_instructions.extend(build_unwrap_wsol_instructions(owner, rpc=self._rpc))

        yield (close_instructions, "close_position", True)

    def build_close_position_with_simulation(
        self,
        position: Position,
        owner: str,
    ) -> Tuple[List["Instruction"], callable]:
        """
        Build close position instructions with multi-variant simulation.

        Returns instructions and a selector function that picks the working
        variant through simulation.

        Args:
            position: Position to close
            owner: Owner wallet address

        Returns:
            Tuple of (instructions, selector_fn)
        """
        from solders.pubkey import Pubkey

        pool_state = self._fetch_pool_state(position.pool.address, refresh=True)
        position_state = fetch_position_by_nft(self._rpc, position.nft_mint)

        if not position_state:
            raise PositionNotFound.not_found(position.id)

        instructions = []

        # Decrease liquidity AND collect fees/rewards first
        # (Always call even if liquidity is 0 to collect fees/rewards)
        liquidity_delta = position_state["liquidity"]
        decrease_ixs = build_decrease_liquidity_instructions(
            position_state=position_state,
            pool_state=pool_state,
            owner=owner,
            liquidity_delta=liquidity_delta,
            amount_0_min=0,
            amount_1_min=0,
            rpc=self._rpc,
        )
        instructions.extend(decrease_ixs)

        # Get close position candidates
        nft_mint = Pubkey.from_string(position_state["nft_mint"])
        owner_pubkey = Pubkey.from_string(owner)

        # Detect NFT token program
        token_program_nft = detect_token_program_for_mint(self._rpc, nft_mint)
        nft_account = get_associated_token_address(owner_pubkey, nft_mint, token_program_nft)

        candidates = build_close_position_candidates(
            position_state=position_state,
            pool_state=pool_state,
            owner=owner,
            nft_account=nft_account,
            token_program_nft=token_program_nft,
        )

        # Return base instructions and candidates for simulation
        return instructions, candidates

    def build_add_liquidity(
        self,
        position: Position,
        amount0: Decimal,
        amount1: Decimal,
        owner: str,
        slippage_bps: int = 50,
    ) -> List["Instruction"]:
        """
        Build instructions to add liquidity to existing position.

        Args:
            position: Position to add liquidity to
            amount0: Amount of token0 to add
            amount1: Amount of token1 to add
            owner: Owner wallet address
            slippage_bps: Slippage tolerance in basis points

        Returns:
            List of instructions to execute
        """
        if not position.nft_mint:
            raise PositionNotFound(
                f"Position has no NFT mint: {position.id or 'unknown'}",
                position_id=position.id,
            )

        # Fetch fresh states
        pool_state = self._fetch_pool_state(position.pool.address, refresh=True)
        position_state = fetch_position_by_nft(self._rpc, position.nft_mint)

        if not position_state:
            raise PositionNotFound.not_found(position.id or "unknown")

        # Convert amounts to raw
        amount0_raw = int(amount0 * Decimal(10 ** position.pool.token0.decimals))
        amount1_raw = int(amount1 * Decimal(10 ** position.pool.token1.decimals))

        # Calculate sqrt prices for range
        sqrt_price_lower = tick_to_sqrt_price_x64(position_state["tick_lower"])
        sqrt_price_upper = tick_to_sqrt_price_x64(position_state["tick_upper"])
        sqrt_price_current = pool_state["sqrt_price_x64"]

        # Calculate liquidity from amounts
        liquidity = get_liquidity_from_amounts(
            amount0_raw,
            amount1_raw,
            sqrt_price_current,
            sqrt_price_lower,
            sqrt_price_upper,
        )

        if liquidity == 0:
            return []

        # Apply slippage for max amounts
        slippage_factor = Decimal(1) + Decimal(slippage_bps) / Decimal(10000)
        amount0_max = int(Decimal(amount0_raw) * slippage_factor)
        amount1_max = int(Decimal(amount1_raw) * slippage_factor)

        return build_increase_liquidity_instructions(
            position_state=position_state,
            pool_state=pool_state,
            owner=owner,
            liquidity_delta=liquidity,
            amount_0_max=amount0_max,
            amount_1_max=amount1_max,
            rpc=self._rpc,
        )

    def build_remove_liquidity(
        self,
        position: Position,
        liquidity_percent: float,
        owner: str,
        slippage_bps: int = 50,
    ) -> List["Instruction"]:
        """
        Build instructions to remove liquidity.

        Args:
            position: Position to remove liquidity from
            liquidity_percent: Percentage of liquidity to remove (0-100)
            owner: Owner wallet address
            slippage_bps: Slippage tolerance (not currently used for min amounts)

        Returns:
            List of instructions to execute
        """
        if not position.nft_mint:
            raise PositionNotFound(
                f"Position has no NFT mint: {position.id or 'unknown'}",
                position_id=position.id,
            )

        pool_state = self._fetch_pool_state(position.pool.address, refresh=True)
        position_state = fetch_position_by_nft(self._rpc, position.nft_mint)

        if not position_state:
            raise PositionNotFound.not_found(position.id or "unknown")

        # Calculate liquidity to remove
        liquidity_delta = int(position_state["liquidity"] * liquidity_percent / 100)

        if liquidity_delta == 0:
            return []

        return build_decrease_liquidity_instructions(
            position_state=position_state,
            pool_state=pool_state,
            owner=owner,
            liquidity_delta=liquidity_delta,
            amount_0_min=0,
            amount_1_min=0,
            rpc=self._rpc,
        )

    def build_claim_fees(
        self,
        position: Position,
        owner: str,
    ) -> List["Instruction"]:
        """
        Build instructions to claim fees.

        In Raydium, fees are collected when decreasing liquidity.
        To claim without removing liquidity, we decrease 0 liquidity.

        Args:
            position: Position to claim fees from
            owner: Owner wallet address

        Returns:
            List of instructions to execute
        """
        if not position.nft_mint:
            raise PositionNotFound(
                f"Position has no NFT mint: {position.id or 'unknown'}",
                position_id=position.id,
            )

        pool_state = self._fetch_pool_state(position.pool.address, refresh=True)
        position_state = fetch_position_by_nft(self._rpc, position.nft_mint)

        if not position_state:
            raise PositionNotFound.not_found(position.id or "unknown")

        return build_decrease_liquidity_instructions(
            position_state=position_state,
            pool_state=pool_state,
            owner=owner,
            liquidity_delta=0,  # 0 liquidity = just collect fees
            amount_0_min=0,
            amount_1_min=0,
            rpc=self._rpc,
        )

    # ========== Price/Range Calculations ==========

    # USD stablecoin mints
    USD_STABLECOINS = {
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
        "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
    }

    def calculate_amounts_for_range(
        self,
        pool: Pool,
        price_range: PriceRange,
        target_value_usd: Decimal,
    ) -> tuple[Decimal, Decimal]:
        """
        Calculate token amounts for a given range and USD value.

        Note: This method assumes token1 is a USD stablecoin (USDC/USDT).
        For non-USD pairs, use explicit amount0/amount1 parameters instead.

        Args:
            pool: Pool to open position in
            price_range: Price range specification
            target_value_usd: Target USD value to deposit

        Returns:
            (amount0, amount1) tuple
        """
        # Validate that token1 is a USD stablecoin
        if pool.token1.mint not in self.USD_STABLECOINS:
            raise ConfigurationError.invalid(
                "pool",
                f"amount_usd requires a USD-quoted pool (token1 must be USDC or USDT). "
                f"Pool {pool.address} has token1={pool.token1.symbol or pool.token1.mint}. "
                f"Use explicit amount0/amount1 parameters for non-USD pairs."
            )

        pool_state = self._fetch_pool_state(pool.address)

        tick_lower, tick_upper = self.price_range_to_ticks(pool, price_range)

        sqrt_price_lower = tick_to_sqrt_price_x64(tick_lower)
        sqrt_price_upper = tick_to_sqrt_price_x64(tick_upper)
        sqrt_price_current = pool_state["sqrt_price_x64"]

        current_price = pool.price
        price_lower = tick_to_price(tick_lower, pool.token0.decimals, pool.token1.decimals)
        price_upper = tick_to_price(tick_upper, pool.token0.decimals, pool.token1.decimals)

        # Validate current_price to avoid division by zero
        if current_price <= Decimal(0):
            raise ValueError(
                f"Cannot calculate amounts: pool price is {current_price}. "
                f"Price must be positive."
            )

        # Calculate amounts based on price position in range
        if price_lower <= current_price <= price_upper:
            # In range: split value based on price position
            value_per_token = target_value_usd / 2
            amount0 = value_per_token / current_price
            amount1 = value_per_token
        elif current_price < price_lower:
            # Below range: all token0
            amount0 = target_value_usd / current_price
            amount1 = Decimal(0)
        else:
            # Above range: all token1
            amount0 = Decimal(0)
            amount1 = target_value_usd

        return amount0, amount1

    def price_range_to_ticks(
        self,
        pool: Pool,
        price_range: PriceRange,
    ) -> tuple[int, int]:
        """Convert price range to ticks"""
        tick_spacing = pool.tick_spacing or 1
        current_tick = pool.current_tick or 0
        decimals_a = pool.token0.decimals
        decimals_b = pool.token1.decimals

        if price_range.mode == RangeMode.ONE_TICK:
            return one_tick_range(current_tick, tick_spacing)

        if price_range.mode == RangeMode.TICK_RANGE:
            return int(price_range.lower), int(price_range.upper)

        if price_range.mode in (RangeMode.PERCENT, RangeMode.BPS):
            current_price = pool.price
            lower_price, upper_price = price_range.to_absolute(current_price)

            tick_lower = price_to_tick(lower_price, decimals_a, decimals_b, tick_spacing)
            tick_upper = price_to_tick(upper_price, decimals_a, decimals_b, tick_spacing)

            return tick_lower, tick_upper

        if price_range.mode == RangeMode.ABSOLUTE:
            tick_lower = price_to_tick(price_range.lower, decimals_a, decimals_b, tick_spacing)
            tick_upper = price_to_tick(price_range.upper, decimals_a, decimals_b, tick_spacing)
            return tick_lower, tick_upper

        raise OperationNotSupported.not_implemented(f"price_range_mode:{price_range.mode}", "raydium")

    def ticks_to_prices(
        self,
        pool: Pool,
        lower_tick: int,
        upper_tick: int,
    ) -> tuple[Decimal, Decimal]:
        """Convert ticks to prices"""
        decimals_a = pool.token0.decimals
        decimals_b = pool.token1.decimals

        price_lower = tick_to_price(lower_tick, decimals_a, decimals_b)
        price_upper = tick_to_price(upper_tick, decimals_a, decimals_b)

        return price_lower, price_upper
