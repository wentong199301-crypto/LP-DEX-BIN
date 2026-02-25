"""
Uniswap Unified Liquidity Adapter

Provides liquidity management functionality for Ethereum and other EVM chains
via Uniswap V3 and V4. Automatically detects pool version and routes calls accordingly.

Note: Swap operations should use 1inch adapter instead.
"""

import logging
import math
import time
from decimal import Decimal
from typing import Optional, Dict, Any, List, Tuple, Literal, Union
from enum import Enum

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
    NATIVE_TOKEN_ADDRESS,
)
from ...infra.evm_signer import EVMSigner, create_web3
from ...errors import SignerError, ConfigurationError, ErrorCode
from ...config import config as global_config

from .api import (
    UNISWAP_V3_POSITION_MANAGER_ADDRESSES,
    UNISWAP_V3_FACTORY_ADDRESSES,
    UNISWAP_V4_POOL_MANAGER_ADDRESSES,
    UNISWAP_V4_POSITION_MANAGER_ADDRESSES,
    UNISWAP_FEE_TIERS,
    TICK_SPACING_BY_FEE,
    UNISWAP_SUPPORTED_CHAINS,
    CHAIN_NAMES,
    NATIVE_ETH_ADDRESS,
    NO_HOOKS_ADDRESS,
)

logger = logging.getLogger(__name__)


class PoolVersion(Enum):
    """Uniswap pool version"""
    V3 = "v3"
    V4 = "v4"


# Standard ERC20 ABI
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

# V3 NonfungiblePositionManager ABI
V3_POSITION_MANAGER_ABI = [
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
    {
        "inputs": [
            {"name": "amountMinimum", "type": "uint256"},
            {"name": "recipient", "type": "address"},
        ],
        "name": "unwrapWETH9",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [
            {"name": "token", "type": "address"},
            {"name": "amountMinimum", "type": "uint256"},
            {"name": "recipient", "type": "address"},
        ],
        "name": "sweepToken",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "refundETH",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function"
    },
]

