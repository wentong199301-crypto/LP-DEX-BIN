"""
PancakeSwap V3 Liquidity Adapter

Provides liquidity management functionality for BSC and Ethereum chains via PancakeSwap V3.
Note: Swap operations should use 1inch adapter instead.
"""

import logging
import math
import time
from decimal import Decimal
from typing import Optional, Dict, Any, List, Tuple, Union

try:
    from web3 import Web3
    _HAS_WEB3 = True
except ImportError:
    Web3 = None
    _HAS_WEB3 = False

from ...types.result import TxResult, TxStatus
from ...types.pool import Pool
from ...types.position import Position
from ...types.price import PriceRange, RangeMode
from ...types.common import Token, STABLECOINS
from ...types.evm_tokens import (
    resolve_token_address,
    get_token_decimals,
    get_token_symbol,
    is_native_token,
    get_native_symbol,
    get_wrapped_native_address,
)
from ...infra.evm_signer import EVMSigner, create_web3
from ...errors import SignerError, ConfigurationError, ErrorCode
from ...config import config as global_config

from .api import (
    PANCAKESWAP_POSITION_MANAGER_ADDRESSES,
    PANCAKESWAP_FACTORY_ADDRESSES,
    TICK_SPACING_BY_FEE,
)

logger = logging.getLogger(__name__)


# Standard ERC20 ABI for approve and allowance
ERC20_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [
            {"name": "_owner", "type": "address"},
            {"name": "_spender", "type": "address"}
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    }
]

# PancakeSwap V3 NonfungiblePositionManager ABI (subset)
POSITION_MANAGER_ABI = [
    {
        "inputs": [{"name": "tokenId", "type": "uint256"}],
        "name": "positions",
        "outputs": [
            {"name": "nonce", "type": "uint96"},
            {"name": "operator", "type": "address"},
            {"name": "token0", "type": "address"},
            {"name": "token1", "type": "address"},
            {"name": "fee", "type": "uint24"},
            {"name": "tickLower", "type": "int24"},
            {"name": "tickUpper", "type": "int24"},
            {"name": "liquidity", "type": "uint128"},
            {"name": "feeGrowthInside0LastX128", "type": "uint256"},
            {"name": "feeGrowthInside1LastX128", "type": "uint256"},
            {"name": "tokensOwed0", "type": "uint128"},
            {"name": "tokensOwed1", "type": "uint128"},
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"name": "owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "index", "type": "uint256"}
        ],
        "name": "tokenOfOwnerByIndex",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {
                "components": [
                    {"name": "token0", "type": "address"},
                    {"name": "token1", "type": "address"},
                    {"name": "fee", "type": "uint24"},
                    {"name": "tickLower", "type": "int24"},
                    {"name": "tickUpper", "type": "int24"},
                    {"name": "amount0Desired", "type": "uint256"},
                    {"name": "amount1Desired", "type": "uint256"},
                    {"name": "amount0Min", "type": "uint256"},
                    {"name": "amount1Min", "type": "uint256"},
                    {"name": "recipient", "type": "address"},
                    {"name": "deadline", "type": "uint256"},
                ],
                "name": "params",
                "type": "tuple"
            }
        ],
        "name": "mint",
        "outputs": [
            {"name": "tokenId", "type": "uint256"},
            {"name": "liquidity", "type": "uint128"},
            {"name": "amount0", "type": "uint256"},
            {"name": "amount1", "type": "uint256"},
        ],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [
            {
                "components": [
                    {"name": "tokenId", "type": "uint256"},
                    {"name": "amount0Desired", "type": "uint256"},
                    {"name": "amount1Desired", "type": "uint256"},
                    {"name": "amount0Min", "type": "uint256"},
                    {"name": "amount1Min", "type": "uint256"},
                    {"name": "deadline", "type": "uint256"},
                ],
                "name": "params",
                "type": "tuple"
            }
        ],
        "name": "increaseLiquidity",
        "outputs": [
            {"name": "liquidity", "type": "uint128"},
            {"name": "amount0", "type": "uint256"},
            {"name": "amount1", "type": "uint256"},
        ],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [
            {
                "components": [
                    {"name": "tokenId", "type": "uint256"},
                    {"name": "liquidity", "type": "uint128"},
                    {"name": "amount0Min", "type": "uint256"},
                    {"name": "amount1Min", "type": "uint256"},
                    {"name": "deadline", "type": "uint256"},
                ],
                "name": "params",
                "type": "tuple"
            }
        ],
        "name": "decreaseLiquidity",
        "outputs": [
            {"name": "amount0", "type": "uint256"},
            {"name": "amount1", "type": "uint256"},
        ],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [
            {
                "components": [
                    {"name": "tokenId", "type": "uint256"},
                    {"name": "recipient", "type": "address"},
                    {"name": "amount0Max", "type": "uint128"},
                    {"name": "amount1Max", "type": "uint128"},
                ],
                "name": "params",
                "type": "tuple"
            }
        ],
        "name": "collect",
        "outputs": [
            {"name": "amount0", "type": "uint256"},
            {"name": "amount1", "type": "uint256"},
        ],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [{"name": "tokenId", "type": "uint256"}],
        "name": "burn",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [{"name": "data", "type": "bytes[]"}],
        "name": "multicall",
        "outputs": [{"name": "results", "type": "bytes[]"}],
        "stateMutability": "payable",
        "type": "function"
    },
]

