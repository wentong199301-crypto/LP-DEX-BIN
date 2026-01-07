"""
Meteora DLMM Protocol Adapter

Implements ProtocolAdapter interface for Meteora Dynamic Liquidity.
"""

import logging
import struct
import base64
from decimal import Decimal
from typing import List, Optional, Dict, Any, Tuple, TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from solders.instruction import Instruction
    from solders.keypair import Keypair

from ..base import ProtocolAdapter
from ...types import Pool, Position, PriceRange, RangeMode, Token
from ...infra import RpcClient
from ...errors import PoolUnavailable, PositionNotFound, ConfigurationError, OperationNotSupported

from .constants import (
    DLMM_PROGRAM_ID,
    StrategyType,
    ACCOUNT_DISCRIMINATORS,
    POSITION_LB_PAIR_OFFSET,
    POSITION_OWNER_OFFSET,
    POSITION_LIQUIDITY_SHARES_OFFSET,
    POSITION_LOWER_BIN_ID_OFFSET,
    POSITION_UPPER_BIN_ID_OFFSET,
    MAX_POSITION_WIDTH,
)
from .math import (
    bin_id_to_price,
    price_to_bin_id,
    one_bin_range,
    get_bin_array_index,
)
from .instructions import (
    build_initialize_position_instructions,
    build_initialize_bin_array_instructions,
    build_initialize_bitmap_extension_instructions,
    build_add_liquidity_by_strategy_instructions,
    build_remove_liquidity_instructions,
    build_close_position_instructions as build_close_position_ixs,
    build_claim_fee_instructions,
    WRAPPED_SOL_MINT,
)


