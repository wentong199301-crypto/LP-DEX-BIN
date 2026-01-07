"""
EVM Token Registry for ETH and BSC chains

Provides token address mappings and decimals for common tokens on Ethereum and BSC.
Used by the 1inch adapter for token resolution.
"""

from typing import Dict, Optional
from enum import Enum
from dataclasses import dataclass

from ..errors import ConfigurationError


class EVMChain(Enum):
    """Supported EVM chains"""
    ETH = 1
    BSC = 56


@dataclass(frozen=True)
class EVMToken:
    """EVM token information"""
    address: str
    symbol: str
    decimals: int
    name: str = ""
    chain_id: int = 1

    def __str__(self) -> str:
        return self.symbol


# Native token address (use this for native ETH/BNB in 1inch API)
NATIVE_TOKEN_ADDRESS = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"


# =============================================================================
# Ethereum Mainnet Tokens (Chain ID: 1)
# =============================================================================

ETH_TOKEN_ADDRESSES: Dict[str, str] = {
    # Native
    "ETH": NATIVE_TOKEN_ADDRESS,
    "WETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",

    # Stablecoins
    "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
    "DAI": "0x6B175474E89094C44Da98b954EedeaC495271d0F",
    "FRAX": "0x853d955aCEf822Db058eb8505911ED77F175b99e",
    "LUSD": "0x5f98805A4E8be255a32880FDeC7F6728C6568bA0",

    # Major tokens
    "WBTC": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",
    "LINK": "0x514910771AF9Ca656af840dff83E8264EcF986CA",
    "UNI": "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984",
    "AAVE": "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9",
    "MKR": "0x9f8F72aA9304c8B593d555F12eF6589cC3A579A2",
    "SNX": "0xC011a73ee8576Fb46F5E1c5751cA3B9Fe0af2a6F",
    "CRV": "0xD533a949740bb3306d119CC777fa900bA034cd52",
    "LDO": "0x5A98FcBEA516Cf06857215779Fd812CA3beF1B32",
    "RPL": "0xD33526068D116cE69F19A9ee46F0bd304F21A51f",

    # Meme tokens
    "SHIB": "0x95aD61b0a150d79219dCF64E1E6Cc01f0B64C4cE",
    "PEPE": "0x6982508145454Ce325dDbE47a25d4ec3d2311933",

    # L2 tokens
    "MATIC": "0x7D1AfA7B718fb893dB30A3aBc0Cfc608AaCfeBB0",
    "ARB": "0xB50721BCf8d664c30412Cfbc6cf7a15145234ad1",
    "OP": "0x4200000000000000000000000000000000000042",

    # Liquid staking
    "STETH": "0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84",
    "RETH": "0xae78736Cd615f374D3085123A210448E74Fc6393",
    "CBETH": "0xBe9895146f7AF43049ca1c1AE358B0541Ea49704",
}

ETH_TOKEN_DECIMALS: Dict[str, int] = {
    "ETH": 18,
    "WETH": 18,
    "USDC": 6,
    "USDT": 6,
    "DAI": 18,
    "FRAX": 18,
    "LUSD": 18,
    "WBTC": 8,
    "LINK": 18,
    "UNI": 18,
    "AAVE": 18,
    "MKR": 18,
    "SNX": 18,
    "CRV": 18,
    "LDO": 18,
    "RPL": 18,
    "SHIB": 18,
    "PEPE": 18,
    "MATIC": 18,
    "ARB": 18,
    "OP": 18,
    "STETH": 18,
    "RETH": 18,
    "CBETH": 18,
}


# =============================================================================
# BSC Mainnet Tokens (Chain ID: 56)
# =============================================================================

BSC_TOKEN_ADDRESSES: Dict[str, str] = {
    # Native
    "BNB": NATIVE_TOKEN_ADDRESS,
    "WBNB": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",

    # Stablecoins
    "USDC": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
    "USDT": "0x55d398326f99059fF775485246999027B3197955",
    "BUSD": "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56",
    "DAI": "0x1AF3F329e8BE154074D8769D1FFa4eE058B1DBc3",
    "FRAX": "0x90C97F71E18723b0Cf0dfa30ee176Ab653E89F40",
    "TUSD": "0x14016E85a25aeb13065688cAFB43044C2ef86784",

    # Bridged assets
    "ETH": "0x2170Ed0880ac9A755fd29B2688956BD959F933F8",
    "BTCB": "0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c",

    # DeFi tokens
    "CAKE": "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82",
    "XVS": "0xcF6BB5389c92Bdda8a3747Ddb454cB7a64626C63",
    "ALPACA": "0x8F0528cE5eF7B51152A59745bEfDD91D97091d2F",
    "BIFI": "0xCa3F508B8e4Dd382eE878A314789373D80A5190A",

    # Gaming/Metaverse
    "AXS": "0x715D400F88C167884bbCc41C5FeA407ed4D2f8A0",
    "MBOX": "0x3203c9E46cA618C8C1cE5dC67e7e9D75f5da2377",

    # Meme tokens
    "DOGE": "0xbA2aE424d960c26247Dd6c32edC70B295c744C43",
    "FLOKI": "0xfb5B838b6cfEEdC2873aB27866079AC55363D37E",

    # Other
    "DOT": "0x7083609fCE4d1d8Dc0C979AAb8c869Ea2C873402",
    "LINK": "0xF8A0BF9cF54Bb92F17374d9e9A321E6a111a51bD",
    "UNI": "0xBf5140A22578168FD562DCcF235E5D43A02ce9B1",
    "LTC": "0x4338665CBB7B2485A8855A139b75D5e34AB0DB94",
    "XRP": "0x1D2F0da169ceB9fC7B3144628dB156f3F6c60dBE",
    "ADA": "0x3EE2200Efb3400fAbB9AacF31297cBdD1d435D47",
}