# PancakeSwap V3 Factory ABI (subset)
FACTORY_ABI = [
    {
        "inputs": [
            {"name": "tokenA", "type": "address"},
            {"name": "tokenB", "type": "address"},
            {"name": "fee", "type": "uint24"},
        ],
        "name": "getPool",
        "outputs": [{"name": "pool", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
]

# PancakeSwap V3 Pool ABI (subset)
POOL_ABI = [
    {
        "inputs": [],
        "name": "slot0",
        "outputs": [
            {"name": "sqrtPriceX96", "type": "uint160"},
            {"name": "tick", "type": "int24"},
            {"name": "observationIndex", "type": "uint16"},
            {"name": "observationCardinality", "type": "uint16"},
            {"name": "observationCardinalityNext", "type": "uint16"},
            {"name": "feeProtocol", "type": "uint32"},
            {"name": "unlocked", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "token0",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "token1",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "fee",
        "outputs": [{"name": "", "type": "uint24"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "tickSpacing",
        "outputs": [{"name": "", "type": "int24"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "liquidity",
        "outputs": [{"name": "", "type": "uint128"}],
        "stateMutability": "view",
        "type": "function"
    },
]

# Constants for V3 math
Q96 = 2**96
MIN_TICK = -887272
MAX_TICK = 887272


class PancakeSwapAdapter:
    """
    PancakeSwap V3 Liquidity Adapter for BSC

    Provides liquidity management functionality via PancakeSwap V3 on BSC.
    Uses web3.py for transaction signing and sending.

    Usage:
        signer = EVMSigner.from_env()
        adapter = PancakeSwapAdapter(chain_id=56, signer=signer)

        # Get pool
        pool = adapter.get_pool("WBNB", "USDT", fee=2500)

        # Open position
        result = adapter.open_position(pool, PriceRange.percent(0.05), amount0=Decimal("1.0"))

        # List positions
        positions = adapter.get_positions()

        # Close position
        result = adapter.close_position(position)
    """

    name = "pancakeswap"

    def __init__(
        self,
        chain_id: int = 56,
        signer: Optional[EVMSigner] = None,
        rpc_url: Optional[str] = None,
    ):
        """
        Initialize PancakeSwap V3 liquidity adapter

        Args:
            chain_id: Chain ID (56 for BSC only)
            signer: Optional EVM signer for executing transactions
            rpc_url: Optional RPC URL (uses config default if not provided)
        """
        if not _HAS_WEB3:
            raise RuntimeError(
                "web3 is required for PancakeSwapAdapter. "
                "Install with: pip install web3"
            )

        self._chain_id = chain_id
        self._signer = signer

        # Validate chain ID (BSC only)
        if chain_id != 56:
            raise ConfigurationError.invalid(
                "chain_id",
                f"Unsupported chain ID: {chain_id}. PancakeSwap only supports BSC (56)"
            )

        # Determine RPC URL
        if rpc_url:
            self._rpc_url = rpc_url
        else:
            self._rpc_url = global_config.pancakeswap.bsc_rpc_url

        # Initialize web3
        self._web3 = create_web3(self._rpc_url, chain_id)

        logger.info(f"Initialized PancakeSwapAdapter for BSC ({chain_id})")

    @property
    def chain_id(self) -> int:
        """Chain ID"""
        return self._chain_id

    @property
    def chain_name(self) -> str:
        """Human-readable chain name"""
        return "BSC"

    @property
    def address(self) -> Optional[str]:
        """Signer address if available"""
        return self._signer.address if self._signer else None

    @property
    def pubkey(self) -> Optional[str]:
        """Signer public key (alias for address)"""
        return self.address

    @property
    def web3(self) -> "Web3":
        """Web3 instance"""
        return self._web3

    @property
    def position_manager_address(self) -> str:
        """PancakeSwap V3 NonfungiblePositionManager address"""
        return PANCAKESWAP_POSITION_MANAGER_ADDRESSES.get(self._chain_id, PANCAKESWAP_POSITION_MANAGER_ADDRESSES[56])

    @property
    def factory_address(self) -> str:
        """PancakeSwap V3 Factory address"""
        return PANCAKESWAP_FACTORY_ADDRESSES.get(self._chain_id, PANCAKESWAP_FACTORY_ADDRESSES[56])

    def wrap_native(self, amount: Decimal) -> str:
        """
        Wrap native BNB into WBNB.

        Args:
            amount: Amount of BNB to wrap (UI units, e.g. Decimal("0.01"))

        Returns:
            Transaction hash
        """
        if not self._signer:
            raise SignerError.missing("Signer required for wrap")

        wbnb_address = get_wrapped_native_address(self._chain_id)
        raw_amount = int(amount * Decimal(10**18))

        wbnb_abi = [{"constant": False, "inputs": [], "name": "deposit", "outputs": [], "stateMutability": "payable", "type": "function"}]
        contract = self._web3.eth.contract(
            address=self._web3.to_checksum_address(wbnb_address), abi=wbnb_abi
        )

        tx = contract.functions.deposit().build_transaction({
            "from": self.address,
            "value": raw_amount,
            "gas": 50000,
            "gasPrice": self._web3.eth.gas_price,
            "nonce": self._web3.eth.get_transaction_count(self.address),
            "chainId": self._chain_id,
        })

        raw_tx, tx_hash_hex = self._signer.sign_transaction(tx)
        self._web3.eth.send_raw_transaction(raw_tx)
        receipt = self._web3.eth.wait_for_transaction_receipt(bytes.fromhex(tx_hash_hex), timeout=60)

        status = "OK" if receipt["status"] == 1 else "FAILED"
        logger.info(f"Wrap {amount} BNB -> WBNB: {status} (tx: {tx_hash_hex})")
        return tx_hash_hex

    def unwrap_native(self, amount: Decimal) -> str:
        """
        Unwrap WBNB back to native BNB.

        Args:
            amount: Amount of WBNB to unwrap (UI units, e.g. Decimal("0.01"))

        Returns:
            Transaction hash
        """
        if not self._signer:
            raise SignerError.missing("Signer required for unwrap")

        wbnb_address = get_wrapped_native_address(self._chain_id)
        raw_amount = int(amount * Decimal(10**18))

        wbnb_abi = [{"constant": False, "inputs": [{"name": "wad", "type": "uint256"}], "name": "withdraw", "outputs": [], "type": "function"}]
        contract = self._web3.eth.contract(
            address=self._web3.to_checksum_address(wbnb_address), abi=wbnb_abi
        )

        tx = contract.functions.withdraw(raw_amount).build_transaction({
            "from": self.address,
            "value": 0,
            "gas": 50000,
            "gasPrice": self._web3.eth.gas_price,
            "nonce": self._web3.eth.get_transaction_count(self.address),
            "chainId": self._chain_id,
        })

        raw_tx, tx_hash_hex = self._signer.sign_transaction(tx)
        self._web3.eth.send_raw_transaction(raw_tx)
        receipt = self._web3.eth.wait_for_transaction_receipt(bytes.fromhex(tx_hash_hex), timeout=60)

        status = "OK" if receipt["status"] == 1 else "FAILED"
        logger.info(f"Unwrap {amount} WBNB -> BNB: {status} (tx: {tx_hash_hex})")
        return tx_hash_hex

    def _get_position_manager_contract(self):
        """Get Position Manager contract instance"""
        return self._web3.eth.contract(
            address=Web3.to_checksum_address(self.position_manager_address),
            abi=POSITION_MANAGER_ABI,
        )

    def _get_factory_contract(self):
        """Get Factory contract instance"""
        return self._web3.eth.contract(
            address=Web3.to_checksum_address(self.factory_address),
            abi=FACTORY_ABI,
        )

    def _get_pool_contract(self, pool_address: str):
        """Get Pool contract instance"""
        return self._web3.eth.contract(
            address=Web3.to_checksum_address(pool_address),
            abi=POOL_ABI,
        )

    def _get_token_contract(self, token_address: str):
        """Get ERC20 token contract instance"""
        return self._web3.eth.contract(
            address=Web3.to_checksum_address(token_address),
            abi=ERC20_ABI,
        )

    def _result_to_tx_result(self, result: Dict[str, Any]) -> TxResult:
        """Convert signer result to TxResult"""
        if result["status"] == "success":
            return TxResult.success(signature=result["tx_hash"])
        elif result["status"] == "pending":
            return TxResult(
                status=TxStatus.PENDING,
                signature=result.get("tx_hash"),
            )
        else:
            return TxResult.failed(
                error=result.get("error", "Transaction failed"),
                signature=result.get("tx_hash"),
            )

    def _get_decimals(self, token: str) -> int:
        """Get token decimals"""
        return get_token_decimals(token, self._chain_id)

    # =========================================================================
    # V3 Math Helper Functions
    # =========================================================================

    @staticmethod
    def tick_to_price(tick: int, decimals0: int = 18, decimals1: int = 18) -> Decimal:
        """Convert tick to price"""
        price = Decimal(str(1.0001 ** tick))
        # Adjust for decimals
        decimal_adjustment = Decimal(10 ** (decimals0 - decimals1))
        return price * decimal_adjustment

    @staticmethod
    def price_to_tick(price: Decimal, decimals0: int = 18, decimals1: int = 18) -> int:
        """Convert price to tick"""
        # Adjust for decimals
        decimal_adjustment = Decimal(10 ** (decimals1 - decimals0))
        adjusted_price = float(price * decimal_adjustment)
        if adjusted_price <= 0:
            return MIN_TICK
        tick = int(math.log(adjusted_price) / math.log(1.0001))
        return max(MIN_TICK, min(MAX_TICK, tick))

    @staticmethod
    def sqrt_price_x96_to_price(sqrt_price_x96: int, decimals0: int = 18, decimals1: int = 18) -> Decimal:
        """Convert sqrtPriceX96 to price"""
        price = (Decimal(sqrt_price_x96) / Decimal(Q96)) ** 2
        # Adjust for decimals
        decimal_adjustment = Decimal(10 ** (decimals0 - decimals1))
        return price * decimal_adjustment

    @staticmethod
    def price_to_sqrt_price_x96(price: Decimal, decimals0: int = 18, decimals1: int = 18) -> int:
        """Convert price to sqrtPriceX96"""
        decimal_adjustment = Decimal(10 ** (decimals1 - decimals0))
        adjusted_price = price * decimal_adjustment
        sqrt_price = adjusted_price.sqrt()
        return int(sqrt_price * Decimal(Q96))

    def _align_tick_to_spacing(self, tick: int, tick_spacing: int, round_up: bool = False) -> int:
        """Align tick to tick spacing"""
        if round_up:
            return ((tick + tick_spacing - 1) // tick_spacing) * tick_spacing
        return (tick // tick_spacing) * tick_spacing

    def _calculate_tvl(
        self,
        pool_address: str,
        token0_contract,
        token1_contract,
        decimals0: int,
        decimals1: int,
        price: Decimal,
        token0_symbol: str = "",
        token1_symbol: str = "",
    ) -> Decimal:
        """
        Calculate TVL from pool token balances.

        Args:
            pool_address: Pool contract address
            token0_contract: Token0 contract instance
            token1_contract: Token1 contract instance
            decimals0: Token0 decimals
            decimals1: Token1 decimals
            price: Token0 price in Token1 terms
            token0_symbol: Token0 symbol (for stablecoin detection)
            token1_symbol: Token1 symbol (for stablecoin detection)

        Returns:
            TVL in USD
        """
        try:
            pool_addr = Web3.to_checksum_address(pool_address)

            balance0_raw = token0_contract.functions.balanceOf(pool_addr).call()
            balance1_raw = token1_contract.functions.balanceOf(pool_addr).call()

            balance0 = Decimal(balance0_raw) / Decimal(10 ** decimals0)
            balance1 = Decimal(balance1_raw) / Decimal(10 ** decimals1)

            # Detect which token is the stablecoin
            token0_is_stable = token0_symbol.upper() in STABLECOINS
            token1_is_stable = token1_symbol.upper() in STABLECOINS

            if token0_is_stable and not token1_is_stable:
                # Token0 is stablecoin: TVL = balance0 + (balance1 * price_of_token1_in_usd)
                # price = token0/token1, so price_of_token1_in_usd = 1/price
                if price > 0:
                    tvl = balance0 + (balance1 / price)
                else:
                    tvl = balance0
            else:
                # Token1 is stablecoin (or both/neither): TVL = (balance0 * price) + balance1
                tvl = (balance0 * price) + balance1

            return tvl
        except Exception:
            return Decimal(0)

    # =========================================================================
    # Pool Methods
    # =========================================================================

    def get_pool(
        self,
        token0: str,
        token1: str,
        fee: int = 2500,
    ) -> Optional[Pool]:
        """
        Get V3 pool information

        Args:
            token0: First token (symbol or address)
            token1: Second token (symbol or address)
            fee: Fee tier (100, 500, 2500, 10000)

        Returns:
            Pool object or None if not found
        """
        # Resolve token addresses
        addr0 = resolve_token_address(token0, self._chain_id)
        addr1 = resolve_token_address(token1, self._chain_id)

        # Handle native tokens - use wrapped version
        if is_native_token(addr0):
            addr0 = get_wrapped_native_address(self._chain_id)
        if is_native_token(addr1):
            addr1 = get_wrapped_native_address(self._chain_id)

        # Sort addresses (Uniswap V3 convention)
        if addr0.lower() > addr1.lower():
            addr0, addr1 = addr1, addr0

        try:
            # Get pool address from factory
            factory = self._get_factory_contract()
            pool_address = factory.functions.getPool(
                Web3.to_checksum_address(addr0),
                Web3.to_checksum_address(addr1),
                fee,
            ).call()

            if pool_address == "0x0000000000000000000000000000000000000000":
                return None

            # Get pool data
            pool_contract = self._get_pool_contract(pool_address)
            slot0 = pool_contract.functions.slot0().call()
            sqrt_price_x96 = slot0[0]
            current_tick = slot0[1]
            tick_spacing = pool_contract.functions.tickSpacing().call()
            liquidity = pool_contract.functions.liquidity().call()

            # Get token info
            token0_contract = self._get_token_contract(addr0)
            token1_contract = self._get_token_contract(addr1)

            decimals0 = token0_contract.functions.decimals().call()
            decimals1 = token1_contract.functions.decimals().call()

            try:
                symbol0 = token0_contract.functions.symbol().call()
            except Exception:
                symbol0 = get_token_symbol(addr0, self._chain_id) or addr0[:8]

            try:
                symbol1 = token1_contract.functions.symbol().call()
            except Exception:
                symbol1 = get_token_symbol(addr1, self._chain_id) or addr1[:8]

            # Calculate price
            price = self.sqrt_price_x96_to_price(sqrt_price_x96, decimals0, decimals1)

            # Create token objects
            token0_obj = Token(mint=addr0, symbol=symbol0, decimals=decimals0)
            token1_obj = Token(mint=addr1, symbol=symbol1, decimals=decimals1)

            # Calculate TVL from pool token balances
            tvl_usd = self._calculate_tvl(
                pool_address=pool_address,
                token0_contract=token0_contract,
                token1_contract=token1_contract,
                decimals0=decimals0,
                decimals1=decimals1,
                price=price,
                token0_symbol=symbol0,
                token1_symbol=symbol1,
            )

            return Pool(
                address=pool_address,
                dex="pancakeswap",
                symbol=f"{symbol0}/{symbol1}",
                token0=token0_obj,
                token1=token1_obj,
                price=price,
                tvl_usd=tvl_usd,
                fee_rate=Decimal(fee) / Decimal(1_000_000),
                tick_spacing=tick_spacing,
                current_tick=current_tick,
                sqrt_price_x64=sqrt_price_x96,  # Store as x96 in the x64 field
                metadata={
                    "liquidity": liquidity,
                    "fee": fee,
                    "chain_id": self._chain_id,
                },
            )

        except Exception as e:
            logger.error(f"Failed to get pool: {e}")
            return None

    def get_pool_by_address(self, pool_address: str) -> Optional[Pool]:
        """
        Get V3 pool information by address

        Args:
            pool_address: Pool contract address

        Returns:
            Pool object or None if not found
        """
        try:
            pool_contract = self._get_pool_contract(pool_address)

            # Get pool data
            slot0 = pool_contract.functions.slot0().call()
            sqrt_price_x96 = slot0[0]
            current_tick = slot0[1]

            token0_addr = pool_contract.functions.token0().call()
            token1_addr = pool_contract.functions.token1().call()
            fee = pool_contract.functions.fee().call()
            tick_spacing = pool_contract.functions.tickSpacing().call()
            liquidity = pool_contract.functions.liquidity().call()

            # Get token info
            token0_contract = self._get_token_contract(token0_addr)
            token1_contract = self._get_token_contract(token1_addr)

            decimals0 = token0_contract.functions.decimals().call()
            decimals1 = token1_contract.functions.decimals().call()

            try:
                symbol0 = token0_contract.functions.symbol().call()
            except Exception:
                symbol0 = get_token_symbol(token0_addr, self._chain_id) or token0_addr[:8]

            try:
                symbol1 = token1_contract.functions.symbol().call()
            except Exception:
                symbol1 = get_token_symbol(token1_addr, self._chain_id) or token1_addr[:8]

            # Calculate price
            price = self.sqrt_price_x96_to_price(sqrt_price_x96, decimals0, decimals1)

            # Create token objects
            token0_obj = Token(mint=token0_addr, symbol=symbol0, decimals=decimals0)
            token1_obj = Token(mint=token1_addr, symbol=symbol1, decimals=decimals1)

            # Calculate TVL from pool token balances
            tvl_usd = self._calculate_tvl(
                pool_address=pool_address,
                token0_contract=token0_contract,
                token1_contract=token1_contract,
                decimals0=decimals0,
                decimals1=decimals1,
                price=price,
                token0_symbol=symbol0,
                token1_symbol=symbol1,
            )

            return Pool(
                address=pool_address,
                dex="pancakeswap",
                symbol=f"{symbol0}/{symbol1}",
                token0=token0_obj,
                token1=token1_obj,
                price=price,
                tvl_usd=tvl_usd,
                fee_rate=Decimal(fee) / Decimal(1_000_000),
                tick_spacing=tick_spacing,
                current_tick=current_tick,
                sqrt_price_x64=sqrt_price_x96,
                metadata={
                    "liquidity": liquidity,
                    "fee": fee,
                    "chain_id": self._chain_id,
                },
            )

        except Exception as e:
            logger.error(f"Failed to get pool by address: {e}")
            return None

    # =========================================================================
    # Position Methods
    # =========================================================================

    def get_positions(self, owner: Optional[str] = None) -> List[Position]:
        """
        Get all positions owned by address

        Args:
            owner: Owner address (defaults to signer address)

        Returns:
            List of Position objects
        """
        if owner is None:
            if not self._signer:
                raise SignerError.not_configured()
            owner = self._signer.address

        positions = []
        try:
            pm = self._get_position_manager_contract()
            balance = pm.functions.balanceOf(Web3.to_checksum_address(owner)).call()

            for i in range(balance):
                token_id = pm.functions.tokenOfOwnerByIndex(
                    Web3.to_checksum_address(owner),
                    i,
                ).call()

                position = self.get_position(token_id)
                if position:
                    positions.append(position)

        except Exception as e:
            logger.error(f"Failed to get positions: {e}")

        return positions

    def get_position(self, token_id: int) -> Optional[Position]:
        """
        Get position by token ID

        Args:
            token_id: NFT token ID

        Returns:
            Position object or None if not found
        """
        try:
            pm = self._get_position_manager_contract()
            pos_data = pm.functions.positions(token_id).call()

            # Parse position data
            # (nonce, operator, token0, token1, fee, tickLower, tickUpper,
            #  liquidity, feeGrowthInside0LastX128, feeGrowthInside1LastX128,
            #  tokensOwed0, tokensOwed1)
            token0_addr = pos_data[2]
            token1_addr = pos_data[3]
            fee = pos_data[4]
            tick_lower = pos_data[5]
            tick_upper = pos_data[6]
            liquidity = pos_data[7]
            tokens_owed0 = pos_data[10]
            tokens_owed1 = pos_data[11]

            # Get pool
            pool = self.get_pool(token0_addr, token1_addr, fee)
            if not pool:
                logger.warning(f"Pool not found for position {token_id}")
                return None

            # Calculate prices from ticks
            decimals0 = pool.token0.decimals
            decimals1 = pool.token1.decimals
            price_lower = self.tick_to_price(tick_lower, decimals0, decimals1)
            price_upper = self.tick_to_price(tick_upper, decimals0, decimals1)

            # Check if in range
            is_in_range = tick_lower <= pool.current_tick <= tick_upper

            # Calculate token amounts (simplified - full calculation would need more pool state)
            amount0 = Decimal(0)
            amount1 = Decimal(0)
            if liquidity > 0:
                # This is a simplified calculation
                sqrt_price = Decimal(pool.sqrt_price_x64) / Decimal(Q96)
                sqrt_price_lower = Decimal(str(1.0001 ** (tick_lower / 2)))
                sqrt_price_upper = Decimal(str(1.0001 ** (tick_upper / 2)))

                if pool.current_tick < tick_lower:
                    # All token0
                    amount0 = Decimal(liquidity) * (1 / sqrt_price_lower - 1 / sqrt_price_upper)
                elif pool.current_tick >= tick_upper:
                    # All token1
                    amount1 = Decimal(liquidity) * (sqrt_price_upper - sqrt_price_lower)
                else:
                    # Both tokens
                    amount0 = Decimal(liquidity) * (1 / sqrt_price - 1 / sqrt_price_upper)
                    amount1 = Decimal(liquidity) * (sqrt_price - sqrt_price_lower)

                # Convert to UI amounts
                amount0 = amount0 / Decimal(10 ** decimals0)
                amount1 = amount1 / Decimal(10 ** decimals1)

            # Unclaimed fees
            unclaimed_fees = {
                pool.token0.mint: Decimal(tokens_owed0) / Decimal(10 ** decimals0),
                pool.token1.mint: Decimal(tokens_owed1) / Decimal(10 ** decimals1),
            }

            return Position(
                id=str(token_id),
                pool=pool,
                owner=self._signer.address if self._signer else "",
                price_lower=price_lower,
                price_upper=price_upper,
                amount0=amount0,
                amount1=amount1,
                liquidity=liquidity,
                unclaimed_fees=unclaimed_fees,
                is_in_range=is_in_range,
                nft_mint=str(token_id),
                tick_lower=tick_lower,
                tick_upper=tick_upper,
                metadata={
                    "token_id": token_id,
                    "fee": fee,
                    "chain_id": self._chain_id,
                },
            )

        except Exception as e:
            logger.error(f"Failed to get position {token_id}: {e}")
            return None

    def open_position(
        self,
        pool: Pool,
        price_range: PriceRange,
        amount0: Optional[Decimal] = None,
        amount1: Optional[Decimal] = None,
        slippage_bps: Optional[int] = None,
    ) -> TxResult:
        """
        Open a new liquidity position

        Args:
            pool: Pool to add liquidity to
            price_range: Price range for the position
            amount0: Amount of token0 (optional)
            amount1: Amount of token1 (optional)
            slippage_bps: Slippage tolerance in basis points (uses config default if not specified)

        Returns:
            TxResult with position token ID in metadata
        """
        if not self._signer:
            raise SignerError.not_configured()

        # Use config default if not specified
        if slippage_bps is None:
            slippage_bps = global_config.trading.default_lp_slippage_bps

        if amount0 is None and amount1 is None:
            raise ConfigurationError.missing("amount0 or amount1")

        try:
            # Calculate ticks from price range
            tick_lower, tick_upper = self._price_range_to_ticks(pool, price_range)

            # Convert amounts to raw
            decimals0 = pool.token0.decimals
            decimals1 = pool.token1.decimals
            raw_amount0 = int((amount0 or Decimal(0)) * Decimal(10 ** decimals0))
            raw_amount1 = int((amount1 or Decimal(0)) * Decimal(10 ** decimals1))

            # For minting, set min amounts to 0.
            # The tick range already defines the price bounds, and the pool
            # calculates the optimal token ratio — the actual deposited amounts
            # may be less than desired. Applying slippage to desired amounts
            # causes "Price slippage check" reverts.
            min_amount0 = 0
            min_amount1 = 0

            # Handle token approvals
            token0_addr = pool.token0.mint
            token1_addr = pool.token1.mint

            # Always use token transfers (not native BNB)
            # This avoids complexity with multicall/wrapETH
            # User should have WBNB balance if interacting with WBNB pools
            native_value = 0

            # Approve both tokens (including WBNB)
            if raw_amount0 > 0:
                approval = self._ensure_approval_for_position_manager(token0_addr, raw_amount0)
                if approval and not approval.is_success:
                    return approval
            if raw_amount1 > 0:
                approval = self._ensure_approval_for_position_manager(token1_addr, raw_amount1)
                if approval and not approval.is_success:
                    return approval

            # Build mint parameters
            fee = pool.metadata.get("fee", 2500)

            def build_tx():
                deadline = int(time.time()) + global_config.evm.tx_deadline_seconds  # 20 minutes
                mint_params = (
                    Web3.to_checksum_address(token0_addr),
                    Web3.to_checksum_address(token1_addr),
                    fee,
                    tick_lower,
                    tick_upper,
                    raw_amount0,
                    raw_amount1,
                    min_amount0,
                    min_amount1,
                    Web3.to_checksum_address(self._signer.address),
                    deadline,
                )

                pm = self._get_position_manager_contract()
                return pm.functions.mint(mint_params).build_transaction({
                    "from": self._signer.address,
                    "value": native_value,
                    "gas": global_config.evm.lp_gas_limit,
                    "nonce": self._web3.eth.get_transaction_count(self._signer.address),
                    "chainId": self._chain_id,
                })

            return self._execute_with_retry("open_position", build_tx)

        except Exception as e:
            logger.error(f"Failed to open position: {e}")
            return TxResult.failed(str(e))

    def add_liquidity(
        self,
        position: Position,
        amount0: Decimal,
        amount1: Decimal,
        slippage_bps: Optional[int] = None,
    ) -> TxResult:
        """
        Add liquidity to existing position

        Args:
            position: Position to add liquidity to
            amount0: Amount of token0 to add
            amount1: Amount of token1 to add
            slippage_bps: Slippage tolerance in basis points (uses config default if not specified)

        Returns:
            TxResult
        """
        if not self._signer:
            raise SignerError.not_configured()

        # Use config default if not specified
        if slippage_bps is None:
            slippage_bps = global_config.trading.default_lp_slippage_bps

        try:
            token_id = int(position.id)
            pool = position.pool

            # Convert amounts to raw
            decimals0 = pool.token0.decimals
            decimals1 = pool.token1.decimals
            raw_amount0 = int(amount0 * Decimal(10 ** decimals0))
            raw_amount1 = int(amount1 * Decimal(10 ** decimals1))

            # Calculate minimum amounts with slippage
            slippage_factor = Decimal(10000 - slippage_bps) / Decimal(10000)
            min_amount0 = int(Decimal(raw_amount0) * slippage_factor)
            min_amount1 = int(Decimal(raw_amount1) * slippage_factor)

            # Handle token approvals
            token0_addr = pool.token0.mint
            token1_addr = pool.token1.mint

            # Check if using native token
            native_value = 0
            wrapped_native = get_wrapped_native_address(self._chain_id)
            token0_is_native = token0_addr.lower() == wrapped_native.lower()
            token1_is_native = token1_addr.lower() == wrapped_native.lower()

            # Handle native BNB value (can send BNB for wrapped native tokens)
            if token0_is_native and raw_amount0 > 0:
                native_value += raw_amount0
            if token1_is_native and raw_amount1 > 0:
                native_value += raw_amount1

            # Approve non-native tokens (must approve even in mixed pairs)
            if not token0_is_native and raw_amount0 > 0:
                approval = self._ensure_approval_for_position_manager(token0_addr, raw_amount0)
                if approval and not approval.is_success:
                    return approval
            if not token1_is_native and raw_amount1 > 0:
                approval = self._ensure_approval_for_position_manager(token1_addr, raw_amount1)
                if approval and not approval.is_success:
                    return approval

            # Build increase liquidity parameters
            def build_tx():
                deadline = int(time.time()) + global_config.evm.tx_deadline_seconds
                increase_params = (
                    token_id,
                    raw_amount0,
                    raw_amount1,
                    min_amount0,
                    min_amount1,
                    deadline,
                )

                pm = self._get_position_manager_contract()
                return pm.functions.increaseLiquidity(increase_params).build_transaction({
                    "from": self._signer.address,
                    "value": native_value,
                    "gas": 400000,
                    "nonce": self._web3.eth.get_transaction_count(self._signer.address),
                    "chainId": self._chain_id,
                })

            return self._execute_with_retry("add_liquidity", build_tx)

        except Exception as e:
            logger.error(f"Failed to add liquidity: {e}")
            return TxResult.failed(str(e))

    def remove_liquidity(
        self,
        position: Position,
        percent: float = 100.0,
        slippage_bps: Optional[int] = None,
    ) -> TxResult:
        """
        Remove liquidity from position

        Args:
            position: Position to remove liquidity from
            percent: Percentage of liquidity to remove (0-100)
            slippage_bps: Slippage tolerance in basis points (uses config default if not specified)

        Returns:
            TxResult
        """
        if not self._signer:
            raise SignerError.not_configured()

        # Use config default if not specified
        if slippage_bps is None:
            slippage_bps = global_config.trading.default_lp_slippage_bps

        try:
            token_id = int(position.id)

            # Calculate liquidity to remove (use integer math to avoid float precision loss)
            liquidity_to_remove = position.liquidity * int(percent) // 100
            if liquidity_to_remove == 0:
                return TxResult.skipped("No liquidity to remove")

            # Calculate minimum amounts with slippage protection
            slippage_factor = Decimal(10000 - slippage_bps) / Decimal(10000)
            expected_amount0 = position.amount0 * Decimal(percent) / Decimal(100)
            expected_amount1 = position.amount1 * Decimal(percent) / Decimal(100)
            amount0_min = int(expected_amount0 * slippage_factor * Decimal(10 ** position.pool.token0.decimals))
            amount1_min = int(expected_amount1 * slippage_factor * Decimal(10 ** position.pool.token1.decimals))

            # Build decrease liquidity parameters
            def build_tx():
                deadline = int(time.time()) + global_config.evm.tx_deadline_seconds
                decrease_params = (
                    token_id,
                    liquidity_to_remove,
                    amount0_min,
                    amount1_min,
                    deadline,
                )

                pm = self._get_position_manager_contract()
                return pm.functions.decreaseLiquidity(decrease_params).build_transaction({
                    "from": self._signer.address,
                    "value": 0,
                    "gas": 300000,
                    "nonce": self._web3.eth.get_transaction_count(self._signer.address),
                    "chainId": self._chain_id,
                })

            return self._execute_with_retry("remove_liquidity", build_tx)

        except Exception as e:
            logger.error(f"Failed to remove liquidity: {e}")
            return TxResult.failed(str(e))

    def claim_fees(self, position: Position) -> TxResult:
        """
        Collect accumulated fees from position

        Args:
            position: Position to collect fees from

        Returns:
            TxResult
        """
        if not self._signer:
            raise SignerError.not_configured()

        try:
            token_id = int(position.id)

            # Build collect parameters (collect max uint128)
            max_uint128 = 2**128 - 1

            def build_tx():
                collect_params = (
                    token_id,
                    Web3.to_checksum_address(self._signer.address),
                    max_uint128,
                    max_uint128,
                )

                pm = self._get_position_manager_contract()
                return pm.functions.collect(collect_params).build_transaction({
                    "from": self._signer.address,
                    "value": 0,
                    "gas": 200000,
                    "nonce": self._web3.eth.get_transaction_count(self._signer.address),
                    "chainId": self._chain_id,
                })

            return self._execute_with_retry("claim_fees", build_tx)

        except Exception as e:
            logger.error(f"Failed to claim fees: {e}")
            return TxResult.failed(str(e))

    def close_position(
        self,
        position: Optional[Position] = None,
    ) -> Union[TxResult, List[TxResult]]:
        """
        Close position(s) (remove all liquidity, collect fees, burn NFT)

        Args:
            position: Position to close. If None, closes all positions.

        Returns:
            TxResult for single position, List[TxResult] for all positions

        Examples:
            # Close a specific position
            result = adapter.close_position(position)

            # Close all positions
            results = adapter.close_position()
        """
        if not self._signer:
            raise SignerError.not_configured()

        # If no position provided, close all positions
        if position is None:
            positions = self.get_positions()
            if not positions:
                logger.info("No positions to close")
                return []

            results = []
            for pos in positions:
                logger.info(f"Closing position {pos.id}...")
                try:
                    result = self._close_single_position(pos)
                    results.append(result)
                    if result.is_success:
                        logger.info(f"  Closed: {result.signature}")
                    else:
                        logger.warning(f"  Failed: {result.error}")
                except Exception as e:
                    logger.error(f"  Error closing position {pos.id}: {e}")
                    results.append(TxResult.failed(str(e)))
            return results

        return self._close_single_position(position)

    def _close_single_position(self, position: Position) -> TxResult:
        """Close a single position"""
        try:
            token_id = int(position.id)

            # Step 1: Remove all liquidity if any
            if position.liquidity > 0:
                remove_result = self.remove_liquidity(position, 100.0)
                if not remove_result.is_success:
                    return remove_result

            # Step 2: Collect any remaining fees/tokens
            collect_result = self.claim_fees(position)
            if not collect_result.is_success:
                # Continue even if collect fails (might have nothing to collect)
                logger.warning(f"Collect failed during close: {collect_result.error}")

            # Step 3: Burn the NFT with retry
            def build_burn_tx():
                pm = self._get_position_manager_contract()
                return pm.functions.burn(token_id).build_transaction({
                    "from": self._signer.address,
                    "value": 0,
                    "gas": 150000,  # Burn needs ~90-115k gas
                    "nonce": self._web3.eth.get_transaction_count(self._signer.address),
                    "chainId": self._chain_id,
                })

            burn_result = self._execute_with_retry("close_position_burn", build_burn_tx)
            if not burn_result.is_success:
                return burn_result

            # Step 4: Unwrap WBNB to native BNB if either token is wrapped native
            wrapped_native = get_wrapped_native_address(self._chain_id)
            token0_is_wrapped = position.pool.token0.mint.lower() == wrapped_native.lower()
            token1_is_wrapped = position.pool.token1.mint.lower() == wrapped_native.lower()

            if token0_is_wrapped or token1_is_wrapped:
                try:
                    wbnb_contract = self._get_token_contract(wrapped_native)
                    wbnb_balance_raw = wbnb_contract.functions.balanceOf(
                        Web3.to_checksum_address(self._signer.address)
                    ).call()

                    if wbnb_balance_raw > 0:
                        wbnb_balance = Decimal(wbnb_balance_raw) / Decimal(10**18)
                        logger.info(f"Unwrapping {wbnb_balance} WBNB -> BNB...")
                        self.unwrap_native(wbnb_balance)
                        logger.info("Unwrap complete")
                except Exception as e:
                    logger.warning(f"Failed to unwrap WBNB after close: {e}")

            return burn_result

        except Exception as e:
            logger.error(f"Failed to close position: {e}")
            return TxResult.failed(str(e))

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _price_range_to_ticks(self, pool: Pool, price_range: PriceRange) -> Tuple[int, int]:
        """Convert price range to ticks"""
        tick_spacing = pool.tick_spacing or TICK_SPACING_BY_FEE.get(pool.metadata.get("fee", 2500), 50)
        current_tick = pool.current_tick or 0
        decimals0 = pool.token0.decimals
        decimals1 = pool.token1.decimals

        if price_range.mode == RangeMode.TICK_RANGE:
            # Direct tick specification
            tick_lower = int(price_range.lower)
            tick_upper = int(price_range.upper)
        elif price_range.mode == RangeMode.ONE_TICK:
            # Single tick around current price
            tick_lower = self._align_tick_to_spacing(current_tick, tick_spacing, round_up=False)
            tick_upper = tick_lower + tick_spacing
        elif price_range.mode in (RangeMode.PERCENT, RangeMode.BPS):
            # Percentage-based range
            # For PERCENT mode: lower/upper are already fractions (e.g., -0.01, 0.01 for +/-1%)
            # For BPS mode: lower/upper are already fractions (stored as bps/10000)
            # Use 1 + value to get price factor (lower is negative, upper is positive)
            if price_range.mode == RangeMode.PERCENT:
                lower_factor = Decimal(1) + price_range.lower
                upper_factor = Decimal(1) + price_range.upper
            else:  # BPS
                lower_factor = Decimal(1) + price_range.lower / Decimal(10000)
                upper_factor = Decimal(1) + price_range.upper / Decimal(10000)

            current_price = pool.price
            price_lower = current_price * lower_factor
            price_upper = current_price * upper_factor

            tick_lower = self.price_to_tick(price_lower, decimals0, decimals1)
            tick_upper = self.price_to_tick(price_upper, decimals0, decimals1)
        elif price_range.mode == RangeMode.ABSOLUTE:
            # Absolute price range
            tick_lower = self.price_to_tick(price_range.lower, decimals0, decimals1)
            tick_upper = self.price_to_tick(price_range.upper, decimals0, decimals1)
        else:
            raise ConfigurationError.invalid("price_range.mode", f"Unsupported mode: {price_range.mode}")

        # Align to tick spacing
        tick_lower = self._align_tick_to_spacing(tick_lower, tick_spacing, round_up=False)
        tick_upper = self._align_tick_to_spacing(tick_upper, tick_spacing, round_up=True)

        # Ensure valid range
        tick_lower = max(MIN_TICK, tick_lower)
        tick_upper = min(MAX_TICK, tick_upper)

        if tick_lower >= tick_upper:
            tick_upper = tick_lower + tick_spacing

        return tick_lower, tick_upper

    def _ensure_approval_for_position_manager(
        self,
        token_address: str,
        amount: int,
    ) -> Optional[TxResult]:
        """Ensure token is approved for Position Manager"""
        try:
            token_contract = self._get_token_contract(token_address)
            pm_address = Web3.to_checksum_address(self.position_manager_address)

            allowance = token_contract.functions.allowance(
                Web3.to_checksum_address(self._signer.address),
                pm_address,
            ).call()

            if allowance >= amount:
                return None

            logger.info(f"Approving token {token_address} for Position Manager...")

            max_amount = 2**256 - 1
            approve_tx = token_contract.functions.approve(
                pm_address,
                max_amount,
            ).build_transaction({
                "from": self._signer.address,
                "gas": 100000,
                "nonce": self._web3.eth.get_transaction_count(self._signer.address),
                "chainId": self._chain_id,
            })

            self._add_gas_price(approve_tx)

            result = self._signer.sign_and_send(
                self._web3,
                approve_tx,
                wait_for_receipt=True,
                timeout=60,
            )

            if result["status"] == "success":
                logger.info(f"Token approval successful: {result['tx_hash']}")
                return TxResult.success(signature=result["tx_hash"])
            else:
                return TxResult.failed(f"Approval failed: {result.get('error')}")

        except Exception as e:
            logger.error(f"Token approval error: {e}")
            return TxResult.failed(f"Approval error: {e}")

    def _add_gas_price(self, tx: Dict[str, Any]):
        """Add gas price to transaction with minimum priority fee from config

        Note: web3 v7's build_transaction may auto-add EIP-1559 params.
        For BSC (legacy gas), we must remove them before adding gasPrice.
        """
        if self._chain_id == 1:
            latest_block = self._web3.eth.get_block("latest")
            base_fee = latest_block.get("baseFeePerGas", 0)
            # Use configurable priority fee (default 0.1 gwei for minimum cost)
            priority_fee_gwei = global_config.pancakeswap.priority_fee_gwei
            max_priority_fee = self._web3.to_wei(priority_fee_gwei, "gwei")
            max_fee = int(base_fee * global_config.pancakeswap.base_fee_multiplier) + max_priority_fee
            tx["maxFeePerGas"] = max_fee
            tx["maxPriorityFeePerGas"] = max_priority_fee
            # Remove legacy gasPrice if present
            tx.pop("gasPrice", None)
        else:
            # BSC uses legacy gas price (no EIP-1559)
            # Remove EIP-1559 params that web3 v7 may have auto-added
            tx.pop("maxFeePerGas", None)
            tx.pop("maxPriorityFeePerGas", None)
            tx["gasPrice"] = self._web3.eth.gas_price

    def _is_recoverable_error(self, error_str: str) -> bool:
        """Check if error is recoverable (network/timeout issues)"""
        error_lower = error_str.lower()
        recoverable_keywords = [
            "timeout", "connection", "network", "rate limit",
            "too many requests", "503", "502", "504",
            "temporarily unavailable", "service unavailable",
            "econnreset", "enotfound", "etimedout",
            "socket hang up", "request failed", "nonce too low",
            "replacement transaction underpriced",
        ]
        return any(keyword in error_lower for keyword in recoverable_keywords)

    def _is_slippage_error(self, error_str: str) -> bool:
        """Check if error is slippage-related"""
        error_lower = error_str.lower()
        slippage_keywords = [
            "slippage", "price moved", "insufficient output",
            "price impact", "price change", "amount out less than minimum",
            "exceeds slippage", "price slippage", "too little received",
        ]
        return any(keyword in error_lower for keyword in slippage_keywords)

    def _execute_with_retry(
        self,
        operation_name: str,
        tx_builder: callable,
        max_retries: Optional[int] = None,
        retry_delay: Optional[float] = None,
    ) -> TxResult:
        """
        Execute a transaction with automatic retry for recoverable errors.

        Args:
            operation_name: Name for logging
            tx_builder: Callable that builds and returns the transaction dict
            max_retries: Max retry attempts (defaults to config.tx.lp_max_retries)
            retry_delay: Base delay between retries (defaults to config.tx.retry_delay)

        Returns:
            TxResult
        """
        max_retries = max_retries if max_retries is not None else global_config.tx.lp_max_retries
        retry_delay = retry_delay if retry_delay is not None else global_config.tx.retry_delay
        last_error = None

        for attempt in range(max_retries):
            try:
                # Build fresh transaction (gets updated nonce)
                tx = tx_builder()

                # Add gas price
                self._add_gas_price(tx)

                # Sign and send
                result = self._signer.sign_and_send(
                    self._web3,
                    tx,
                    wait_for_receipt=True,
                )

                tx_result = self._result_to_tx_result(result)

                if tx_result.is_success:
                    if attempt > 0:
                        logger.info(f"{operation_name} succeeded after {attempt + 1} attempts")
                    return tx_result

                # Check if recoverable
                if result.get("error"):
                    error_str = str(result.get("error", ""))
                    if self._is_slippage_error(error_str) and attempt < max_retries - 1:
                        logger.warning(f"{operation_name} slippage error (attempt {attempt + 1}/{max_retries})")
                        time.sleep(retry_delay)
                        continue
                    if self._is_recoverable_error(error_str) and attempt < max_retries - 1:
                        logger.warning(f"{operation_name} recoverable error (attempt {attempt + 1}/{max_retries}): {error_str}")
                        time.sleep(retry_delay * (attempt + 1))
                        continue

                return tx_result

            except Exception as e:
                last_error = e
                error_str = str(e)

                if self._is_slippage_error(error_str):
                    logger.warning(f"{operation_name} slippage error (attempt {attempt + 1}/{max_retries}): {e}")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        continue
                    return TxResult.failed(
                        f"Slippage exceeded after {max_retries} attempts: {e}",
                        recoverable=True,
                        error_code=ErrorCode.SLIPPAGE_EXCEEDED,
                    )

                if self._is_recoverable_error(error_str) and attempt < max_retries - 1:
                    logger.warning(f"{operation_name} recoverable error (attempt {attempt + 1}/{max_retries}): {e}")
                    time.sleep(retry_delay * (attempt + 1))
                    continue

                logger.error(f"{operation_name} failed: {e}")
                return TxResult.failed(str(e), recoverable=self._is_recoverable_error(error_str))

        error_msg = f"Max retries ({max_retries}) exceeded for {operation_name}"
        if last_error:
            error_msg += f". Last error: {last_error}"
        return TxResult.failed(error_msg, recoverable=True)

    def close(self):
        """Cleanup (no-op, kept for compatibility)"""
        pass

    def __enter__(self) -> "PancakeSwapAdapter":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __repr__(self) -> str:
        addr = self.address[:10] + "..." if self.address else "None"
        return f"PancakeSwapAdapter(chain={self.chain_name}, address={addr})"