# V3 Factory ABI
V3_FACTORY_ABI = [
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

# V3 Pool ABI
V3_POOL_ABI = [
    {
        "inputs": [],
        "name": "slot0",
        "outputs": [
            {"name": "sqrtPriceX96", "type": "uint160"},
            {"name": "tick", "type": "int24"},
            {"name": "observationIndex", "type": "uint16"},
            {"name": "observationCardinality", "type": "uint16"},
            {"name": "observationCardinalityNext", "type": "uint16"},
            {"name": "feeProtocol", "type": "uint8"},
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

# V4 PoolManager ABI (for querying pool state)
V4_POOL_MANAGER_ABI = [
    {
        "inputs": [{"name": "id", "type": "bytes32"}],
        "name": "getSlot0",
        "outputs": [
            {"name": "sqrtPriceX96", "type": "uint160"},
            {"name": "tick", "type": "int24"},
            {"name": "protocolFee", "type": "uint24"},
            {"name": "lpFee", "type": "uint24"},
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"name": "id", "type": "bytes32"}],
        "name": "getLiquidity",
        "outputs": [{"name": "liquidity", "type": "uint128"}],
        "stateMutability": "view",
        "type": "function"
    },
]

# V4 PositionManager ABI
V4_POSITION_MANAGER_ABI = [
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
        "inputs": [{"name": "tokenId", "type": "uint256"}],
        "name": "getPositionInfo",
        "outputs": [
            {
                "components": [
                    {"name": "currency0", "type": "address"},
                    {"name": "currency1", "type": "address"},
                    {"name": "fee", "type": "uint24"},
                    {"name": "tickSpacing", "type": "int24"},
                    {"name": "hooks", "type": "address"},
                ],
                "name": "poolKey",
                "type": "tuple"
            },
            {"name": "tickLower", "type": "int24"},
            {"name": "tickUpper", "type": "int24"},
            {"name": "liquidity", "type": "uint128"},
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"name": "unlockData", "type": "bytes"},
            {"name": "deadline", "type": "uint256"},
        ],
        "name": "modifyLiquidities",
        "outputs": [{"name": "returnData", "type": "bytes"}],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [{"name": "tokenId", "type": "uint256"}],
        "name": "burn",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
]

# Constants
Q96 = 2**96
MIN_TICK = -887272
MAX_TICK = 887272

# V4 Action Types (from Uniswap V4 Actions library)
class V4Actions:
    """Uniswap V4 PositionManager action types"""
    # Liquidity actions
    INCREASE_LIQUIDITY = 0x00
    DECREASE_LIQUIDITY = 0x01
    MINT_POSITION = 0x02
    BURN_POSITION = 0x03
    # Delta-resolving actions
    TAKE_PAIR = 0x14  # 20
    SETTLE_PAIR = 0x15  # 21
    SETTLE = 0x16  # 22
    TAKE = 0x17  # 23
    CLOSE_CURRENCY = 0x18  # 24
    CLEAR_OR_TAKE = 0x19  # 25
    SWEEP = 0x1a  # 26


class V4ActionEncoder:
    """
    Encodes actions for Uniswap V4 PositionManager.modifyLiquidities()

    The unlockData format is: abi.encode(bytes actions, bytes[] params)
    - actions: concatenated action bytes
    - params: array of ABI-encoded parameters for each action
    """

    @staticmethod
    def encode_pool_key(currency0: str, currency1: str, fee: int, tick_spacing: int, hooks: str) -> tuple:
        """Create PoolKey tuple"""
        return (
            Web3.to_checksum_address(currency0),
            Web3.to_checksum_address(currency1),
            fee,
            tick_spacing,
            Web3.to_checksum_address(hooks),
        )

    @staticmethod
    def encode_mint_position(
        pool_key: tuple,
        tick_lower: int,
        tick_upper: int,
        liquidity: int,
        amount0_max: int,
        amount1_max: int,
        recipient: str,
        hook_data: bytes = b''
    ) -> bytes:
        """Encode MINT_POSITION action parameters"""
        from eth_abi import encode
        return encode(
            ['(address,address,uint24,int24,address)', 'int24', 'int24', 'uint256', 'uint128', 'uint128', 'address', 'bytes'],
            [pool_key, tick_lower, tick_upper, liquidity, amount0_max, amount1_max, Web3.to_checksum_address(recipient), hook_data]
        )

    @staticmethod
    def encode_increase_liquidity(
        token_id: int,
        liquidity: int,
        amount0_max: int,
        amount1_max: int,
        hook_data: bytes = b''
    ) -> bytes:
        """Encode INCREASE_LIQUIDITY action parameters"""
        from eth_abi import encode
        return encode(
            ['uint256', 'uint256', 'uint128', 'uint128', 'bytes'],
            [token_id, liquidity, amount0_max, amount1_max, hook_data]
        )

    @staticmethod
    def encode_decrease_liquidity(
        token_id: int,
        liquidity: int,
        amount0_min: int,
        amount1_min: int,
        hook_data: bytes = b''
    ) -> bytes:
        """Encode DECREASE_LIQUIDITY action parameters"""
        from eth_abi import encode
        return encode(
            ['uint256', 'uint256', 'uint128', 'uint128', 'bytes'],
            [token_id, liquidity, amount0_min, amount1_min, hook_data]
        )

    @staticmethod
    def encode_burn_position(
        token_id: int,
        amount0_min: int,
        amount1_min: int,
        hook_data: bytes = b''
    ) -> bytes:
        """Encode BURN_POSITION action parameters"""
        from eth_abi import encode
        return encode(
            ['uint256', 'uint128', 'uint128', 'bytes'],
            [token_id, amount0_min, amount1_min, hook_data]
        )

    @staticmethod
    def encode_settle_pair(currency0: str, currency1: str) -> bytes:
        """Encode SETTLE_PAIR action parameters"""
        from eth_abi import encode
        return encode(
            ['address', 'address'],
            [Web3.to_checksum_address(currency0), Web3.to_checksum_address(currency1)]
        )

    @staticmethod
    def encode_take_pair(currency0: str, currency1: str, recipient: str) -> bytes:
        """Encode TAKE_PAIR action parameters"""
        from eth_abi import encode
        return encode(
            ['address', 'address', 'address'],
            [Web3.to_checksum_address(currency0), Web3.to_checksum_address(currency1), Web3.to_checksum_address(recipient)]
        )

    @staticmethod
    def encode_close_currency(currency: str) -> bytes:
        """Encode CLOSE_CURRENCY action parameters"""
        from eth_abi import encode
        return encode(['address'], [Web3.to_checksum_address(currency)])

    @staticmethod
    def encode_sweep(currency: str, recipient: str) -> bytes:
        """Encode SWEEP action parameters"""
        from eth_abi import encode
        return encode(
            ['address', 'address'],
            [Web3.to_checksum_address(currency), Web3.to_checksum_address(recipient)]
        )

    @staticmethod
    def build_unlock_data(actions: List[int], params: List[bytes]) -> bytes:
        """
        Build the unlockData for modifyLiquidities

        Format: abi.encode(bytes actions, bytes[] params)
        """
        from eth_abi import encode
        actions_bytes = bytes(actions)
        return encode(['bytes', 'bytes[]'], [actions_bytes, params])


class UniswapAdapter:
    """
    Unified Uniswap Liquidity Adapter for V3 and V4

    Automatically detects pool version and routes calls to appropriate contracts.
    Supports Ethereum, Optimism, Polygon, Arbitrum, and Base.

    Usage:
        signer = EVMSigner.from_env()
        adapter = UniswapAdapter(chain_id=1, signer=signer)

        # Get pool (auto-detects V3 or V4)
        pool = adapter.get_pool("WETH", "USDC", fee=3000)

        # Or specify version explicitly
        pool = adapter.get_pool("WETH", "USDC", fee=3000, version="v3")

        # Open position
        result = adapter.open_position(pool, PriceRange.percent(0.05), amount0=Decimal("1.0"))

        # List positions
        positions = adapter.get_positions()

        # Close position
        result = adapter.close_position(position)
    """

    name = "uniswap"

    def __init__(
        self,
        chain_id: int = 1,
        signer: Optional[EVMSigner] = None,
        rpc_url: Optional[str] = None,
        default_version: Literal["v3", "v4"] = "v3",
    ):
        """
        Initialize Uniswap adapter

        Args:
            chain_id: Chain ID (1=ETH, 10=Optimism, 137=Polygon, 42161=Arbitrum, 8453=Base)
            signer: Optional EVM signer for executing transactions
            rpc_url: Optional RPC URL (uses config default if not provided)
            default_version: Default pool version when not specified ("v3" or "v4")
        """
        if not _HAS_WEB3:
            raise RuntimeError(
                "web3 is required for UniswapAdapter. "
                "Install with: pip install web3"
            )

        self._chain_id = chain_id
        self._signer = signer
        self._default_version = default_version

        # Validate chain ID
        if chain_id not in UNISWAP_SUPPORTED_CHAINS:
            supported = ", ".join(f"{c} ({CHAIN_NAMES.get(c, 'Unknown')})" for c in UNISWAP_SUPPORTED_CHAINS)
            raise ConfigurationError.invalid(
                "chain_id",
                f"Unsupported chain ID: {chain_id}. Supported: {supported}"
            )

        # Determine RPC URL
        if rpc_url:
            self._rpc_url = rpc_url
        else:
            self._rpc_url = global_config.uniswap.eth_rpc_url

        # Validate RPC URL
        if not self._rpc_url or not self._rpc_url.strip():
            raise ConfigurationError.missing(
                "ETH_RPC_URL",
                "Ethereum RPC URL is required for UniswapAdapter. "
                "Please set ETH_RPC_URL environment variable or pass rpc_url parameter. "
                "Example: ETH_RPC_URL=https://eth-mainnet.g.alchemy.com/v2/YOUR_API_KEY"
            )

        # Initialize web3
        self._web3 = create_web3(self._rpc_url, chain_id)

        # Internal nonce tracker to avoid stale nonce from RPC
        self._nonce: Optional[int] = None

        logger.info(f"Initialized UniswapAdapter for {self.chain_name} ({chain_id})")

    @property
    def chain_id(self) -> int:
        return self._chain_id

    @property
    def chain_name(self) -> str:
        return CHAIN_NAMES.get(self._chain_id, f"Chain-{self._chain_id}")

    @property
    def address(self) -> Optional[str]:
        return self._signer.address if self._signer else None

    @property
    def pubkey(self) -> Optional[str]:
        return self.address

    def _get_nonce(self) -> int:
        """Get next nonce, using internal tracker to avoid stale RPC results."""
        rpc_nonce = self._web3.eth.get_transaction_count(self._signer.address, "pending")
        if self._nonce is None or rpc_nonce > self._nonce:
            self._nonce = rpc_nonce
        nonce = self._nonce
        self._nonce = nonce + 1
        return nonce

    def _reset_nonce(self):
        """Reset nonce tracker (call after errors that may leave nonce inconsistent)."""
        self._nonce = None

    @property
    def web3(self) -> "Web3":
        return self._web3

    @property
    def v3_position_manager_address(self) -> str:
        return UNISWAP_V3_POSITION_MANAGER_ADDRESSES.get(self._chain_id, UNISWAP_V3_POSITION_MANAGER_ADDRESSES[1])

    @property
    def v3_factory_address(self) -> str:
        return UNISWAP_V3_FACTORY_ADDRESSES.get(self._chain_id, UNISWAP_V3_FACTORY_ADDRESSES[1])

    @property
    def v4_pool_manager_address(self) -> str:
        return UNISWAP_V4_POOL_MANAGER_ADDRESSES.get(self._chain_id, UNISWAP_V4_POOL_MANAGER_ADDRESSES[1])

    @property
    def v4_position_manager_address(self) -> str:
        return UNISWAP_V4_POSITION_MANAGER_ADDRESSES.get(self._chain_id, UNISWAP_V4_POSITION_MANAGER_ADDRESSES[1])

    # =========================================================================
    # Contract Instances
    # =========================================================================

    def _get_v3_position_manager(self):
        return self._web3.eth.contract(
            address=Web3.to_checksum_address(self.v3_position_manager_address),
            abi=V3_POSITION_MANAGER_ABI,
        )

    def _get_v3_factory(self):
        return self._web3.eth.contract(
            address=Web3.to_checksum_address(self.v3_factory_address),
            abi=V3_FACTORY_ABI,
        )

    def _get_v3_pool(self, pool_address: str):
        return self._web3.eth.contract(
            address=Web3.to_checksum_address(pool_address),
            abi=V3_POOL_ABI,
        )

    def _get_v4_position_manager(self):
        return self._web3.eth.contract(
            address=Web3.to_checksum_address(self.v4_position_manager_address),
            abi=V4_POSITION_MANAGER_ABI,
        )

    def _get_v4_pool_manager(self):
        return self._web3.eth.contract(
            address=Web3.to_checksum_address(self.v4_pool_manager_address),
            abi=V4_POOL_MANAGER_ABI,
        )

    def _get_token_contract(self, token_address: str):
        return self._web3.eth.contract(
            address=Web3.to_checksum_address(token_address),
            abi=ERC20_ABI,
        )

    def unwrap_native(self, amount: Decimal) -> str:
        """
        Unwrap WETH back to native ETH.

        Args:
            amount: Amount of WETH to unwrap (UI units, e.g. Decimal("0.01"))

        Returns:
            Transaction hash
        """
        if not self._signer:
            raise SignerError.missing("Signer required for unwrap")

        weth_address = get_wrapped_native_address(self._chain_id)
        raw_amount = int(amount * Decimal(10**18))

        weth_abi = [{"constant": False, "inputs": [{"name": "wad", "type": "uint256"}], "name": "withdraw", "outputs": [], "type": "function"}]
        contract = self._web3.eth.contract(
            address=self._web3.to_checksum_address(weth_address), abi=weth_abi
        )

        tx = contract.functions.withdraw(raw_amount).build_transaction({
            "from": self.address,
            "value": 0,
            "gas": 50000,
            "nonce": self._get_nonce(),
            "chainId": self._chain_id,
        })

        self._add_gas_price(tx)
        raw_tx, tx_hash_hex = self._signer.sign_transaction(tx)
        self._web3.eth.send_raw_transaction(raw_tx)
        receipt = self._web3.eth.wait_for_transaction_receipt(bytes.fromhex(tx_hash_hex), timeout=60)

        status = "OK" if receipt["status"] == 1 else "FAILED"
        logger.info(f"Unwrap {amount} WETH -> ETH: {status} (tx: {tx_hash_hex})")
        return tx_hash_hex

    # =========================================================================
    # Version Detection
    # =========================================================================

    def detect_pool_version(self, pool: Pool) -> PoolVersion:
        """
        Detect if a pool is V3 or V4 based on metadata

        Args:
            pool: Pool object

        Returns:
            PoolVersion.V3 or PoolVersion.V4
        """
        version = pool.metadata.get("version")
        if version == "v4":
            return PoolVersion.V4
        return PoolVersion.V3

    def _is_v4_pool(self, pool: Pool) -> bool:
        """Check if pool is V4"""
        return self.detect_pool_version(pool) == PoolVersion.V4

    # =========================================================================
    # Math Helper Functions
    # =========================================================================

    @staticmethod
    def tick_to_price(tick: int, decimals0: int = 18, decimals1: int = 18) -> Decimal:
        """Convert tick to price using full Decimal precision.

        price = 1.0001^tick * 10^(decimals0 - decimals1)
        """
        # Use Decimal exponentiation to avoid float precision loss on extreme ticks
        base = Decimal("1.0001")
        if tick >= 0:
            price = base ** tick
        else:
            price = Decimal(1) / (base ** (-tick))
        decimal_adjustment = Decimal(10 ** (decimals0 - decimals1))
        return price * decimal_adjustment

    @staticmethod
    def price_to_tick(price: Decimal, decimals0: int = 18, decimals1: int = 18) -> int:
        """Convert price to tick using full Decimal precision.

        tick = log(price * 10^(decimals1 - decimals0)) / log(1.0001)
        """
        decimal_adjustment = Decimal(10 ** (decimals1 - decimals0))
        adjusted_price = price * decimal_adjustment
        if adjusted_price <= 0:
            return MIN_TICK
        # Use Decimal.ln() for precision instead of float math.log
        tick = int(adjusted_price.ln() / Decimal("1.0001").ln())
        return max(MIN_TICK, min(MAX_TICK, tick))

    @staticmethod
    def sqrt_price_x96_to_price(sqrt_price_x96: int, decimals0: int = 18, decimals1: int = 18) -> Decimal:
        """Convert sqrtPriceX96 to price"""
        price = (Decimal(sqrt_price_x96) / Decimal(Q96)) ** 2
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

    def _get_eth_usd_price(self) -> Optional[Decimal]:
        """
        Fetch ETH/USD price from USDC/WETH pool.

        Returns:
            ETH price in USD, or None if fetch fails
        """
        try:
            # USDC/WETH 0.3% pool on Ethereum mainnet
            usdc_weth_pool = "0x8ad599c3A0ff1De082011EFDDc58f1908eb6e6D8"
            pool_contract = self._web3.eth.contract(
                address=Web3.to_checksum_address(usdc_weth_pool),
                abi=V3_POOL_ABI,
            )
            slot0 = pool_contract.functions.slot0().call()
            sqrt_price_x96 = slot0[0]
            # USDC decimals=6, WETH decimals=18
            # Price = USDC per WETH
            price = self.sqrt_price_x96_to_price(sqrt_price_x96, 6, 18)
            if price > 0:
                # price is USDC/WETH, so ETH price = 1/price
                return Decimal(1) / price
            return None
        except Exception as e:
            logger.debug(f"Failed to get ETH/USD price: {e}")
            return None

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
            elif token1_is_stable and not token0_is_stable:
                # Token1 is stablecoin: TVL = (balance0 * price) + balance1
                tvl = (balance0 * price) + balance1
            else:
                # Neither is stablecoin - need USD price for one of them
                # Calculate TVL in token1 first, then convert to USD
                tvl_in_token1 = (balance0 * price) + balance1

                # Try to get USD price for token1
                token1_upper = token1_symbol.upper()
                if token1_upper in ("WETH", "ETH"):
                    eth_usd = self._get_eth_usd_price()
                    if eth_usd:
                        tvl = tvl_in_token1 * eth_usd
                    else:
                        tvl = tvl_in_token1  # Fallback: return in ETH terms
                else:
                    # For other non-stablecoin pairs, return value in token1 terms
                    # (Better than wrong USD value)
                    tvl = tvl_in_token1

            return tvl
        except Exception:
            return Decimal(0)

    def _calculate_liquidity(
        self,
        sqrt_price_x96: int,
        tick_lower: int,
        tick_upper: int,
        amount0: int,
        amount1: int,
    ) -> int:
        """
        Calculate liquidity for a concentrated liquidity position.

        Based on Uniswap V3/V4 math:
        - L = amount0 * (sqrt(p_upper) * sqrt(p)) / (sqrt(p_upper) - sqrt(p)) when price in range (using token0)
        - L = amount1 / (sqrt(p) - sqrt(p_lower)) when price in range (using token1)
        - Take min of both if both amounts provided

        Args:
            sqrt_price_x96: Current sqrtPriceX96
            tick_lower: Lower tick of range
            tick_upper: Upper tick of range
            amount0: Amount of token0 (raw)
            amount1: Amount of token1 (raw)

        Returns:
            Liquidity as integer
        """
        # Calculate sqrt prices for tick bounds
        sqrt_ratio_lower = int(Decimal(str(1.0001 ** (tick_lower / 2))) * Decimal(Q96))
        sqrt_ratio_upper = int(Decimal(str(1.0001 ** (tick_upper / 2))) * Decimal(Q96))

        # If pool has no price yet, estimate from amounts
        if sqrt_price_x96 == 0:
            # Use geometric mean of range
            sqrt_price_x96 = int((Decimal(sqrt_ratio_lower) * Decimal(sqrt_ratio_upper)).sqrt())

        liquidity_from_0 = 0
        liquidity_from_1 = 0

        if sqrt_price_x96 <= sqrt_ratio_lower:
            # Current price is below range - only token0 needed
            if amount0 > 0 and sqrt_ratio_upper > sqrt_ratio_lower:
                liquidity_from_0 = (
                    amount0 * sqrt_ratio_lower * sqrt_ratio_upper
                ) // ((sqrt_ratio_upper - sqrt_ratio_lower) * Q96)
        elif sqrt_price_x96 >= sqrt_ratio_upper:
            # Current price is above range - only token1 needed
            if amount1 > 0 and sqrt_ratio_upper > sqrt_ratio_lower:
                liquidity_from_1 = (amount1 * Q96) // (sqrt_ratio_upper - sqrt_ratio_lower)
        else:
            # Current price is in range - need both tokens
            if amount0 > 0 and sqrt_ratio_upper > sqrt_price_x96:
                liquidity_from_0 = (
                    amount0 * sqrt_price_x96 * sqrt_ratio_upper
                ) // ((sqrt_ratio_upper - sqrt_price_x96) * Q96)
            if amount1 > 0 and sqrt_price_x96 > sqrt_ratio_lower:
                liquidity_from_1 = (amount1 * Q96) // (sqrt_price_x96 - sqrt_ratio_lower)

        # Return the constraining liquidity (minimum of both if both provided)
        if liquidity_from_0 > 0 and liquidity_from_1 > 0:
            return min(liquidity_from_0, liquidity_from_1)
        return liquidity_from_0 or liquidity_from_1 or 1  # At least 1 to avoid revert

    # =========================================================================
    # Pool Methods
    # =========================================================================

    def get_pool(
        self,
        token0: str,
        token1: str,
        fee: int = 3000,
        version: Optional[Literal["v3", "v4"]] = None,
        hooks: str = NO_HOOKS_ADDRESS,
    ) -> Optional[Pool]:
        """
        Get pool information

        Args:
            token0: First token (symbol or address)
            token1: Second token (symbol or address)
            fee: Fee tier (100, 500, 3000, 10000)
            version: Pool version ("v3" or "v4"), auto-detects if None
            hooks: Hooks address for V4 (defaults to no hooks)

        Returns:
            Pool object or None if not found
        """
        version = version or self._default_version

        if version == "v4":
            return self._get_pool_v4(token0, token1, fee, hooks)
        else:
            return self._get_pool_v3(token0, token1, fee)

    def _get_pool_v3(self, token0: str, token1: str, fee: int) -> Optional[Pool]:
        """Get V3 pool"""
        addr0 = resolve_token_address(token0, self._chain_id)
        addr1 = resolve_token_address(token1, self._chain_id)

        # Handle native tokens - use wrapped version
        if is_native_token(addr0):
            addr0 = get_wrapped_native_address(self._chain_id)
        if is_native_token(addr1):
            addr1 = get_wrapped_native_address(self._chain_id)

        # Sort addresses
        if addr0.lower() > addr1.lower():
            addr0, addr1 = addr1, addr0

        try:
            factory = self._get_v3_factory()
            pool_address = factory.functions.getPool(
                Web3.to_checksum_address(addr0),
                Web3.to_checksum_address(addr1),
                fee,
            ).call()

            if pool_address == "0x0000000000000000000000000000000000000000":
                return None

            pool_contract = self._get_v3_pool(pool_address)
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

            price = self.sqrt_price_x96_to_price(sqrt_price_x96, decimals0, decimals1)

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
                dex="uniswap",
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
                    "version": "v3",
                    "liquidity": liquidity,
                    "fee": fee,
                    "chain_id": self._chain_id,
                },
            )

        except Exception as e:
            logger.error(f"Failed to get V3 pool: {e}")
            return None

    def _is_v4_native(self, address: str) -> bool:
        """Check if address is native token for V4 (address(0) or sentinel)"""
        addr_lower = address.lower()
        return (
            addr_lower == NATIVE_ETH_ADDRESS.lower() or  # V4 address(0)
            is_native_token(address)  # 0xEeEe... sentinel
        )

    def _get_pool_v4(self, token0: str, token1: str, fee: int, hooks: str) -> Optional[Pool]:
        """Get V4 pool"""
        # V4 uses address(0) for native ETH
        # Handle both symbol inputs and raw addresses (from position queries)
        if token0.startswith("0x"):
            addr0 = token0
        else:
            addr0 = resolve_token_address(token0, self._chain_id)

        if token1.startswith("0x"):
            addr1 = token1
        else:
            addr1 = resolve_token_address(token1, self._chain_id)

        # Normalize native token addresses to V4's address(0)
        if self._is_v4_native(addr0):
            addr0 = NATIVE_ETH_ADDRESS
        if self._is_v4_native(addr1):
            addr1 = NATIVE_ETH_ADDRESS

        # Sort addresses
        if addr0.lower() > addr1.lower():
            addr0, addr1 = addr1, addr0

        tick_spacing = TICK_SPACING_BY_FEE.get(fee, 60)

        try:
            # Get token info
            if addr0 == NATIVE_ETH_ADDRESS:
                symbol0, decimals0 = "ETH", 18
            else:
                token0_contract = self._get_token_contract(addr0)
                decimals0 = token0_contract.functions.decimals().call()
                try:
                    symbol0 = token0_contract.functions.symbol().call()
                except Exception:
                    symbol0 = get_token_symbol(addr0, self._chain_id) or addr0[:8]

            if addr1 == NATIVE_ETH_ADDRESS:
                symbol1, decimals1 = "ETH", 18
            else:
                token1_contract = self._get_token_contract(addr1)
                decimals1 = token1_contract.functions.decimals().call()
                try:
                    symbol1 = token1_contract.functions.symbol().call()
                except Exception:
                    symbol1 = get_token_symbol(addr1, self._chain_id) or addr1[:8]

            # Generate pool ID from key
            pool_key = (
                Web3.to_checksum_address(addr0),
                Web3.to_checksum_address(addr1),
                fee,
                tick_spacing,
                Web3.to_checksum_address(hooks),
            )

            pool_id_bytes = Web3.keccak(
                self._web3.codec.encode(
                    ['address', 'address', 'uint24', 'int24', 'address'],
                    list(pool_key)
                )
            )
            pool_id = pool_id_bytes.hex()

            # Query pool state from PoolManager
            sqrt_price_x96 = 0
            current_tick = 0
            liquidity = 0
            try:
                pool_manager = self._get_v4_pool_manager()
                slot0 = pool_manager.functions.getSlot0(pool_id_bytes).call()
                sqrt_price_x96 = slot0[0]
                current_tick = slot0[1]
                liquidity = pool_manager.functions.getLiquidity(pool_id_bytes).call()
            except Exception as e:
                # Pool may not exist yet, or RPC error - use defaults
                logger.debug(f"Could not fetch V4 pool state: {e}")

            # Calculate price from sqrtPriceX96
            if sqrt_price_x96 > 0:
                price = self.sqrt_price_x96_to_price(sqrt_price_x96, decimals0, decimals1)
            else:
                price = Decimal(0)

            token0_obj = Token(mint=addr0, symbol=symbol0, decimals=decimals0)
            token1_obj = Token(mint=addr1, symbol=symbol1, decimals=decimals1)

            return Pool(
                address=pool_id,
                dex="uniswap",
                symbol=f"{symbol0}/{symbol1}",
                token0=token0_obj,
                token1=token1_obj,
                price=price,
                fee_rate=Decimal(fee) / Decimal(1_000_000),
                tick_spacing=tick_spacing,
                current_tick=current_tick,
                sqrt_price_x64=sqrt_price_x96,
                metadata={
                    "version": "v4",
                    "fee": fee,
                    "hooks": hooks,
                    "pool_key": pool_key,
                    "liquidity": liquidity,
                    "chain_id": self._chain_id,
                },
            )

        except Exception as e:
            logger.error(f"Failed to get V4 pool: {e}")
            return None

    def get_pool_by_address(self, pool_address: str) -> Optional[Pool]:
        """Get V3 pool by address (V4 uses pool IDs, not addresses)"""
        try:
            pool_contract = self._get_v3_pool(pool_address)

            slot0 = pool_contract.functions.slot0().call()
            sqrt_price_x96 = slot0[0]
            current_tick = slot0[1]

            token0_addr = pool_contract.functions.token0().call()
            token1_addr = pool_contract.functions.token1().call()
            fee = pool_contract.functions.fee().call()
            tick_spacing = pool_contract.functions.tickSpacing().call()
            liquidity = pool_contract.functions.liquidity().call()

            token0_contract = self._get_token_contract(token0_addr)
            token1_contract = self._get_token_contract(token1_addr)

            decimals0 = token0_contract.functions.decimals().call()
            decimals1 = token1_contract.functions.decimals().call()

            try:
                symbol0 = token0_contract.functions.symbol().call()
            except Exception:
                symbol0 = token0_addr[:8]

            try:
                symbol1 = token1_contract.functions.symbol().call()
            except Exception:
                symbol1 = token1_addr[:8]

            price = self.sqrt_price_x96_to_price(sqrt_price_x96, decimals0, decimals1)

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
                dex="uniswap",
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
                    "version": "v3",
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

    def get_positions(self, owner: Optional[str] = None, version: Optional[Literal["v3", "v4"]] = None) -> List[Position]:
        """
        Get all positions owned by address

        Args:
            owner: Owner address (defaults to signer)
            version: Pool version to query ("v3", "v4", or None for both)

        Returns:
            List of Position objects
        """
        if owner is None:
            if not self._signer:
                raise SignerError.not_configured()
            owner = self._signer.address

        positions = []

        if version is None or version == "v3":
            positions.extend(self._get_positions_v3(owner))

        if version is None or version == "v4":
            positions.extend(self._get_positions_v4(owner))

        return positions

    def _get_positions_v3(self, owner: str) -> List[Position]:
        """Get V3 positions"""
        positions = []
        try:
            pm = self._get_v3_position_manager()
            balance = pm.functions.balanceOf(Web3.to_checksum_address(owner)).call()

            for i in range(balance):
                token_id = pm.functions.tokenOfOwnerByIndex(
                    Web3.to_checksum_address(owner), i
                ).call()
                position = self._get_position_v3(token_id)
                if position:
                    positions.append(position)

        except Exception as e:
            logger.error(f"Failed to get V3 positions: {e}")

        return positions

    def _get_positions_v4(self, owner: str) -> List[Position]:
        """Get V4 positions"""
        positions = []
        try:
            pm = self._get_v4_position_manager()
            balance = pm.functions.balanceOf(Web3.to_checksum_address(owner)).call()

            for i in range(balance):
                token_id = pm.functions.tokenOfOwnerByIndex(
                    Web3.to_checksum_address(owner), i
                ).call()
                position = self._get_position_v4(token_id)
                if position:
                    positions.append(position)

        except Exception as e:
            logger.error(f"Failed to get V4 positions: {e}")

        return positions

    def get_position(self, token_id: int, version: Literal["v3", "v4"] = "v3") -> Optional[Position]:
        """Get position by token ID"""
        if version == "v4":
            return self._get_position_v4(token_id)
        return self._get_position_v3(token_id)

    def _get_position_v3(self, token_id: int) -> Optional[Position]:
        """Get V3 position by token ID"""
        try:
            pm = self._get_v3_position_manager()
            pos_data = pm.functions.positions(token_id).call()

            token0_addr = pos_data[2]
            token1_addr = pos_data[3]
            fee = pos_data[4]
            tick_lower = pos_data[5]
            tick_upper = pos_data[6]
            liquidity = pos_data[7]
            tokens_owed0 = pos_data[10]
            tokens_owed1 = pos_data[11]

            pool = self._get_pool_v3(token0_addr, token1_addr, fee)
            if not pool:
                return None

            decimals0 = pool.token0.decimals
            decimals1 = pool.token1.decimals
            price_lower = self.tick_to_price(tick_lower, decimals0, decimals1)
            price_upper = self.tick_to_price(tick_upper, decimals0, decimals1)

            is_in_range = tick_lower <= pool.current_tick <= tick_upper

            # Calculate amounts
            amount0, amount1 = Decimal(0), Decimal(0)
            if liquidity > 0:
                sqrt_price = Decimal(pool.sqrt_price_x64) / Decimal(Q96)
                sqrt_price_lower = Decimal(str(1.0001 ** (tick_lower / 2)))
                sqrt_price_upper = Decimal(str(1.0001 ** (tick_upper / 2)))

                if pool.current_tick < tick_lower:
                    amount0 = Decimal(liquidity) * (1 / sqrt_price_lower - 1 / sqrt_price_upper)
                elif pool.current_tick >= tick_upper:
                    amount1 = Decimal(liquidity) * (sqrt_price_upper - sqrt_price_lower)
                else:
                    amount0 = Decimal(liquidity) * (1 / sqrt_price - 1 / sqrt_price_upper)
                    amount1 = Decimal(liquidity) * (sqrt_price - sqrt_price_lower)

                amount0 = amount0 / Decimal(10 ** decimals0)
                amount1 = amount1 / Decimal(10 ** decimals1)

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
                    "version": "v3",
                    "token_id": token_id,
                    "fee": fee,
                    "chain_id": self._chain_id,
                },
            )

        except Exception as e:
            logger.error(f"Failed to get V3 position {token_id}: {e}")
            return None

    def _get_position_v4(self, token_id: int) -> Optional[Position]:
        """Get V4 position by token ID"""
        try:
            pm = self._get_v4_position_manager()
            pos_info = pm.functions.getPositionInfo(token_id).call()

            pool_key = pos_info[0]
            tick_lower = pos_info[1]
            tick_upper = pos_info[2]
            liquidity = pos_info[3]

            currency0, currency1, fee, tick_spacing, hooks = pool_key

            pool = self._get_pool_v4(currency0, currency1, fee, hooks)
            if not pool:
                return None

            decimals0 = pool.token0.decimals
            decimals1 = pool.token1.decimals
            price_lower = self.tick_to_price(tick_lower, decimals0, decimals1)
            price_upper = self.tick_to_price(tick_upper, decimals0, decimals1)

            return Position(
                id=str(token_id),
                pool=pool,
                owner=self._signer.address if self._signer else "",
                price_lower=price_lower,
                price_upper=price_upper,
                amount0=Decimal(0),
                amount1=Decimal(0),
                liquidity=liquidity,
                unclaimed_fees={},
                is_in_range=True,
                nft_mint=str(token_id),
                tick_lower=tick_lower,
                tick_upper=tick_upper,
                metadata={
                    "version": "v4",
                    "token_id": token_id,
                    "fee": fee,
                    "hooks": hooks,
                    "pool_key": pool_key,
                    "chain_id": self._chain_id,
                },
            )

        except Exception as e:
            logger.error(f"Failed to get V4 position {token_id}: {e}")
            return None

    # =========================================================================
    # Liquidity Operations
    # =========================================================================

    def open_position(
        self,
        pool: Pool,
        price_range: PriceRange,
        amount0: Optional[Decimal] = None,
        amount1: Optional[Decimal] = None,
        slippage_bps: Optional[int] = None,
    ) -> TxResult:
        """Open a new liquidity position (routes to V3 or V4 based on pool)"""
        # Use config default if not specified
        if slippage_bps is None:
            slippage_bps = global_config.trading.default_lp_slippage_bps

        if self._is_v4_pool(pool):
            return self._open_position_v4(pool, price_range, amount0, amount1, slippage_bps)
        return self._open_position_v3(pool, price_range, amount0, amount1, slippage_bps)

    def _open_position_v3(
        self,
        pool: Pool,
        price_range: PriceRange,
        amount0: Optional[Decimal],
        amount1: Optional[Decimal],
        slippage_bps: int,
    ) -> TxResult:
        """Open V3 position"""
        if not self._signer:
            raise SignerError.not_configured()

        if amount0 is None and amount1 is None:
            raise ConfigurationError.missing("amount0 or amount1")

        try:
            tick_lower, tick_upper = self._price_range_to_ticks(pool, price_range)

            decimals0 = pool.token0.decimals
            decimals1 = pool.token1.decimals
            raw_amount0 = int((amount0 or Decimal(0)) * Decimal(10 ** decimals0))
            raw_amount1 = int((amount1 or Decimal(0)) * Decimal(10 ** decimals1))

            # Set min amounts to 0: Uniswap V3 mint computes liquidity as
            # min(liq_from_amount0, liq_from_amount1) for in-range positions,
            # so actual deposited amounts can be much less than desired.
            # Deadline provides frontrun protection.
            min_amount0 = 0
            min_amount1 = 0

            token0_addr = pool.token0.mint
            token1_addr = pool.token1.mint

            native_value = 0
            wrapped_native = get_wrapped_native_address(self._chain_id)
            token0_is_native = token0_addr.lower() == wrapped_native.lower()
            token1_is_native = token1_addr.lower() == wrapped_native.lower()

            # Handle native ETH value (can send ETH for wrapped native tokens)
            if token0_is_native and raw_amount0 > 0:
                native_value += raw_amount0
            if token1_is_native and raw_amount1 > 0:
                native_value += raw_amount1

            # Approve non-native tokens (must approve even in mixed pairs)
            if not token0_is_native and raw_amount0 > 0:
                approval = self._ensure_approval(token0_addr, raw_amount0, self.v3_position_manager_address)
                if approval and not approval.is_success:
                    return approval
            if not token1_is_native and raw_amount1 > 0:
                approval = self._ensure_approval(token1_addr, raw_amount1, self.v3_position_manager_address)
                if approval and not approval.is_success:
                    return approval

            fee = pool.metadata.get("fee", 3000)

            def build_tx():
                deadline = int(time.time()) + global_config.evm.tx_deadline_seconds
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

                pm = self._get_v3_position_manager()

                if native_value > 0:
                    # Use multicall to batch mint + refundETH so unused ETH is returned
                    mint_data = pm.functions.mint(mint_params)._encode_transaction_data()
                    refund_data = pm.functions.refundETH()._encode_transaction_data()
                    call_bytes = []
                    for c in [mint_data, refund_data]:
                        call_bytes.append(bytes.fromhex(c[2:]) if isinstance(c, str) else c)
                    return pm.functions.multicall(call_bytes).build_transaction({
                        "from": self._signer.address,
                        "value": native_value,
                        "gas": global_config.evm.lp_gas_limit,
                        "nonce": self._get_nonce(),
                        "chainId": self._chain_id,
                    })
                else:
                    return pm.functions.mint(mint_params).build_transaction({
                        "from": self._signer.address,
                        "value": 0,
                        "gas": global_config.evm.lp_gas_limit,
                        "nonce": self._get_nonce(),
                        "chainId": self._chain_id,
                    })

            return self._execute_with_retry("open_position_v3", build_tx)

        except Exception as e:
            logger.error(f"Failed to open V3 position: {e}")
            return TxResult.failed(str(e))

    def _open_position_v4(
        self,
        pool: Pool,
        price_range: PriceRange,
        amount0: Optional[Decimal],
        amount1: Optional[Decimal],
        slippage_bps: int,
    ) -> TxResult:
        """Open V4 position using modifyLiquidities"""
        if not self._signer:
            raise SignerError.not_configured()

        if amount0 is None and amount1 is None:
            raise ConfigurationError.missing("amount0 or amount1")

        try:
            # Calculate ticks from price range
            tick_lower, tick_upper = self._price_range_to_ticks(pool, price_range)

            # Get pool key from metadata
            pool_key = pool.metadata.get("pool_key")
            if not pool_key:
                return TxResult.failed("Pool key not found in metadata - use get_pool with version='v4'")

            # Convert amounts to raw
            decimals0 = pool.token0.decimals
            decimals1 = pool.token1.decimals
            raw_amount0 = int((amount0 or Decimal(0)) * Decimal(10 ** decimals0))
            raw_amount1 = int((amount1 or Decimal(0)) * Decimal(10 ** decimals1))

            # Calculate liquidity from amounts using proper V3/V4 math
            sqrt_price_x96 = pool.sqrt_price_x64 or 0
            liquidity = self._calculate_liquidity(
                sqrt_price_x96, tick_lower, tick_upper, raw_amount0, raw_amount1
            )

            # Calculate max amounts with slippage buffer
            slippage_factor = Decimal(10000 + slippage_bps) / Decimal(10000)
            amount0_max = int(Decimal(raw_amount0) * slippage_factor) if raw_amount0 > 0 else 2**128 - 1
            amount1_max = int(Decimal(raw_amount1) * slippage_factor) if raw_amount1 > 0 else 2**128 - 1

            # Build actions for minting position
            actions = [V4Actions.MINT_POSITION, V4Actions.SETTLE_PAIR]
            params = [
                V4ActionEncoder.encode_mint_position(
                    pool_key=pool_key,
                    tick_lower=tick_lower,
                    tick_upper=tick_upper,
                    liquidity=liquidity,
                    amount0_max=amount0_max,
                    amount1_max=amount1_max,
                    recipient=self._signer.address,
                    hook_data=b''
                ),
                V4ActionEncoder.encode_settle_pair(pool.token0.mint, pool.token1.mint),
            ]

            unlock_data = V4ActionEncoder.build_unlock_data(actions, params)

            # Handle token approvals and native value
            token0_addr = pool.token0.mint
            token1_addr = pool.token1.mint
            native_value = 0
            token0_is_native = self._is_v4_native(token0_addr)
            token1_is_native = self._is_v4_native(token1_addr)

            # Handle native ETH value
            if token0_is_native and raw_amount0 > 0:
                native_value += raw_amount0
            if token1_is_native and raw_amount1 > 0:
                native_value += raw_amount1

            # Approve non-native tokens (must approve even in mixed pairs)
            if not token0_is_native and raw_amount0 > 0:
                approval = self._ensure_approval(token0_addr, raw_amount0, self.v4_position_manager_address)
                if approval and not approval.is_success:
                    return approval
            if not token1_is_native and raw_amount1 > 0:
                approval = self._ensure_approval(token1_addr, raw_amount1, self.v4_position_manager_address)
                if approval and not approval.is_success:
                    return approval

            def build_tx():
                deadline = int(time.time()) + global_config.evm.tx_deadline_seconds
                pm = self._get_v4_position_manager()
                return pm.functions.modifyLiquidities(unlock_data, deadline).build_transaction({
                    "from": self._signer.address,
                    "value": native_value,
                    "gas": global_config.evm.lp_gas_limit,
                    "nonce": self._get_nonce(),
                    "chainId": self._chain_id,
                })

            return self._execute_with_retry("open_position_v4", build_tx)

        except Exception as e:
            logger.error(f"Failed to open V4 position: {e}")
            return TxResult.failed(str(e))

    def add_liquidity(
        self,
        position: Position,
        amount0: Decimal,
        amount1: Decimal,
        slippage_bps: Optional[int] = None,
    ) -> TxResult:
        """Add liquidity to existing position"""
        # Use config default if not specified
        if slippage_bps is None:
            slippage_bps = global_config.trading.default_lp_slippage_bps

        if self._is_v4_pool(position.pool):
            return self._add_liquidity_v4(position, amount0, amount1, slippage_bps)
        return self._add_liquidity_v3(position, amount0, amount1, slippage_bps)

    def _add_liquidity_v4(
        self,
        position: Position,
        amount0: Decimal,
        amount1: Decimal,
        slippage_bps: int,
    ) -> TxResult:
        """Add liquidity to V4 position using modifyLiquidities"""
        if not self._signer:
            raise SignerError.not_configured()

        try:
            token_id = int(position.id)
            pool = position.pool

            # Convert amounts to raw
            decimals0 = pool.token0.decimals
            decimals1 = pool.token1.decimals
            raw_amount0 = int(amount0 * Decimal(10 ** decimals0))
            raw_amount1 = int(amount1 * Decimal(10 ** decimals1))

            # Calculate liquidity from amounts using proper V3/V4 math
            sqrt_price_x96 = pool.sqrt_price_x64 or 0
            liquidity_delta = self._calculate_liquidity(
                sqrt_price_x96, position.tick_lower, position.tick_upper, raw_amount0, raw_amount1
            )

            # Calculate max amounts with slippage buffer
            slippage_factor = Decimal(10000 + slippage_bps) / Decimal(10000)
            amount0_max = int(Decimal(raw_amount0) * slippage_factor)
            amount1_max = int(Decimal(raw_amount1) * slippage_factor)

            # Build actions
            actions = [V4Actions.INCREASE_LIQUIDITY, V4Actions.SETTLE_PAIR]
            params = [
                V4ActionEncoder.encode_increase_liquidity(
                    token_id=token_id,
                    liquidity=liquidity_delta,
                    amount0_max=amount0_max,
                    amount1_max=amount1_max,
                    hook_data=b''
                ),
                V4ActionEncoder.encode_settle_pair(pool.token0.mint, pool.token1.mint),
            ]

            unlock_data = V4ActionEncoder.build_unlock_data(actions, params)

            # Handle token approvals and native value
            token0_addr = pool.token0.mint
            token1_addr = pool.token1.mint
            native_value = 0
            token0_is_native = self._is_v4_native(token0_addr)
            token1_is_native = self._is_v4_native(token1_addr)

            # Handle native ETH value
            if token0_is_native and raw_amount0 > 0:
                native_value += raw_amount0
            if token1_is_native and raw_amount1 > 0:
                native_value += raw_amount1

            # Approve non-native tokens (must approve even in mixed pairs)
            if not token0_is_native and raw_amount0 > 0:
                approval = self._ensure_approval(token0_addr, raw_amount0, self.v4_position_manager_address)
                if approval and not approval.is_success:
                    return approval
            if not token1_is_native and raw_amount1 > 0:
                approval = self._ensure_approval(token1_addr, raw_amount1, self.v4_position_manager_address)
                if approval and not approval.is_success:
                    return approval

            def build_tx():
                deadline = int(time.time()) + global_config.evm.tx_deadline_seconds
                pm = self._get_v4_position_manager()
                return pm.functions.modifyLiquidities(unlock_data, deadline).build_transaction({
                    "from": self._signer.address,
                    "value": native_value,
                    "gas": global_config.evm.lp_gas_limit,
                    "nonce": self._get_nonce(),
                    "chainId": self._chain_id,
                })

            return self._execute_with_retry("add_liquidity_v4", build_tx)

        except Exception as e:
            logger.error(f"Failed to add V4 liquidity: {e}")
            return TxResult.failed(str(e))

    def _add_liquidity_v3(
        self,
        position: Position,
        amount0: Decimal,
        amount1: Decimal,
        slippage_bps: int,
    ) -> TxResult:
        """Add liquidity to V3 position"""
        if not self._signer:
            raise SignerError.not_configured()

        try:
            token_id = int(position.id)
            pool = position.pool

            decimals0 = pool.token0.decimals
            decimals1 = pool.token1.decimals
            raw_amount0 = int(amount0 * Decimal(10 ** decimals0))
            raw_amount1 = int(amount1 * Decimal(10 ** decimals1))

            slippage_factor = Decimal(10000 - slippage_bps) / Decimal(10000)
            min_amount0 = int(Decimal(raw_amount0) * slippage_factor)
            min_amount1 = int(Decimal(raw_amount1) * slippage_factor)

            token0_addr = pool.token0.mint
            token1_addr = pool.token1.mint

            native_value = 0
            wrapped_native = get_wrapped_native_address(self._chain_id)
            token0_is_native = token0_addr.lower() == wrapped_native.lower()
            token1_is_native = token1_addr.lower() == wrapped_native.lower()

            # Handle native ETH value (can send ETH for wrapped native tokens)
            if token0_is_native and raw_amount0 > 0:
                native_value += raw_amount0
            if token1_is_native and raw_amount1 > 0:
                native_value += raw_amount1

            # Approve non-native tokens (must approve even in mixed pairs)
            if not token0_is_native and raw_amount0 > 0:
                approval = self._ensure_approval(token0_addr, raw_amount0, self.v3_position_manager_address)
                if approval and not approval.is_success:
                    return approval
            if not token1_is_native and raw_amount1 > 0:
                approval = self._ensure_approval(token1_addr, raw_amount1, self.v3_position_manager_address)
                if approval and not approval.is_success:
                    return approval

            def build_tx():
                deadline = int(time.time()) + global_config.evm.tx_deadline_seconds
                increase_params = (token_id, raw_amount0, raw_amount1, min_amount0, min_amount1, deadline)

                pm = self._get_v3_position_manager()
                return pm.functions.increaseLiquidity(increase_params).build_transaction({
                    "from": self._signer.address,
                    "value": native_value,
                    "gas": global_config.evm.lp_gas_limit,
                    "nonce": self._get_nonce(),
                    "chainId": self._chain_id,
                })

            return self._execute_with_retry("add_liquidity_v3", build_tx)

        except Exception as e:
            logger.error(f"Failed to add liquidity: {e}")
            return TxResult.failed(str(e))

    def remove_liquidity(
        self,
        position: Position,
        percent: float = 100.0,
        slippage_bps: Optional[int] = None,
    ) -> TxResult:
        """Remove liquidity from position"""
        # Use config default if not specified
        if slippage_bps is None:
            slippage_bps = global_config.trading.default_lp_slippage_bps

        if self._is_v4_pool(position.pool):
            return self._remove_liquidity_v4(position, percent, slippage_bps)
        return self._remove_liquidity_v3(position, percent, slippage_bps)

    def _remove_liquidity_v3(self, position: Position, percent: float, slippage_bps: int) -> TxResult:
        """Remove liquidity from V3 position"""
        if not self._signer:
            raise SignerError.not_configured()

        try:
            token_id = int(position.id)
            liquidity_to_remove = int(position.liquidity * percent / 100)

            if liquidity_to_remove == 0:
                return TxResult.skipped("No liquidity to remove")

            # Calculate minimum amounts with slippage protection
            slippage_factor = Decimal(10000 - slippage_bps) / Decimal(10000)
            expected_amount0 = position.amount0 * Decimal(percent) / Decimal(100)
            expected_amount1 = position.amount1 * Decimal(percent) / Decimal(100)
            amount0_min = int(expected_amount0 * slippage_factor * Decimal(10 ** position.pool.token0.decimals))
            amount1_min = int(expected_amount1 * slippage_factor * Decimal(10 ** position.pool.token1.decimals))

            def build_tx():
                deadline = int(time.time()) + global_config.evm.tx_deadline_seconds
                decrease_params = (token_id, liquidity_to_remove, amount0_min, amount1_min, deadline)

                pm = self._get_v3_position_manager()
                return pm.functions.decreaseLiquidity(decrease_params).build_transaction({
                    "from": self._signer.address,
                    "value": 0,
                    "gas": global_config.evm.lp_gas_limit,
                    "nonce": self._get_nonce(),
                    "chainId": self._chain_id,
                })

            return self._execute_with_retry("remove_liquidity_v3", build_tx)

        except Exception as e:
            logger.error(f"Failed to remove liquidity: {e}")
            return TxResult.failed(str(e))

    def _remove_liquidity_v4(self, position: Position, percent: float, slippage_bps: int) -> TxResult:
        """Remove liquidity from V4 position using modifyLiquidities"""
        if not self._signer:
            raise SignerError.not_configured()

        try:
            token_id = int(position.id)
            pool = position.pool

            # Calculate liquidity to remove
            liquidity_to_remove = int(position.liquidity * percent / 100)

            if liquidity_to_remove == 0:
                return TxResult.skipped("No liquidity to remove")

            # Calculate minimum amounts with slippage protection
            slippage_factor = Decimal(10000 - slippage_bps) / Decimal(10000)
            expected_amount0 = position.amount0 * Decimal(percent) / Decimal(100)
            expected_amount1 = position.amount1 * Decimal(percent) / Decimal(100)
            amount0_min = int(expected_amount0 * slippage_factor * Decimal(10 ** pool.token0.decimals))
            amount1_min = int(expected_amount1 * slippage_factor * Decimal(10 ** pool.token1.decimals))

            # Build actions: DECREASE_LIQUIDITY + TAKE_PAIR
            actions = [V4Actions.DECREASE_LIQUIDITY, V4Actions.TAKE_PAIR]
            params = [
                V4ActionEncoder.encode_decrease_liquidity(
                    token_id=token_id,
                    liquidity=liquidity_to_remove,
                    amount0_min=amount0_min,
                    amount1_min=amount1_min,
                    hook_data=b''
                ),
                V4ActionEncoder.encode_take_pair(
                    pool.token0.mint,
                    pool.token1.mint,
                    self._signer.address
                ),
            ]

            unlock_data = V4ActionEncoder.build_unlock_data(actions, params)

            def build_tx():
                deadline = int(time.time()) + global_config.evm.tx_deadline_seconds
                pm = self._get_v4_position_manager()
                return pm.functions.modifyLiquidities(unlock_data, deadline).build_transaction({
                    "from": self._signer.address,
                    "value": 0,
                    "gas": global_config.evm.lp_gas_limit,
                    "nonce": self._get_nonce(),
                    "chainId": self._chain_id,
                })

            return self._execute_with_retry("remove_liquidity_v4", build_tx)

        except Exception as e:
            logger.error(f"Failed to remove V4 liquidity: {e}")
            return TxResult.failed(str(e))

    def claim_fees(self, position: Position) -> TxResult:
        """Collect accumulated fees"""
        if self._is_v4_pool(position.pool):
            return self._claim_fees_v4(position)
        return self._claim_fees_v3(position)

    def _claim_fees_v3(self, position: Position) -> TxResult:
        """Collect fees from V3 position"""
        if not self._signer:
            raise SignerError.not_configured()

        try:
            token_id = int(position.id)
            max_uint128 = 2**128 - 1

            def build_tx():
                collect_params = (
                    token_id,
                    Web3.to_checksum_address(self._signer.address),
                    max_uint128,
                    max_uint128,
                )

                pm = self._get_v3_position_manager()
                return pm.functions.collect(collect_params).build_transaction({
                    "from": self._signer.address,
                    "value": 0,
                    "gas": global_config.evm.lp_gas_limit,
                    "nonce": self._get_nonce(),
                    "chainId": self._chain_id,
                })

            return self._execute_with_retry("claim_fees_v3", build_tx)

        except Exception as e:
            logger.error(f"Failed to claim fees: {e}")
            return TxResult.failed(str(e))

    def _claim_fees_v4(self, position: Position) -> TxResult:
        """
        Collect fees from V4 position using modifyLiquidities.

        In V4, fees are collected by decreasing liquidity with 0 amount,
        which triggers fee collection, then taking the resulting deltas.
        """
        if not self._signer:
            raise SignerError.not_configured()

        try:
            token_id = int(position.id)
            pool = position.pool

            # DECREASE_LIQUIDITY with 0 liquidity collects fees without removing liquidity
            # Then TAKE_PAIR to receive the collected fees
            actions = [V4Actions.DECREASE_LIQUIDITY, V4Actions.TAKE_PAIR]
            params = [
                V4ActionEncoder.encode_decrease_liquidity(
                    token_id=token_id,
                    liquidity=0,  # 0 liquidity = collect fees only
                    amount0_min=0,
                    amount1_min=0,
                    hook_data=b''
                ),
                V4ActionEncoder.encode_take_pair(
                    pool.token0.mint,
                    pool.token1.mint,
                    self._signer.address
                ),
            ]

            unlock_data = V4ActionEncoder.build_unlock_data(actions, params)

            def build_tx():
                deadline = int(time.time()) + global_config.evm.tx_deadline_seconds
                pm = self._get_v4_position_manager()
                return pm.functions.modifyLiquidities(unlock_data, deadline).build_transaction({
                    "from": self._signer.address,
                    "value": 0,
                    "gas": global_config.evm.lp_gas_limit,
                    "nonce": self._get_nonce(),
                    "chainId": self._chain_id,
                })

            return self._execute_with_retry("claim_fees_v4", build_tx)

        except Exception as e:
            logger.error(f"Failed to claim V4 fees: {e}")
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
                    if self._is_v4_pool(pos.pool):
                        result = self._close_position_v4(pos)
                    else:
                        result = self._close_position_v3(pos)
                    results.append(result)
                    if result.is_success:
                        logger.info(f"  Closed: {result.signature}")
                    else:
                        logger.warning(f"  Failed: {result.error}")
                except Exception as e:
                    logger.error(f"  Error closing position {pos.id}: {e}")
                    results.append(TxResult.failed(str(e)))
            return results

        if self._is_v4_pool(position.pool):
            return self._close_position_v4(position)
        return self._close_position_v3(position)

    def _close_position_v3(self, position: Position) -> TxResult:
        """Close V3 position using multicall to batch all operations into a single tx.

        Batches: decreaseLiquidity + collect + (unwrapWETH9 + sweepToken | nothing) + burn
        """
        if not self._signer:
            raise SignerError.not_configured()

        try:
            token_id = int(position.id)
            max_uint128 = 2**128 - 1
            pm = self._get_v3_position_manager()
            wallet = Web3.to_checksum_address(self._signer.address)

            wrapped_native = get_wrapped_native_address(self._chain_id)
            token0_addr = position.pool.token0.mint
            token1_addr = position.pool.token1.mint
            token0_is_weth = token0_addr.lower() == wrapped_native.lower()
            token1_is_weth = token1_addr.lower() == wrapped_native.lower()
            has_weth = token0_is_weth or token1_is_weth

            def build_tx():
                deadline = int(time.time()) + global_config.evm.tx_deadline_seconds
                calls = []

                # 1. Decrease all liquidity
                if position.liquidity > 0:
                    calls.append(
                        pm.functions.decreaseLiquidity(
                            (token_id, position.liquidity, 0, 0, deadline)
                        )._encode_transaction_data()
                    )

                # 2. Collect tokens
                if has_weth:
                    # Collect to Position Manager contract (address(0)) so it can unwrap
                    collect_recipient = "0x0000000000000000000000000000000000000000"
                else:
                    collect_recipient = wallet

                calls.append(
                    pm.functions.collect(
                        (token_id, Web3.to_checksum_address(collect_recipient), max_uint128, max_uint128)
                    )._encode_transaction_data()
                )

                # 3. If WETH involved: unwrap + sweep the other token
                if has_weth:
                    calls.append(
                        pm.functions.unwrapWETH9(0, wallet)._encode_transaction_data()
                    )
                    other_token = token1_addr if token0_is_weth else token0_addr
                    calls.append(
                        pm.functions.sweepToken(
                            Web3.to_checksum_address(other_token), 0, wallet
                        )._encode_transaction_data()
                    )

                # 4. Burn NFT
                calls.append(
                    pm.functions.burn(token_id)._encode_transaction_data()
                )

                # Convert hex strings to bytes for multicall
                call_bytes = []
                for c in calls:
                    call_bytes.append(bytes.fromhex(c[2:]) if isinstance(c, str) else c)

                return pm.functions.multicall(call_bytes).build_transaction({
                    "from": self._signer.address,
                    "value": 0,
                    "gas": global_config.evm.lp_gas_limit,
                    "nonce": self._get_nonce(),
                    "chainId": self._chain_id,
                })

            return self._execute_with_retry("close_position_v3", build_tx)

        except Exception as e:
            logger.error(f"Failed to close position: {e}")
            return TxResult.failed(str(e))

    def _close_position_v4(self, position: Position) -> TxResult:
        """
        Close V4 position using modifyLiquidities.

        This performs all operations atomically:
        1. DECREASE_LIQUIDITY - Remove all liquidity (also collects fees)
        2. TAKE_PAIR - Receive the tokens
        3. BURN_POSITION - Burn the NFT

        In V4, we can batch all these actions in a single transaction.
        """
        if not self._signer:
            raise SignerError.not_configured()

        try:
            token_id = int(position.id)
            pool = position.pool

            # Build actions for atomic close
            actions = []
            params = []

            # Step 1: Decrease all liquidity (also collects fees)
            if position.liquidity > 0:
                actions.append(V4Actions.DECREASE_LIQUIDITY)
                params.append(
                    V4ActionEncoder.encode_decrease_liquidity(
                        token_id=token_id,
                        liquidity=position.liquidity,
                        amount0_min=0,
                        amount1_min=0,
                        hook_data=b''
                    )
                )

            # Step 2: Take the resulting tokens
            actions.append(V4Actions.TAKE_PAIR)
            params.append(
                V4ActionEncoder.encode_take_pair(
                    pool.token0.mint,
                    pool.token1.mint,
                    self._signer.address
                )
            )

            # Step 3: Burn the NFT position
            actions.append(V4Actions.BURN_POSITION)
            params.append(
                V4ActionEncoder.encode_burn_position(
                    token_id=token_id,
                    amount0_min=0,
                    amount1_min=0,
                    hook_data=b''
                )
            )

            unlock_data = V4ActionEncoder.build_unlock_data(actions, params)

            def build_tx():
                deadline = int(time.time()) + global_config.evm.tx_deadline_seconds
                pm = self._get_v4_position_manager()
                return pm.functions.modifyLiquidities(unlock_data, deadline).build_transaction({
                    "from": self._signer.address,
                    "value": 0,
                    "gas": global_config.evm.lp_gas_limit,
                    "nonce": self._get_nonce(),
                    "chainId": self._chain_id,
                })

            v4_result = self._execute_with_retry("close_position_v4", build_tx)
            if not v4_result.is_success:
                return v4_result

            # Unwrap WETH to native ETH if either token is wrapped native.
            # Skip redundant balanceOf check — unwrap directly based on known position.
            wrapped_native = get_wrapped_native_address(self._chain_id)
            if pool.token0.mint.lower() == wrapped_native.lower() or pool.token1.mint.lower() == wrapped_native.lower():
                try:
                    weth_contract = self._get_token_contract(wrapped_native)
                    weth_balance_raw = weth_contract.functions.balanceOf(
                        Web3.to_checksum_address(self._signer.address)
                    ).call()
                    if weth_balance_raw > 0:
                        weth_balance = Decimal(weth_balance_raw) / Decimal(10**18)
                        logger.info(f"Unwrapping {weth_balance} WETH -> ETH...")
                        self.unwrap_native(weth_balance)
                except Exception as e:
                    logger.warning(f"Failed to unwrap WETH after V4 close: {e}")

            return v4_result

        except Exception as e:
            logger.error(f"Failed to close V4 position: {e}")
            return TxResult.failed(str(e))

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _unwrap_if_native(self, position: Position):
        """Unwrap WETH to native ETH if either pool token is wrapped native"""
        wrapped_native = get_wrapped_native_address(self._chain_id)
        token0_is_wrapped = position.pool.token0.mint.lower() == wrapped_native.lower()
        token1_is_wrapped = position.pool.token1.mint.lower() == wrapped_native.lower()

        if token0_is_wrapped or token1_is_wrapped:
            try:
                weth_contract = self._get_token_contract(wrapped_native)
                weth_balance_raw = weth_contract.functions.balanceOf(
                    Web3.to_checksum_address(self._signer.address)
                ).call()

                if weth_balance_raw > 0:
                    weth_balance = Decimal(weth_balance_raw) / Decimal(10**18)
                    logger.info(f"Unwrapping {weth_balance} WETH -> ETH...")
                    self.unwrap_native(weth_balance)
                    logger.info("Unwrap complete")
            except Exception as e:
                logger.warning(f"Failed to unwrap WETH after close: {e}")

    def _price_range_to_ticks(self, pool: Pool, price_range: PriceRange) -> Tuple[int, int]:
        """Convert price range to ticks"""
        tick_spacing = pool.tick_spacing or TICK_SPACING_BY_FEE.get(pool.metadata.get("fee", 3000), 60)
        current_tick = pool.current_tick or 0
        decimals0 = pool.token0.decimals
        decimals1 = pool.token1.decimals

        if price_range.mode == RangeMode.TICK_RANGE:
            tick_lower = int(price_range.lower)
            tick_upper = int(price_range.upper)
        elif price_range.mode == RangeMode.ONE_TICK:
            tick_lower = self._align_tick_to_spacing(current_tick, tick_spacing, round_up=False)
            tick_upper = tick_lower + tick_spacing
        elif price_range.mode in (RangeMode.PERCENT, RangeMode.BPS):
            # For PERCENT mode: lower/upper are already fractions (e.g., -0.01, 0.01 for +/-1%)
            # For BPS mode: lower/upper are already fractions (stored as bps/10000)
            # Use 1 + value to get price factor (lower is negative, upper is positive)
            if price_range.mode == RangeMode.PERCENT:
                lower_factor = Decimal(1) + price_range.lower
                upper_factor = Decimal(1) + price_range.upper
            else:
                lower_factor = Decimal(1) + price_range.lower / Decimal(10000)
                upper_factor = Decimal(1) + price_range.upper / Decimal(10000)

            current_price = pool.price
            price_lower = current_price * lower_factor
            price_upper = current_price * upper_factor

            tick_lower = self.price_to_tick(price_lower, decimals0, decimals1)
            tick_upper = self.price_to_tick(price_upper, decimals0, decimals1)
        elif price_range.mode == RangeMode.ABSOLUTE:
            tick_lower = self.price_to_tick(price_range.lower, decimals0, decimals1)
            tick_upper = self.price_to_tick(price_range.upper, decimals0, decimals1)
        else:
            raise ConfigurationError.invalid("price_range.mode", f"Unsupported: {price_range.mode}")

        tick_lower = self._align_tick_to_spacing(tick_lower, tick_spacing, round_up=False)
        tick_upper = self._align_tick_to_spacing(tick_upper, tick_spacing, round_up=True)

        tick_lower = max(MIN_TICK, tick_lower)
        tick_upper = min(MAX_TICK, tick_upper)

        if tick_lower >= tick_upper:
            tick_upper = tick_lower + tick_spacing

        return tick_lower, tick_upper

    def _ensure_approval(self, token_address: str, amount: int, spender: str) -> Optional[TxResult]:
        """Ensure token approval"""
        try:
            token_contract = self._get_token_contract(token_address)
            spender_addr = Web3.to_checksum_address(spender)

            allowance = token_contract.functions.allowance(
                Web3.to_checksum_address(self._signer.address),
                spender_addr,
            ).call()

            if allowance >= amount:
                return None

            logger.info(f"Approving token {token_address}...")

            approve_tx = token_contract.functions.approve(
                spender_addr,
                2**256 - 1,
            ).build_transaction({
                "from": self._signer.address,
                "gas": 70000,
                "nonce": self._get_nonce(),
                "chainId": self._chain_id,
            })

            self._add_gas_price(approve_tx)

            result = self._signer.sign_and_send(self._web3, approve_tx, wait_for_receipt=True, timeout=60)

            if result["status"] == "success":
                return TxResult.success(signature=result["tx_hash"])
            return TxResult.failed(f"Approval failed: {result.get('error')}")

        except Exception as e:
            return TxResult.failed(f"Approval error: {e}")

    def _add_gas_price(self, tx: Dict[str, Any]):
        """Add EIP-1559 gas price with minimum priority fee from config

        Note: web3 v7's build_transaction may auto-add gas params.
        We explicitly set EIP-1559 params and remove legacy gasPrice.
        """
        latest_block = self._web3.eth.get_block("latest")
        base_fee = latest_block.get("baseFeePerGas", 0)
        # Use configurable priority fee (default 0.1 gwei for minimum cost)
        priority_fee_gwei = global_config.uniswap.priority_fee_gwei
        max_priority_fee = self._web3.to_wei(priority_fee_gwei, "gwei")
        max_fee = int(base_fee * global_config.uniswap.base_fee_multiplier) + max_priority_fee
        tx["maxFeePerGas"] = max_fee
        tx["maxPriorityFeePerGas"] = max_priority_fee
        # Remove legacy gasPrice if present (web3 v7 compatibility)
        tx.pop("gasPrice", None)

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
                self._reset_nonce()  # Reset nonce tracker on any error

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

    def _result_to_tx_result(self, result: Dict[str, Any]) -> TxResult:
        """Convert signer result to TxResult"""
        if result["status"] == "success":
            return TxResult.success(signature=result["tx_hash"])
        elif result["status"] == "pending":
            return TxResult(status=TxStatus.PENDING, signature=result.get("tx_hash"))
        return TxResult.failed(error=result.get("error", "Transaction failed"), signature=result.get("tx_hash"))

    def close(self):
        """Cleanup"""
        pass

    def __enter__(self) -> "UniswapAdapter":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __repr__(self) -> str:
        addr = self.address[:10] + "..." if self.address else "None"
        return f"UniswapAdapter(chain={self.chain_name}, address={addr})"
