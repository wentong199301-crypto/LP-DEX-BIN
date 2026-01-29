"""
Wallet Module

Provides multi-chain balance and token account operations.

Supports:
- Solana: SOL and SPL tokens
- Ethereum: ETH and ERC20 tokens
- BSC: BNB and BEP20 tokens
"""

import logging
from decimal import Decimal
from typing import Dict, List, Optional, Union, TYPE_CHECKING
from dataclasses import dataclass
from enum import Enum

if TYPE_CHECKING:
    from ..client import DexClient

logger = logging.getLogger(__name__)


class Chain(Enum):
    """Supported blockchain networks"""
    SOLANA = "solana"
    ETH = "eth"
    BSC = "bsc"

    @classmethod
    def from_string(cls, value: str) -> "Chain":
        """Convert string to Chain enum (case-insensitive)"""
        value_lower = value.lower()
        if value_lower in ("solana", "sol"):
            return cls.SOLANA
        elif value_lower in ("eth", "ethereum", "1"):
            return cls.ETH
        elif value_lower in ("bsc", "bnb", "56"):
            return cls.BSC
        else:
            from ..errors import ConfigurationError
            raise ConfigurationError.invalid("chain", f"Unknown chain: {value}. Supported: solana/sol, eth, bsc")

    @property
    def chain_id(self) -> Optional[int]:
        """Get EVM chain ID (None for Solana)"""
        if self == Chain.ETH:
            return 1
        elif self == Chain.BSC:
            return 56
        return None

    @property
    def is_evm(self) -> bool:
        """Check if this is an EVM chain"""
        return self in (Chain.ETH, Chain.BSC)

    @property
    def native_token(self) -> str:
        """Get native token symbol"""
        if self == Chain.SOLANA:
            return "SOL"
        elif self == Chain.ETH:
            return "ETH"
        else:  # Chain.BSC
            return "BNB"

    @property
    def aggregator(self) -> str:
        """Get aggregator name for this chain"""
        if self == Chain.SOLANA:
            return "Jupiter"
        return "1inch"


@dataclass(frozen=True)
class TokenAccount:
    """Token account information"""
    address: str
    mint: str
    owner: str
    balance: Decimal
    decimals: int


from ..types.solana_tokens import SOLANA_TOKEN_MINTS, resolve_token_mint