BSC_TOKEN_DECIMALS: Dict[str, int] = {
    "BNB": 18,
    "WBNB": 18,
    "USDC": 18,  # BSC USDC has 18 decimals
    "USDT": 18,  # BSC USDT has 18 decimals
    "BUSD": 18,
    "DAI": 18,
    "FRAX": 18,
    "TUSD": 18,
    "ETH": 18,
    "BTCB": 18,
    "CAKE": 18,
    "XVS": 18,
    "ALPACA": 18,
    "BIFI": 18,
    "AXS": 18,
    "MBOX": 18,
    "DOGE": 8,
    "FLOKI": 9,
    "DOT": 18,
    "LINK": 18,
    "UNI": 18,
    "LTC": 18,
    "XRP": 18,
    "ADA": 18,
}


# =============================================================================
# Helper Functions
# =============================================================================

def get_token_addresses(chain_id: int) -> Dict[str, str]:
    """
    Get token address mapping for a chain

    Args:
        chain_id: Chain ID (1 for ETH, 56 for BSC)

    Returns:
        Dict mapping symbol to address
    """
    if chain_id == 1:
        return ETH_TOKEN_ADDRESSES
    elif chain_id == 56:
        return BSC_TOKEN_ADDRESSES
    return {}


def get_token_decimals_map(chain_id: int) -> Dict[str, int]:
    """
    Get token decimals mapping for a chain

    Args:
        chain_id: Chain ID (1 for ETH, 56 for BSC)

    Returns:
        Dict mapping symbol to decimals
    """
    if chain_id == 1:
        return ETH_TOKEN_DECIMALS
    elif chain_id == 56:
        return BSC_TOKEN_DECIMALS
    return {}


def get_token_address(symbol: str, chain_id: int) -> Optional[str]:
    """
    Get token address for a symbol on a specific chain

    Args:
        symbol: Token symbol (e.g., "ETH", "USDC")
        chain_id: Chain ID (1 for ETH, 56 for BSC)

    Returns:
        Token address if found, None otherwise
    """
    addresses = get_token_addresses(chain_id)
    return addresses.get(symbol.upper())


def get_token_decimals(symbol_or_address: str, chain_id: int) -> int:
    """
    Get token decimals for a symbol on a specific chain

    Args:
        symbol_or_address: Token symbol or address
        chain_id: Chain ID (1 for ETH, 56 for BSC)

    Returns:
        Token decimals (defaults to 18 for unknown tokens)
    """
    # If it's a symbol, look up directly
    upper = symbol_or_address.upper()
    decimals_map = get_token_decimals_map(chain_id)

    if upper in decimals_map:
        return decimals_map[upper]

    # For addresses, try to find in our maps
    addresses = get_token_addresses(chain_id)
    for symbol, addr in addresses.items():
        if addr.lower() == symbol_or_address.lower():
            return decimals_map.get(symbol, 18)

    # Default to 18 for unknown tokens (most EVM tokens use 18)
    return 18


def resolve_token_address(token: str, chain_id: int) -> str:
    """
    Resolve token symbol or address to address

    Args:
        token: Token symbol (e.g., "ETH", "USDC") or address (0x...)
        chain_id: Chain ID (1 for ETH, 56 for BSC)

    Returns:
        Token address

    Raises:
        ValueError: If token symbol is unknown and not an address
    """
    # If already an address (starts with 0x and is 42 chars), return as-is
    if token.startswith("0x") and len(token) == 42:
        return token

    # Look up symbol
    address = get_token_address(token, chain_id)
    if address:
        return address

    raise ConfigurationError.invalid("token", f"Unknown token: {token} on chain {chain_id}")


def is_native_token(address: str) -> bool:
    """
    Check if address is the native token address

    Args:
        address: Token address

    Returns:
        True if native token (ETH/BNB)
    """
    return address.lower() == NATIVE_TOKEN_ADDRESS.lower()


def get_native_symbol(chain_id: int) -> str:
    """
    Get native token symbol for a chain

    Args:
        chain_id: Chain ID

    Returns:
        Native token symbol ("ETH" or "BNB")
    """
    if chain_id == 1:
        return "ETH"
    elif chain_id == 56:
        return "BNB"
    return "ETH"


def get_wrapped_native_address(chain_id: int) -> str:
    """
    Get wrapped native token address for a chain

    Args:
        chain_id: Chain ID

    Returns:
        Wrapped native token address (WETH or WBNB)
    """
    if chain_id == 1:
        return ETH_TOKEN_ADDRESSES["WETH"]
    elif chain_id == 56:
        return BSC_TOKEN_ADDRESSES["WBNB"]
    return ETH_TOKEN_ADDRESSES["WETH"]


def get_token_symbol(address: str, chain_id: int) -> Optional[str]:
    """
    Get token symbol from address

    Args:
        address: Token address
        chain_id: Chain ID

    Returns:
        Token symbol or None if not found
    """
    address_lower = address.lower()

    # Check ETH tokens
    if chain_id == 1:
        for symbol, addr in ETH_TOKEN_ADDRESSES.items():
            if addr.lower() == address_lower:
                return symbol

    # Check BSC tokens
    elif chain_id == 56:
        for symbol, addr in BSC_TOKEN_ADDRESSES.items():
            if addr.lower() == address_lower:
                return symbol

    # Check native token
    if is_native_token(address):
        return get_native_symbol(chain_id)

    return None
