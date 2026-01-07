"""
Centralized Token Registry

Provides a single source of truth for token symbol to mint address mappings.
Used across all modules to avoid duplicate definitions.
"""

from typing import Dict, Optional
from .common import Token


# Well-known token mints (keys are uppercase for case-insensitive lookup)
KNOWN_TOKEN_MINTS: Dict[str, str] = {
    # SOL/WSOL
    "SOL": "So11111111111111111111111111111111111111112",
    "WSOL": "So11111111111111111111111111111111111111112",

    # Stablecoins
    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",

    # Popular tokens
    "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
    "JUP": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
    "RAY": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
    "ORCA": "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE",
    "MNDE": "MNDEFzGvMt87ueuHvVU9VcTqsAP5b3fTGPsHuuPA5ey",
    "MSOL": "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",
    "STSOL": "7dHbWXmci3dT8UFYWYZweBLXgycu7Y3iL6trKn1Y7ARj",
    "JITOSOL": "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn",
    "PYTH": "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3",
    "WIF": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
}

# Mint address to decimals mapping
KNOWN_TOKEN_DECIMALS: Dict[str, int] = {
    "So11111111111111111111111111111111111111112": 9,   # SOL/WSOL
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": 6,  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": 6,  # USDT
    "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263": 5,  # BONK
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN": 6,   # JUP
    "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R": 6,  # RAY
    "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE": 6,   # ORCA
    "MNDEFzGvMt87ueuHvVU9VcTqsAP5b3fTGPsHuuPA5ey": 9,   # MNDE
    "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So": 9,   # mSOL
    "7dHbWXmci3dT8UFYWYZweBLXgycu7Y3iL6trKn1Y7ARj": 9,  # stSOL
    "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn": 9,  # jitoSOL
    "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3": 6,  # PYTH
    "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm": 6,  # WIF
}

# Prebuilt Token objects for common tokens
KNOWN_TOKENS: Dict[str, Token] = {
    "SOL": Token(
        mint="So11111111111111111111111111111111111111112",
        symbol="SOL",
        decimals=9,
        name="Wrapped SOL"
    ),
    "WSOL": Token(
        mint="So11111111111111111111111111111111111111112",
        symbol="WSOL",
        decimals=9,
        name="Wrapped SOL"
    ),
    "USDC": Token(
        mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        symbol="USDC",
        decimals=6,
        name="USD Coin"
    ),
    "USDT": Token(
        mint="Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
        symbol="USDT",
        decimals=6,
        name="Tether USD"
    ),
}


def resolve_token_mint(token: str) -> str:
    """
    Resolve token symbol or mint address to mint address

    Args:
        token: Token symbol (e.g., "SOL", "USDC") or mint address

    Returns:
        Mint address
    """
    # If it looks like a mint address (base58, typically 32-44 chars), return as-is
    if len(token) > 30:
        return token

    # Look up symbol in known tokens (case-insensitive)
    upper = token.upper()
    if upper in KNOWN_TOKEN_MINTS:
        return KNOWN_TOKEN_MINTS[upper]

    # Return as-is (might be a short mint address or unknown symbol)
    return token


def get_token_decimals(mint: str) -> Optional[int]:
    """
    Get decimals for a known token mint

    Args:
        mint: Token mint address

    Returns:
        Decimals if known, None otherwise
    """
    return KNOWN_TOKEN_DECIMALS.get(mint)


def get_token(symbol: str) -> Optional[Token]:
    """
    Get a Token object for a known symbol

    Args:
        symbol: Token symbol (case-insensitive)

    Returns:
        Token if known, None otherwise
    """
    return KNOWN_TOKENS.get(symbol.upper())