class WalletModule:
    """
    Multi-chain wallet operations module

    Provides:
    - SOL/ETH/BNB balance queries
    - Token balance queries (SPL/ERC20/BEP20)
    - Token account listing (Solana only)

    Usage:
        client = DexClient(rpc_url, keypair)

        # Solana balances
        sol = client.wallet.balance("SOL", chain="sol")
        usdc = client.wallet.balance("USDC", chain="sol")

        # ETH chain balances
        eth = client.wallet.balance("ETH", chain="eth")
        usdc = client.wallet.balance("USDC", chain="eth")

        # BSC chain balances
        bnb = client.wallet.balance("BNB", chain="bsc")
        usdc = client.wallet.balance("USDC", chain="bsc")

        # Get all Solana balances
        balances = client.wallet.balances()
    """

    # Common Solana token addresses (from centralized registry)
    WRAPPED_SOL = SOLANA_TOKEN_MINTS["WSOL"]
    USDC = SOLANA_TOKEN_MINTS["USDC"]
    USDT = SOLANA_TOKEN_MINTS["USDT"]

    def __init__(self, client: "DexClient"):
        """
        Initialize wallet module

        Args:
            client: DexClient instance
        """
        self._client = client
        self._rpc = client.rpc

        # EVM configuration
        self._evm_address: Optional[str] = None

    @property
    def address(self) -> str:
        """Solana wallet address"""
        return self._client.pubkey

    @property
    def evm_address(self) -> Optional[str]:
        """EVM wallet address"""
        return self._evm_address

    def set_evm_address(self, address: str) -> None:
        """
        Set EVM wallet address for balance queries

        Args:
            address: EVM wallet address (0x...)
        """
        self._evm_address = address

    def get_address(self, chain: Union[str, Chain]) -> str:
        """
        Get wallet address for a specific chain

        Args:
            chain: Chain to query (required). Options: "sol", "eth", "bsc"

        Returns:
            Wallet address for the chain
        """
        resolved_chain = self._resolve_chain(chain)

        if resolved_chain == Chain.SOLANA:
            return self.address
        else:
            if not self._evm_address:
                from ..errors import ConfigurationError
                raise ConfigurationError.missing("evm_address (call set_evm_address() first)")
            return self._evm_address

    def _resolve_chain(self, chain: Optional[Union[str, Chain]]) -> Chain:
        """Resolve chain parameter to Chain enum"""
        if chain is None:
            return Chain.SOLANA
        if isinstance(chain, Chain):
            return chain
        return Chain.from_string(chain)

    def _get_web3(self, chain_id: int) -> "Web3":
        """
        Create Web3 instance for a chain

        Args:
            chain_id: EVM chain ID (1 for ETH, 56 for BSC)

        Returns:
            Web3 instance
        """
        from ..config import config
        from ..infra.evm_signer import create_web3
        from ..errors import ConfigurationError

        if chain_id == 1:
            rpc_url = config.oneinch.eth_rpc_url
            if not rpc_url:
                raise ConfigurationError.missing("ETH_RPC_URL")
        elif chain_id == 56:
            rpc_url = config.oneinch.bsc_rpc_url
            if not rpc_url:
                raise ConfigurationError.missing("BSC_RPC_URL")
        else:
            raise ConfigurationError.invalid("chain_id", f"Unsupported chain ID: {chain_id}")

        return create_web3(rpc_url, chain_id)

    def _resolve_mint(self, token: str) -> str:
        """
        Resolve Solana token symbol or mint address to mint address

        Args:
            token: Token symbol (e.g., "SOL", "USDC") or mint address

        Returns:
            Mint address
        """
        return resolve_token_mint(token)

    # =========================================================================
    # Solana Balance Methods
    # =========================================================================

    def _solana_balance(self, token: str) -> Decimal:
        """
        Get Solana token balance by symbol or mint address

        Args:
            token: Token symbol (e.g., "SOL", "USDC", "WSOL") or mint address

        Returns:
            Token balance in UI units
        """
        # Handle native SOL explicitly
        if token.upper() == "SOL":
            lamports = self._rpc.get_balance(self.address)
            return Decimal(lamports) / Decimal(10 ** 9)

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
        total = Decimal(0)
        for account in accounts:
            info = account.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
            token_amount = info.get("tokenAmount", {})
            amount_str = token_amount.get("amount")
            decimals = token_amount.get("decimals", 0)
            if amount_str:
                total += Decimal(amount_str) / Decimal(10 ** decimals)

        return total

    def _solana_balance_raw(self, token: str) -> int:
        """
        Get raw Solana token balance (in smallest units)

        Args:
            token: Token symbol or mint address

        Returns:
            Raw balance (lamports for SOL, smallest units for tokens)
        """
        if token.upper() == "SOL":
            return self._rpc.get_balance(self.address)

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

    # =========================================================================
    # EVM Balance Methods
    # =========================================================================

    def _evm_balance(self, token: str, chain_id: int) -> Decimal:
        """
        Get EVM token balance

        Args:
            token: Token symbol or contract address
            chain_id: EVM chain ID (1 for ETH, 56 for BSC)

        Returns:
            Token balance in UI units
        """
        from ..infra.evm_signer import get_balance
        from ..types.evm_tokens import (
            resolve_token_address,
            get_token_decimals,
            is_native_token,
        )
        from ..errors import ConfigurationError

        if not self._evm_address:
            raise ConfigurationError.missing("evm_address (call set_evm_address() first)")

        web3 = self._get_web3(chain_id)

        # Resolve token to address
        token_address = resolve_token_address(token, chain_id)
        decimals = get_token_decimals(token, chain_id)

        # Get raw balance
        raw_balance = get_balance(
            web3,
            self._evm_address,
            token_address if not is_native_token(token_address) else None,
        )

        return Decimal(raw_balance) / Decimal(10 ** decimals)

    def _evm_balance_raw(self, token: str, chain_id: int) -> int:
        """
        Get raw EVM token balance (in smallest units)

        Args:
            token: Token symbol or contract address
            chain_id: EVM chain ID

        Returns:
            Raw balance (wei for native, smallest units for tokens)
        """
        from ..infra.evm_signer import get_balance
        from ..types.evm_tokens import resolve_token_address, is_native_token
        from ..errors import ConfigurationError

        if not self._evm_address:
            raise ConfigurationError.missing("evm_address (call set_evm_address() first)")

        web3 = self._get_web3(chain_id)

        token_address = resolve_token_address(token, chain_id)

        return get_balance(
            web3,
            self._evm_address,
            token_address if not is_native_token(token_address) else None,
        )

    # =========================================================================
    # Unified Balance Methods
    # =========================================================================

    def balance(self, token: str, chain: Union[str, Chain]) -> Decimal:
        """
        Get token balance on any supported chain

        Args:
            token: Token symbol (e.g., "SOL", "ETH", "BNB", "USDC") or address
            chain: Chain to query (required). Options:
                   - "sol" / "solana"
                   - "eth" / "ethereum"
                   - "bsc" / "bnb"

        Returns:
            Token balance in UI units

        Examples:
            # Solana
            client.wallet.balance("SOL", chain="sol")
            client.wallet.balance("USDC", chain="sol")

            # Ethereum
            client.wallet.balance("ETH", chain="eth")
            client.wallet.balance("USDC", chain="eth")

            # BSC
            client.wallet.balance("BNB", chain="bsc")
            client.wallet.balance("USDC", chain="bsc")
        """
        resolved_chain = self._resolve_chain(chain)

        if resolved_chain == Chain.SOLANA:
            return self._solana_balance(token)
        else:
            return self._evm_balance(token, resolved_chain.chain_id)

    def balance_raw(self, token: str, chain: Union[str, Chain]) -> int:
        """
        Get raw token balance (in smallest units) on any chain

        Args:
            token: Token symbol or address
            chain: Chain to query (required). Options: "sol", "eth", "bsc"

        Returns:
            Raw balance (lamports/wei/smallest units)
        """
        resolved_chain = self._resolve_chain(chain)

        if resolved_chain == Chain.SOLANA:
            return self._solana_balance_raw(token)
        else:
            return self._evm_balance_raw(token, resolved_chain.chain_id)

    # =========================================================================
    # Solana-specific Methods
    # =========================================================================

    def balances(self) -> Dict[str, Decimal]:
        """
        Get all Solana token balances

        Returns:
            Dict mapping mint address to balance.
            Native SOL is included under WRAPPED_SOL mint address.
        """
        balances: Dict[str, Decimal] = {}

        # Add native SOL balance under WRAPPED_SOL key
        lamports = self._rpc.get_balance(self.address)
        balances[self.WRAPPED_SOL] = Decimal(lamports) / Decimal(10 ** 9)

        # Get all token accounts
        accounts = self._rpc.get_token_accounts_by_owner(self.address)

        for account in accounts:
            try:
                info = account.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
                mint = info.get("mint")
                token_amount = info.get("tokenAmount", {})

                amount_str = token_amount.get("amount")
                decimals = token_amount.get("decimals", 0)

                if mint and amount_str:
                    amount = Decimal(amount_str) / Decimal(10 ** decimals)
                    if amount > 0:
                        current = balances.get(mint, Decimal(0))
                        balances[mint] = current + amount
            except (KeyError, TypeError, ValueError) as e:
                logger.warning(f"Skipping token account due to parse error: {e}")
                logger.debug("Token account parse error details", exc_info=True)
                continue

        return balances

    def token_accounts(self) -> List[TokenAccount]:
        """
        List all Solana token accounts

        Returns:
            List of TokenAccount objects
        """
        accounts_list: List[TokenAccount] = []

        accounts = self._rpc.get_token_accounts_by_owner(self.address)

        for account in accounts:
            try:
                pubkey = account.get("pubkey")
                info = account.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})

                mint = info.get("mint")
                owner = info.get("owner")
                token_amount = info.get("tokenAmount", {})

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
            except (KeyError, TypeError, ValueError) as e:
                pubkey = account.get('pubkey', 'unknown')
                logger.warning(f"Skipping token account {pubkey} due to parse error: {e}")
                logger.debug("Token account parse error details", exc_info=True)
                continue

        return accounts_list

    def get_token_account(self, token: str) -> Optional[str]:
        """
        Get Solana token account address for a token

        Args:
            token: Token symbol (e.g., "SOL", "USDC") or mint address

        Returns:
            Token account address or None
        """
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
        Check if wallet has a Solana token account for a token

        Args:
            token: Token symbol (e.g., "SOL", "USDC") or mint address

        Returns:
            True if token account exists
        """
        return self.get_token_account(token) is not None

    def close(self) -> None:
        """No resources to clean up (no caching)"""
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
