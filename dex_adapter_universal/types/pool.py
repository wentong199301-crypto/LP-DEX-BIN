"""
Pool type definitions and address registry
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, Optional

from .common import Token


@dataclass
class Pool:
    """
    DEX liquidity pool information

    Attributes:
        address: Pool address (base58)
        dex: DEX protocol name ("raydium" | "meteora")
        symbol: Trading pair symbol (e.g., "SOL/USDC")
        token0: Base token (token X in Meteora)
        token1: Quote token (token Y in Meteora)
        price: Current price of token0 in terms of token1
        tvl_usd: Total value locked in USD
        fee_rate: Trading fee rate (e.g., 0.0025 for 0.25%)
        tick_spacing: CLMM tick spacing (Raydium)
        current_tick: Current tick index (Raydium)
        bin_step: DLMM bin step in basis points (Meteora)
        active_bin_id: Current active bin ID (Meteora)
        sqrt_price_x64: Square root price in X64 format (Raydium)
        protocol_fee_rate: Protocol fee portion
        fund_fee_rate: Fund fee portion (Meteora)
    """
    address: str
    dex: str
    symbol: str
    token0: Token
    token1: Token
    price: Decimal
    tvl_usd: Decimal = Decimal(0)
    fee_rate: Decimal = Decimal("0.0025")

    # Raydium CLMM specific
    tick_spacing: Optional[int] = None
    current_tick: Optional[int] = None
    sqrt_price_x64: Optional[int] = None

    # Meteora DLMM specific
    bin_step: Optional[int] = None
    active_bin_id: Optional[int] = None

    # Fee breakdown
    protocol_fee_rate: Decimal = Decimal(0)
    fund_fee_rate: Decimal = Decimal(0)

    # Additional metadata
    metadata: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.symbol} ({self.dex})"

    def __repr__(self) -> str:
        return f"Pool({self.symbol}, {self.dex}, {self.address[:8]}...)"

    @property
    def is_raydium(self) -> bool:
        return self.dex.lower() == "raydium"

    @property
    def is_meteora(self) -> bool:
        return self.dex.lower() == "meteora"

    @property
    def price_1_per_0(self) -> Decimal:
        """Price of token0 in terms of token1"""
        return self.price

    @property
    def price_0_per_1(self) -> Decimal:
        """Price of token1 in terms of token0"""
        if self.price == 0:
            return Decimal(0)
        return Decimal(1) / self.price

    def get_token_by_mint(self, mint: str) -> Optional[Token]:
        """Get token by mint address"""
        if self.token0.mint == mint:
            return self.token0
        if self.token1.mint == mint:
            return self.token1
        return None

    def is_token0(self, mint: str) -> bool:
        """Check if mint is token0"""
        return self.token0.mint == mint

    def is_token1(self, mint: str) -> bool:
        """Check if mint is token1"""
        return self.token1.mint == mint

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dictionary"""
        return {
            "address": self.address,
            "dex": self.dex,
            "symbol": self.symbol,
            "token0": {
                "mint": self.token0.mint,
                "symbol": self.token0.symbol,
                "decimals": self.token0.decimals,
            },
            "token1": {
                "mint": self.token1.mint,
                "symbol": self.token1.symbol,
                "decimals": self.token1.decimals,
            },
            "price": str(self.price),
            "tvl_usd": str(self.tvl_usd),
            "fee_rate": str(self.fee_rate),
            "tick_spacing": self.tick_spacing,
            "current_tick": self.current_tick,
            "bin_step": self.bin_step,
            "active_bin_id": self.active_bin_id,
        }


# =============================================================================
# Pool Address Registry
# =============================================================================

# Raydium CLMM pools (Solana)
RAYDIUM_POOLS: Dict[str, str] = {
    "SOL/USDC": "3ucNos4NbumPLZNWztqGHNFFgkHeRMBQAVemeeomsUxv",
    "SOL/USDT": "3nMFwZXwY1s1M5s8vYAHqd4wGs4iSxXE4LRoUMMYqEgF",
    "SOL/USD1": "AQAGYQsdU853WAKhXM79CgNdoyhrRwXvYHX6qrDyC1FS",
}

# Meteora DLMM pools (Solana)
METEORA_POOLS: Dict[str, str] = {
    "SOL/USDC": "5rCf1DM8LjKTw4YqhnoLcngyZYeNnQqztScTogYHAS6",
    "TRUMP/USDC": "9d9mb8kooFfaD3SctgZtkxQypkshx6ezhbKio89ixyy2",
}

# Uniswap V3 pools (Ethereum mainnet, chain_id=1)
# Keys match on-chain token0/token1 ordering
UNISWAP_POOLS: Dict[str, str] = {
    # 0.3% fee tier pools
    "USDC/WETH": "0x8ad599c3A0ff1De082011EFDDc58f1908eb6e6D8",
    "WETH/USDT": "0x4e68Ccd3E89f51C3074ca5072bbAC773960dFa36",
    "WBTC/WETH": "0xCBCdF9626bC03E24f779434178A73a0B4bad62eD",
}

# PancakeSwap V3 pools (BSC mainnet, chain_id=56)
# Keys match on-chain token0/token1 ordering
PANCAKESWAP_POOLS: Dict[str, str] = {
    "USDT/WBNB": "0x172fcD41E0913e95784454622d1c3724f546f849",
    "USDC/WBNB": "0xf2688Fb5B81049DFB7703aDa5e770543770612C4",
}

# Combined registry mapping DEX name to pools
KNOWN_POOLS: Dict[str, Dict[str, str]] = {
    "raydium": RAYDIUM_POOLS,
    "meteora": METEORA_POOLS,
    "uniswap": UNISWAP_POOLS,
    "pancakeswap": PANCAKESWAP_POOLS,
}


def get_pool_address(dex: str, symbol: str) -> str | None:
    """
    Get pool address for a DEX and trading pair symbol.

    Args:
        dex: DEX name (raydium, meteora, uniswap, pancakeswap)
        symbol: Trading pair symbol (e.g., "SOL/USDC", "ETH/USDC")

    Returns:
        Pool address if found, None otherwise
    """
    dex_pools = KNOWN_POOLS.get(dex.lower())
    if dex_pools is None:
        return None

    # Try exact match
    symbol_upper = symbol.upper()
    if symbol_upper in dex_pools:
        return dex_pools[symbol_upper]

    # Try reversed symbol
    parts = symbol_upper.split("/")
    if len(parts) == 2:
        reversed_symbol = f"{parts[1]}/{parts[0]}"
        if reversed_symbol in dex_pools:
            return dex_pools[reversed_symbol]

    return None


def list_pools(dex: str) -> list[str]:
    """
    List all known pool symbols for a DEX.

    Args:
        dex: DEX name

    Returns:
        List of trading pair symbols
    """
    dex_pools = KNOWN_POOLS.get(dex.lower())
    if dex_pools is None:
        return []
    return list(dex_pools.keys())


def list_dexes() -> list[str]:
    """
    List all DEXes with known pools.

    Returns:
        List of DEX names
    """
    return list(KNOWN_POOLS.keys())
