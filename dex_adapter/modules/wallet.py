"""
Wallet Module

Provides balance and token account operations.
"""

import logging
from decimal import Decimal
from typing import Dict, List, Optional, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from ..client import DexClient

logger = logging.getLogger(__name__)


@dataclass
class TokenAccount:
    """Token account information"""
    address: str
    mint: str
    owner: str
    balance: Decimal
    decimals: int


from ..types.solana_tokens import KNOWN_TOKEN_MINTS, resolve_token_mint


class WalletModule:
    """
    Wallet operations module

    Provides:
    - SOL balance queries
    - Token balance queries
    - Token account listing

    Usage:
        client = DexClient(rpc_url, keypair)

        # Get SOL balance
        sol = client.wallet.sol_balance()

        # Get token balance (by symbol or mint address)
        usdc = client.wallet.balance("USDC")
        usdc = client.wallet.balance("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")

        # Get all balances
        balances = client.wallet.balances()
    """

    # Common token addresses (from centralized registry)
    WRAPPED_SOL = KNOWN_TOKEN_MINTS["WSOL"]
    USDC = KNOWN_TOKEN_MINTS["USDC"]
    USDT = KNOWN_TOKEN_MINTS["USDT"]

    def __init__(self, client: "DexClient"):
        """
        Initialize wallet module

        Args:
            client: DexClient instance
        """
        self._client = client
        self._rpc = client.rpc

    @property
    def address(self) -> str:
        """Wallet address"""
        return self._client.pubkey

    def _resolve_mint(self, token: str) -> str:
        """
        Resolve token symbol or mint address to mint address

        Args:
            token: Token symbol (e.g., "SOL", "USDC") or mint address

        Returns:
            Mint address
        """
        return resolve_token_mint(token)

    def sol_balance(self) -> Decimal:
        """
        Get native SOL balance

        Returns:
            SOL balance in decimal (e.g., 1.5 SOL)
        """
        lamports = self._rpc.get_balance(self.address)
        return Decimal(lamports) / Decimal(1e9)

    def sol_balance_lamports(self) -> int:
        """Get native SOL balance in lamports"""
        return self._rpc.get_balance(self.address)

    def balance(self, token: str) -> Decimal:
        """
        Get token balance by symbol or mint address

        Args:
            token: Token symbol (e.g., "SOL", "USDC", "WSOL") or mint address
                   "SOL" returns native SOL balance
                   "WSOL" returns wrapped SOL token account balance

        Returns:
            Token balance in UI units
        """
        # Handle native SOL explicitly (before symbol resolution)
        if token.upper() == "SOL":
            return self.sol_balance()

        # Resolve symbol to mint address
        mint = self._resolve_mint(token)

        # Get token accounts for this mint
        accounts = self._rpc.get_token_accounts_by_owner(
            self.address,
            mint=mint,
        )

        if not accounts:
            return Decimal(0)

        # Sum balances from all accounts for this mint
        # Use amount + decimals for precision (uiAmount is a float)
        total = Decimal(0)
        for account in accounts:
            info = account.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
            token_amount = info.get("tokenAmount", {})
            amount_str = token_amount.get("amount")
            decimals = token_amount.get("decimals", 0)
            if amount_str:
                total += Decimal(amount_str) / Decimal(10 ** decimals)

        return total

    def balance_raw(self, token: str) -> int:
        """
        Get raw token balance (in smallest units)

        Args:
            token: Token symbol (e.g., "SOL", "USDC", "WSOL") or mint address
                   "SOL" returns native SOL in lamports
                   "WSOL" returns wrapped SOL token account balance

        Returns:
            Raw balance
        """
        # Handle native SOL explicitly (before symbol resolution)
        if token.upper() == "SOL":
            return self.sol_balance_lamports()

        # Resolve symbol to mint address
        mint = self._resolve_mint(token)

        accounts = self._rpc.get_token_accounts_by_owner(
            self.address,
            mint=mint,
        )

        if not accounts:
            return 0

        total = 0
        for account in accounts:
            info = account.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
            token_amount = info.get("tokenAmount", {})
            amount = token_amount.get("amount")
            if amount:
                total += int(amount)

        return total

    def balances(self) -> Dict[str, Decimal]:
        """
        Get all token balances

        Returns:
            Dict mapping mint address to balance.
            Native SOL is included under WRAPPED_SOL mint address.
            WSOL token accounts are also added to the WRAPPED_SOL entry,
            so the total represents all SOL holdings (native + wrapped).
        """
        balances: Dict[str, Decimal] = {}

        # Add native SOL balance under WRAPPED_SOL key
        balances[self.WRAPPED_SOL] = self.sol_balance()

        # Get all token accounts
        accounts = self._rpc.get_token_accounts_by_owner(self.address)

        for account in accounts:
            try:
                info = account.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
                mint = info.get("mint")
                token_amount = info.get("tokenAmount", {})

                # Use amount + decimals for precision (uiAmount is a float)
                amount_str = token_amount.get("amount")
                decimals = token_amount.get("decimals", 0)

                if mint and amount_str:
                    amount = Decimal(amount_str) / Decimal(10 ** decimals)
                    if amount > 0:
                        # WSOL token accounts are added to native SOL total
                        current = balances.get(mint, Decimal(0))
                        balances[mint] = current + amount
            except Exception as e:
                # Log at warning level for visibility, but continue iterating
                # This can happen with non-standard token formats
                logger.warning(f"Skipping token account due to parse error: {e}")
                logger.debug("Token account parse error details", exc_info=True)
                continue

        return balances

    def token_accounts(self) -> List[TokenAccount]:
        """
        List all token accounts

        Returns:
            List of TokenAccount objects
        """
        accounts_list: List[TokenAccount] = []

        # Get all token accounts
        accounts = self._rpc.get_token_accounts_by_owner(self.address)

        for account in accounts:
            try:
                pubkey = account.get("pubkey")
                info = account.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})

                mint = info.get("mint")
                owner = info.get("owner")
                token_amount = info.get("tokenAmount", {})

                # Use amount + decimals for precision (uiAmount is a float)
                amount_str = token_amount.get("amount", "0")
                decimals = token_amount.get("decimals", 0)
                balance = Decimal(amount_str) / Decimal(10 ** decimals) if amount_str else Decimal(0)

                if pubkey and mint:
                    accounts_list.append(TokenAccount(
                        address=pubkey,
                        mint=mint,
                        owner=owner or self.address,
                        balance=balance,
                        decimals=decimals,
                    ))
            except Exception as e:
                # Log at warning level for visibility, but continue iterating
                pubkey = account.get('pubkey', 'unknown')
                logger.warning(f"Skipping token account {pubkey} due to parse error: {e}")
                logger.debug("Token account parse error details", exc_info=True)
                continue

        return accounts_list

    def get_token_account(self, token: str) -> Optional[str]:
        """
        Get token account address for a token

        Args:
            token: Token symbol (e.g., "SOL", "USDC") or mint address

        Returns:
            Token account address or None
        """
        # Resolve symbol to mint address
        mint = self._resolve_mint(token)

        accounts = self._rpc.get_token_accounts_by_owner(
            self.address,
            mint=mint,
        )

        if accounts:
            return accounts[0].get("pubkey")
        return None

    def has_token_account(self, token: str) -> bool:
        """
        Check if wallet has a token account for a token

        Args:
            token: Token symbol (e.g., "SOL", "USDC") or mint address

        Returns:
            True if token account exists
        """
        return self.get_token_account(token) is not None