class MeteoraAdapter(ProtocolAdapter):
    """
    Meteora DLMM Protocol Adapter

    Provides unified interface for:
    - Pool queries (LbPair)
    - Position management
    - LP operations

    Usage:
        rpc = RpcClient("https://api.mainnet-beta.solana.com")
        adapter = MeteoraAdapter(rpc)

        pool = adapter.get_pool("pool_address...")
    """

    name = "meteora"
    program_id = DLMM_PROGRAM_ID

    def __init__(self, rpc: RpcClient):
        super().__init__(rpc)
        self._pool_cache: Dict[str, Dict] = {}
        self._decimals_cache: Dict[str, int] = {}

    def _get_token_decimals(self, mint: str) -> int:
        """
        Fetch token decimals from mint account with caching

        Note: This duplicates similar caching in JupiterAdapter. A shared
        utility could consolidate this, but would require mixing types
        layer with infrastructure dependencies.
        """
        if mint in self._decimals_cache:
            return self._decimals_cache[mint]

        try:
            account = self._rpc.get_account_info(mint, encoding="jsonParsed")
            if account and "parsed" in account.get("data", {}):
                decimals = account["data"]["parsed"]["info"]["decimals"]
                self._decimals_cache[mint] = decimals
                return decimals
        except Exception:
            pass

        # Default fallback (SOL-like tokens = 9 decimals)
        return 9

    # ========== Pool Operations ==========

    def get_pool(self, pool_address: str) -> Pool:
        """Get pool information by address"""
        state = self._fetch_pool_state(pool_address)
        return self._state_to_pool(pool_address, state)

    def _fetch_pool_state(self, pool_address: str, refresh: bool = False) -> Dict[str, Any]:
        """Fetch and parse LbPair account"""
        if not refresh and pool_address in self._pool_cache:
            return self._pool_cache[pool_address]

        account = self._rpc.get_account_info(pool_address, encoding="base64")
        if not account:
            raise PoolUnavailable.not_found(pool_address)

        # Validate account owner matches Meteora DLMM program ID
        owner = account.get("owner")
        if owner != DLMM_PROGRAM_ID:
            raise PoolUnavailable.invalid_state(
                pool_address,
                f"Account not owned by Meteora DLMM program (owner={owner})"
            )

        data = account.get("data", [])
        if isinstance(data, list) and len(data) > 0:
            raw_data = base64.b64decode(data[0])
        elif isinstance(data, str):
            raw_data = base64.b64decode(data)
        else:
            raise PoolUnavailable.invalid_state(pool_address, "Invalid data format")

        state = self._parse_lb_pair(raw_data)
        self._pool_cache[pool_address] = state
        return state

    def _parse_lb_pair(self, data: bytes) -> Dict[str, Any]:
        """Parse LbPair account structure (DLMM v2)

        Structure layout (verified against on-chain SOL/USDC pool 8M5rjeDQKW4w4rmW...):
        - [0-7]: Discriminator (8 bytes)
        - [8-75]: Parameters block (68 bytes, contains active_id at 76, bin_step at 80)
        - [76]: active_id (i32)
        - [80]: bin_step (u16)
        - [88-119]: mint_x (32 bytes) - token X mint (e.g., WSOL)
        - [120-151]: mint_y (32 bytes) - token Y mint (e.g., USDC)
        - [152-183]: reserve_x (32 bytes) - vault/reserve for token X
        - [184-215]: reserve_y (32 bytes) - vault/reserve for token Y
        """
        # Bin step at offset 80
        bin_step = struct.unpack_from("<H", data, 80)[0]

        # Base factor at offset 84
        base_factor = struct.unpack_from("<H", data, 84)[0]

        # Mint X at offset 88
        mint_x = self._pubkey_from_bytes(data[88:120])

        # Mint Y at offset 120
        mint_y = self._pubkey_from_bytes(data[120:152])

        # Reserve X (vault_x) at offset 152
        vault_x = self._pubkey_from_bytes(data[152:184])

        # Reserve Y (vault_y) at offset 184
        vault_y = self._pubkey_from_bytes(data[184:216])

        # Active bin ID at offset 76
        active_id = struct.unpack_from("<i", data, 76)[0]

        return {
            "vault_x": vault_x,
            "vault_y": vault_y,
            "mint_x": mint_x,
            "mint_y": mint_y,
            "bin_step": bin_step,
            "active_id": active_id,
            "base_factor": base_factor,
        }

    def _state_to_pool(self, address: str, state: Dict[str, Any]) -> Pool:
        """Convert parsed state to Pool"""
        # Fetch token decimals from mint accounts
        decimals_x = self._get_token_decimals(state["mint_x"])
        decimals_y = self._get_token_decimals(state["mint_y"])

        price = bin_id_to_price(
            state["active_id"],
            state["bin_step"],
            decimals_x,
            decimals_y,
        )

        token_x = Token(mint=state["mint_x"], symbol="", decimals=decimals_x)
        token_y = Token(mint=state["mint_y"], symbol="", decimals=decimals_y)

        # Calculate fee rate from bin_step
        fee_rate = Decimal(state["bin_step"]) / Decimal(10000)

        return Pool(
            address=address,
            dex="meteora",
            symbol=f"{token_x.symbol or 'X'}/{token_y.symbol or 'Y'}",
            token0=token_x,
            token1=token_y,
            price=price,
            fee_rate=fee_rate,
            bin_step=state["bin_step"],
            active_bin_id=state["active_id"],
            metadata={
                "vault_x": state["vault_x"],
                "vault_y": state["vault_y"],
            },
        )

    # ========== Position Operations ==========

    def get_positions(
        self,
        owner: str,
        pool: Optional[str] = None,
    ) -> List[Position]:
        """
        Get positions owned by address using getProgramAccounts

        Args:
            owner: Owner wallet address
            pool: Optional pool address to filter by

        Returns:
            List of Position objects with bin_ids populated
        """
        import base58

        positions: List[Position] = []

        # Build filters: discriminator + owner
        # Owner is at offset 40 (after 8 byte discriminator + 32 byte lb_pair)
        owner_bytes = base58.b58decode(owner)
        owner_b58 = base58.b58encode(owner_bytes).decode("ascii")

        filters = [
            # Filter by Position discriminator at offset 0
            {
                "memcmp": {
                    "offset": 0,
                    "bytes": base58.b58encode(ACCOUNT_DISCRIMINATORS["position_v2"]).decode("ascii"),
                }
            },
            # Filter by owner at offset 40
            {
                "memcmp": {
                    "offset": POSITION_OWNER_OFFSET,
                    "bytes": owner_b58,
                }
            },
        ]

        try:
            accounts = self._rpc.get_program_accounts(
                DLMM_PROGRAM_ID,
                filters=filters,
                encoding="base64",
            )
        except Exception as e:
            logger.warning(f"Failed to query Meteora positions: {e}")
            return []

        for account in accounts:
            try:
                pubkey = account.get("pubkey")
                account_data = account.get("account", {})
                data = account_data.get("data", [])

                if isinstance(data, list) and len(data) > 0:
                    raw_data = base64.b64decode(data[0])
                elif isinstance(data, str):
                    raw_data = base64.b64decode(data)
                else:
                    continue

                position = self._parse_position(pubkey, raw_data)
                if position:
                    # Filter by pool if specified
                    if pool and position.pool.address != pool:
                        continue
                    positions.append(position)

            except Exception as e:
                logger.debug(f"Failed to parse position {account.get('pubkey')}: {e}")
                continue

        return positions

    def get_position(self, position_id: str) -> Position:
        """
        Get single position by address

        Args:
            position_id: Position account address

        Returns:
            Position object with bin_ids populated

        Raises:
            PositionNotFound: If position doesn't exist or couldn't be parsed
        """
        account = self._rpc.get_account_info(position_id, encoding="base64")
        if not account:
            raise PositionNotFound.not_found(position_id)

        data = account.get("data", [])
        if isinstance(data, list) and len(data) > 0:
            raw_data = base64.b64decode(data[0])
        elif isinstance(data, str):
            raw_data = base64.b64decode(data)
        else:
            raise PositionNotFound.not_found(position_id)

        position = self._parse_position(position_id, raw_data)
        if not position:
            raise PositionNotFound.not_found(position_id)

        return position

    def _parse_position(self, address: str, data: bytes) -> Optional[Position]:
        """
        Parse Meteora PositionV2 account data

        PositionV2 structure (based on on-chain analysis):
        - discriminator: 8 bytes at offset 0
        - lb_pair: Pubkey (32 bytes) at offset 8
        - owner: Pubkey (32 bytes) at offset 40
        - liquidity_shares: [u128; 490] = 7840 bytes at offset 72
        - lower_bin_id: i32 at offset 7912
        - upper_bin_id: i32 at offset 7916
        - last_updated_at: i64 at offset 7920
        - ...

        Args:
            address: Position account address
            data: Raw account data bytes

        Returns:
            Position object or None if parsing fails
        """
        # Minimum size check - need at least to offset 7920
        if len(data) < 7920:
            logger.debug(f"Position {address} data too small: {len(data)} bytes")
            return None

        # Verify discriminator
        discriminator = data[0:8]
        if discriminator != ACCOUNT_DISCRIMINATORS["position_v2"]:
            logger.debug(f"Position {address} has wrong discriminator")
            return None

        try:
            # Parse lb_pair (pool address)
            lb_pair = self._pubkey_from_bytes(data[POSITION_LB_PAIR_OFFSET:POSITION_LB_PAIR_OFFSET + 32])

            # Parse owner
            owner = self._pubkey_from_bytes(data[POSITION_OWNER_OFFSET:POSITION_OWNER_OFFSET + 32])

            # Parse bin IDs at their known offsets
            lower_bin_id = struct.unpack_from("<i", data, POSITION_LOWER_BIN_ID_OFFSET)[0]
            upper_bin_id = struct.unpack_from("<i", data, POSITION_UPPER_BIN_ID_OFFSET)[0]

            # Sanity check bin IDs
            if not (-500000 < lower_bin_id < 500000 and -500000 < upper_bin_id < 500000):
                logger.warning(f"Position {address} has invalid bin IDs: {lower_bin_id}, {upper_bin_id}")
                return None

            if upper_bin_id < lower_bin_id:
                logger.warning(f"Position {address} has upper < lower bin ID")
                return None

            # Parse liquidity shares for the position's bin range
            # The liquidity_shares array is indexed 0 to (upper - lower)
            position_width = upper_bin_id - lower_bin_id + 1
            liquidity_shares = []
            total_liquidity = 0

            # Warn if position is wider than MAX_POSITION_WIDTH - liquidity may be undercounted
            if position_width > MAX_POSITION_WIDTH:
                logger.warning(
                    f"Position {address} has {position_width} bins but only reading first "
                    f"{MAX_POSITION_WIDTH}. Liquidity and bin_ids may be incomplete."
                )

            for i in range(min(position_width, MAX_POSITION_WIDTH)):
                share_offset = POSITION_LIQUIDITY_SHARES_OFFSET + (i * 16)
                if share_offset + 16 > len(data):
                    break
                # u128 little-endian
                low = struct.unpack_from("<Q", data, share_offset)[0]
                high = struct.unpack_from("<Q", data, share_offset + 8)[0]
                share = low + (high << 64)
                liquidity_shares.append(share)
                total_liquidity += share

            # Calculate bin_ids list - these are the actual bin IDs with liquidity
            bin_ids = []
            for i, share in enumerate(liquidity_shares):
                if share > 0:
                    bin_ids.append(lower_bin_id + i)

            # Get pool info
            try:
                pool = self.get_pool(lb_pair)
            except Exception as e:
                logger.warning(f"Could not fetch pool {lb_pair} for position: {e}")
                return None

            # Calculate prices from bin IDs
            price_lower, price_upper = self.ticks_to_prices(pool, lower_bin_id, upper_bin_id)

            # Calculate total liquidity
            total_liquidity = sum(liquidity_shares)

            # Check if in range
            is_in_range = (
                pool.active_bin_id is not None
                and lower_bin_id <= pool.active_bin_id <= upper_bin_id
            )

            return Position(
                id=address,
                pool=pool,
                owner=owner,
                price_lower=price_lower,
                price_upper=price_upper,
                amount0=Decimal(0),  # Would need to query vault to get actual amounts
                amount1=Decimal(0),
                liquidity=total_liquidity,
                is_in_range=is_in_range,
                lower_bin_id=lower_bin_id,
                upper_bin_id=upper_bin_id,
                bin_ids=bin_ids,
                metadata={
                    "total_liquidity": str(total_liquidity),
                    "liquidity_shares": [str(s) for s in liquidity_shares if s > 0],
                },
            )

        except Exception as e:
            logger.debug(f"Failed to parse position {address}: {e}", exc_info=True)
            return None

    # ========== Instruction Building ==========

    def _get_uninitialized_bin_array_indices(
        self,
        pool_address: str,
        bin_array_indices: set,
    ) -> List[int]:
        """
        Check which bin arrays need to be initialized.

        Args:
            pool_address: LbPair address
            bin_array_indices: Set of bin array indices to check

        Returns:
            List of indices that need initialization
        """
        from solders.pubkey import Pubkey
        import struct as struct_module

        program_id = Pubkey.from_string(DLMM_PROGRAM_ID)
        lb_pair_pubkey = Pubkey.from_string(pool_address)

        uninitialized = []
        for bin_array_index in sorted(bin_array_indices):
            # Derive bin array PDA
            bin_array_pda, _ = Pubkey.find_program_address(
                [
                    b"bin_array",
                    bytes(lb_pair_pubkey),
                    struct_module.pack("<q", bin_array_index),
                ],
                program_id,
            )

            # Check if account exists
            try:
                account = self._rpc.get_account_info(str(bin_array_pda), encoding="base64")
                if not account or account.get("data") is None:
                    uninitialized.append(bin_array_index)
                else:
                    data = account.get("data", [])
                    if isinstance(data, list) and len(data) > 0:
                        raw_data = base64.b64decode(data[0])
                    elif isinstance(data, str):
                        raw_data = base64.b64decode(data)
                    else:
                        uninitialized.append(bin_array_index)
                        continue

                    # If account has no data or is too short, it needs initialization
                    if len(raw_data) < 8:
                        uninitialized.append(bin_array_index)
            except Exception:
                # If we can't fetch it, assume it needs initialization
                uninitialized.append(bin_array_index)

        return uninitialized

    def _check_bitmap_extension_exists(self, pool_address: str) -> bool:
        """
        Check if the bitmap extension PDA exists for a pool.

        Args:
            pool_address: LbPair address

        Returns:
            True if bitmap extension exists and is initialized
        """
        from solders.pubkey import Pubkey

        program_id = Pubkey.from_string(DLMM_PROGRAM_ID)
        lb_pair_pubkey = Pubkey.from_string(pool_address)

        # Derive bitmap extension PDA
        bitmap_extension, _ = Pubkey.find_program_address(
            [b"bitmap", bytes(lb_pair_pubkey)],
            program_id,
        )

        try:
            account = self._rpc.get_account_info(str(bitmap_extension), encoding="base64")
            if not account or account.get("data") is None:
                return False

            data = account.get("data", [])
            if isinstance(data, list) and len(data) > 0:
                raw_data = base64.b64decode(data[0])
            elif isinstance(data, str):
                raw_data = base64.b64decode(data)
            else:
                return False

            # Check if it has data (initialized accounts have data)
            return len(raw_data) > 0
        except Exception:
            return False

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
        Build instructions to open position

        Meteora uses initialize_position + add_liquidity_by_strategy.

        Args:
            pool: Pool to open position in
            price_range: Price range specification
            amount0: Amount of token X
            amount1: Amount of token Y
            owner: Owner wallet
            slippage_bps: Slippage tolerance

        Returns:
            Tuple of (instructions, [position_keypair])
        """
        pool_state = self._fetch_pool_state(pool.address)
        active_id = pool_state["active_id"]

        # Convert price range to bin IDs
        lower_bin, upper_bin = self.price_range_to_ticks(pool, price_range)

        # Check bin array indices for the position range
        lower_array_idx = get_bin_array_index(lower_bin)
        upper_array_idx = get_bin_array_index(upper_bin)

        # Ensure position spans 2 different bin arrays to avoid AccountBorrowFailed
        # When both bins are in the same array, Anchor tries to borrow the same
        # account twice as mutable, causing an error
        from .math import get_bin_array_lower_upper_bin_id

        if lower_array_idx == upper_array_idx:
            # Both bins in same array - need to expand to span 2 arrays
            array_lower_bound, array_upper_bound = get_bin_array_lower_upper_bin_id(lower_array_idx)

            # Decide which direction to expand based on which is closer
            dist_to_lower = abs(lower_bin - (array_lower_bound - 1))
            dist_to_upper = abs((array_upper_bound + 1) - upper_bin)

            if dist_to_lower <= dist_to_upper:
                # Extend lower_bin into previous array
                lower_bin = array_lower_bound - 1
            else:
                # Extend upper_bin into next array
                upper_bin = array_upper_bound + 1

            logger.debug(
                f"Expanded bin range to span 2 arrays: {lower_bin} to {upper_bin} "
                f"(arrays {get_bin_array_index(lower_bin)} to {get_bin_array_index(upper_bin)})"
            )

        width = upper_bin - lower_bin + 1

        instructions = []

        # Initialize bin arrays if needed
        # Determine which bin array indices are required for this position range
        bin_array_indices = set()
        for bin_id in range(lower_bin, upper_bin + 1):
            bin_array_indices.add(get_bin_array_index(bin_id))

        # Check which bin arrays need initialization (don't exist yet)
        uninitialized_indices = self._get_uninitialized_bin_array_indices(
            pool.address, bin_array_indices
        )

        # Build initialization instructions only for uninitialized bin arrays
        for bin_array_index in uninitialized_indices:
            init_bin_array_ixs = build_initialize_bin_array_instructions(
                lb_pair=pool.address,
                bin_array_index=bin_array_index,
                funder=owner,
            )
            instructions.extend(init_bin_array_ixs)

        # Initialize bitmap extension if needed
        # The bitmap extension PDA must exist before addLiquidityByStrategy
        bitmap_exists = self._check_bitmap_extension_exists(pool.address)
        if not bitmap_exists:
            init_bitmap_ixs = build_initialize_bitmap_extension_instructions(
                lb_pair=pool.address,
                funder=owner,
            )
            instructions.extend(init_bitmap_ixs)

        # Initialize position (use V1 - V2 has account size issues)
        init_ixs, position_kp = build_initialize_position_instructions(
            lb_pair=pool.address,
            owner=owner,
            lower_bin_id=lower_bin,
            width=width,
            use_v2=False,
        )
        instructions.extend(init_ixs)

        # Convert amounts to raw
        amount_x_raw = int(amount0 * Decimal(10 ** pool.token0.decimals))
        amount_y_raw = int(amount1 * Decimal(10 ** pool.token1.decimals))

        # Add liquidity (with rpc for Token-2022 support)
        add_ixs = build_add_liquidity_by_strategy_instructions(
            lb_pair=pool.address,
            pool_state=pool_state,
            position=str(position_kp.pubkey()),
            owner=owner,
            amount_x=amount_x_raw,
            amount_y=amount_y_raw,
            active_id=active_id,
            min_bin_id=lower_bin,
            max_bin_id=upper_bin,
            max_active_bin_slippage=slippage_bps // 10,  # Convert to bins
            strategy_type=StrategyType.SPOT_BALANCED,
            rpc=self._rpc,
        )
        instructions.extend(add_ixs)

        return instructions, [position_kp]

    def build_close_position(
        self,
        position: Position,
        owner: str,
    ) -> List["Instruction"]:
        """
        Build instructions to close position

        First removes all liquidity, then closes the position account.
        """
        pool_state = self._fetch_pool_state(position.pool.address, refresh=True)

        # Build position_state dict with bin IDs
        position_state = {
            "lower_bin_id": getattr(position, 'lower_bin_id', 0),
            "upper_bin_id": getattr(position, 'upper_bin_id', 0),
        }

        instructions = []

        # First remove all liquidity if any (with rpc for Token-2022 support)
        if hasattr(position, 'bin_ids') and position.bin_ids:
            remove_ixs = build_remove_liquidity_instructions(
                lb_pair=position.pool.address,
                pool_state=pool_state,
                position=position.id,
                owner=owner,
                bin_ids=position.bin_ids,
                bps_to_remove=10000,  # 100%
                rpc=self._rpc,
            )
            instructions.extend(remove_ixs)

        # Close position
        close_ixs = build_close_position_ixs(
            lb_pair=position.pool.address,
            position=position.id,
            position_state=position_state,
            owner=owner,
        )
        instructions.extend(close_ixs)

        return instructions

    def build_add_liquidity(
        self,
        position: Position,
        amount0: Decimal,
        amount1: Decimal,
        owner: str,
        slippage_bps: int = 50,
    ) -> List["Instruction"]:
        """Build instructions to add liquidity to existing position"""
        pool_state = self._fetch_pool_state(position.pool.address, refresh=True)
        active_id = pool_state["active_id"]

        amount_x_raw = int(amount0 * Decimal(10 ** position.pool.token0.decimals))
        amount_y_raw = int(amount1 * Decimal(10 ** position.pool.token1.decimals))

        # Get bin range from position
        min_bin_id = getattr(position, 'lower_bin_id', active_id)
        max_bin_id = getattr(position, 'upper_bin_id', active_id)

        instructions = []

        # Initialize bitmap extension if needed
        if not self._check_bitmap_extension_exists(position.pool.address):
            init_bitmap_ixs = build_initialize_bitmap_extension_instructions(
                lb_pair=position.pool.address,
                funder=owner,
            )
            instructions.extend(init_bitmap_ixs)

        add_ixs = build_add_liquidity_by_strategy_instructions(
            lb_pair=position.pool.address,
            pool_state=pool_state,
            position=position.id,
            owner=owner,
            amount_x=amount_x_raw,
            amount_y=amount_y_raw,
            active_id=active_id,
            min_bin_id=min_bin_id,
            max_bin_id=max_bin_id,
            max_active_bin_slippage=slippage_bps // 10,
            strategy_type=StrategyType.SPOT_BALANCED,
            rpc=self._rpc,
        )
        instructions.extend(add_ixs)

        return instructions

    def build_remove_liquidity(
        self,
        position: Position,
        liquidity_percent: float,
        owner: str,
        slippage_bps: int = 50,
    ) -> List["Instruction"]:
        """Build instructions to remove liquidity"""
        pool_state = self._fetch_pool_state(position.pool.address, refresh=True)

        if not hasattr(position, 'bin_ids') or not position.bin_ids:
            return []

        # Convert percent (0-100 scale) to bps (0-10000 scale)
        # e.g., 50% -> 5000 bps, 100% -> 10000 bps
        bps_to_remove = int(liquidity_percent * 100)

        return build_remove_liquidity_instructions(
            lb_pair=position.pool.address,
            pool_state=pool_state,
            position=position.id,
            owner=owner,
            bin_ids=position.bin_ids,
            bps_to_remove=bps_to_remove,
            rpc=self._rpc,
        )

    def build_claim_fees(
        self,
        position: Position,
        owner: str,
    ) -> List["Instruction"]:
        """Build instructions to claim fees"""
        pool_state = self._fetch_pool_state(position.pool.address, refresh=True)

        # Build position_state dict with bin IDs
        position_state = {
            "lower_bin_id": getattr(position, 'lower_bin_id', 0),
            "upper_bin_id": getattr(position, 'upper_bin_id', 0),
        }

        return build_claim_fee_instructions(
            lb_pair=position.pool.address,
            pool_state=pool_state,
            position=position.id,
            position_state=position_state,
            owner=owner,
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
        Calculate token amounts for a given range and USD value

        Note: This method assumes token1 is a USD stablecoin (USDC/USDT).
        For non-USD pairs, use explicit amount0/amount1 parameters instead.

        Args:
            pool: Pool to open position in
            price_range: Price range specification
            target_value_usd: Target USD value to deposit

        Returns:
            (amount0, amount1) tuple

        Raises:
            ValueError: If token1 is not a USD stablecoin
        """
        # Validate that token1 is a USD stablecoin
        if pool.token1.mint not in self.USD_STABLECOINS:
            raise ConfigurationError.invalid(
                "pool",
                f"amount_usd requires a USD-quoted pool (token1 must be USDC or USDT). "
                f"Pool {pool.address} has token1={pool.token1.symbol or pool.token1.mint}. "
                f"Use explicit amount0/amount1 parameters for non-USD pairs."
            )

        # Validate pool price to avoid division by zero
        if pool.price <= Decimal(0):
            raise ValueError(
                f"Cannot calculate amounts: pool price is {pool.price}. "
                f"Price must be positive."
            )

        # Simplified: 50/50 split
        value_per_token = target_value_usd / 2
        amount0 = value_per_token / pool.price
        amount1 = value_per_token
        return amount0, amount1

    def price_range_to_ticks(
        self,
        pool: Pool,
        price_range: PriceRange,
    ) -> tuple[int, int]:
        """Convert price range to bin IDs"""
        bin_step = pool.bin_step or 1
        active_id = pool.active_bin_id or 0
        decimals_x = pool.token0.decimals
        decimals_y = pool.token1.decimals

        if price_range.mode in (RangeMode.ONE_BIN, RangeMode.ONE_TICK):
            # ONE_TICK (Raydium) maps to ONE_BIN (Meteora) - single bin range
            return one_bin_range(active_id)

        if price_range.mode == RangeMode.BIN_RANGE:
            # Offset from active bin
            lower_bin = active_id + int(price_range.lower)
            upper_bin = active_id + int(price_range.upper)
            return lower_bin, upper_bin

        if price_range.mode in (RangeMode.PERCENT, RangeMode.BPS):
            current_price = pool.price
            lower_price, upper_price = price_range.to_absolute(current_price)

            lower_bin = price_to_bin_id(lower_price, bin_step, decimals_x, decimals_y)
            upper_bin = price_to_bin_id(upper_price, bin_step, decimals_x, decimals_y)
            return lower_bin, upper_bin

        if price_range.mode == RangeMode.ABSOLUTE:
            lower_bin = price_to_bin_id(price_range.lower, bin_step, decimals_x, decimals_y)
            upper_bin = price_to_bin_id(price_range.upper, bin_step, decimals_x, decimals_y)
            return lower_bin, upper_bin

        raise OperationNotSupported.not_implemented(f"price_range_mode:{price_range.mode}", "meteora")

    def ticks_to_prices(
        self,
        pool: Pool,
        lower_tick: int,
        upper_tick: int,
    ) -> tuple[Decimal, Decimal]:
        """Convert bin IDs to prices"""
        bin_step = pool.bin_step or 1
        decimals_x = pool.token0.decimals
        decimals_y = pool.token1.decimals

        price_lower = bin_id_to_price(lower_tick, bin_step, decimals_x, decimals_y)
        price_upper = bin_id_to_price(upper_tick, bin_step, decimals_x, decimals_y)

        return price_lower, price_upper

    def _pubkey_from_bytes(self, data: bytes) -> str:
        """Convert 32 bytes to base58"""
        import base58
        return base58.b58encode(data).decode("ascii")
