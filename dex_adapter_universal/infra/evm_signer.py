"""
EVM Transaction Signer using web3.py

Provides local signing for Ethereum and BSC transactions.
Only supports local private key signing (no remote signer).
Includes thread-safe nonce management for parallel transactions.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Optional, Dict, Any, Tuple

try:
    from web3 import Web3
    from eth_account import Account
    from eth_account.signers.local import LocalAccount
    # web3 v6+ renamed geth_poa_middleware to ExtraDataToPOAMiddleware
    try:
        from web3.middleware import ExtraDataToPOAMiddleware as geth_poa_middleware
    except ImportError:
        from web3.middleware import geth_poa_middleware
    _HAS_WEB3 = True
except ImportError:
    Web3 = None
    Account = None
    LocalAccount = None
    geth_poa_middleware = None
    _HAS_WEB3 = False

from ..errors import SignerError, ConfigurationError

logger = logging.getLogger(__name__)


class NonceManager:
    """
    Thread-safe nonce manager for EVM transactions.

    Prevents nonce collisions when sending parallel transactions by:
    1. Keeping track of pending nonces locally
    2. Using a lock to prevent race conditions
    3. Syncing with the chain when needed

    Usage:
        nonce_mgr = NonceManager()
        nonce = nonce_mgr.get_nonce(web3, address)  # Thread-safe
        # ... send transaction ...
        nonce_mgr.confirm_nonce(address, nonce)  # On success
        # or
        nonce_mgr.release_nonce(address, nonce)  # On failure
    """

    def __init__(self):
        self._lock = threading.Lock()
        # Track pending nonces per address: {address: next_nonce}
        self._pending_nonces: Dict[str, int] = {}
        # Track in-flight nonces to detect gaps: {address: set of pending nonces}
        self._in_flight: Dict[str, set] = {}

    def get_nonce(self, web3: "Web3", address: str) -> int:
        """
        Get the next available nonce for an address (thread-safe).

        Args:
            web3: Web3 instance
            address: Wallet address

        Returns:
            Next nonce to use
        """
        address = address.lower()

        with self._lock:
            # Get on-chain nonce (includes pending in mempool)
            chain_nonce = web3.eth.get_transaction_count(address, "pending")

            # Get our tracked pending nonce
            tracked_nonce = self._pending_nonces.get(address, chain_nonce)

            # Use the higher of chain nonce or tracked nonce
            # This handles cases where transactions were sent outside this manager
            next_nonce = max(chain_nonce, tracked_nonce)

            # Update tracked nonce for next call
            self._pending_nonces[address] = next_nonce + 1

            # Track in-flight nonce
            if address not in self._in_flight:
                self._in_flight[address] = set()
            self._in_flight[address].add(next_nonce)

            logger.debug(
                f"NonceManager: address={address[:10]}... "
                f"chain={chain_nonce} tracked={tracked_nonce} assigned={next_nonce}"
            )

            return next_nonce

    def confirm_nonce(self, address: str, nonce: int) -> None:
        """
        Confirm a nonce was successfully used (transaction confirmed).

        Args:
            address: Wallet address
            nonce: Nonce that was confirmed
        """
        address = address.lower()

        with self._lock:
            if address in self._in_flight:
                self._in_flight[address].discard(nonce)

    def release_nonce(self, address: str, nonce: int) -> None:
        """
        Release a nonce that failed to be used (transaction failed before broadcast).

        This allows the nonce to be reused by a subsequent transaction.

        Args:
            address: Wallet address
            nonce: Nonce to release
        """
        address = address.lower()

        with self._lock:
            if address in self._in_flight:
                self._in_flight[address].discard(nonce)

            # If this was the highest pending nonce, we can reuse it
            current_pending = self._pending_nonces.get(address, 0)
            if nonce == current_pending - 1:
                self._pending_nonces[address] = nonce
                logger.debug(f"NonceManager: released nonce {nonce} for {address[:10]}...")

    def reset(self, address: Optional[str] = None) -> None:
        """
        Reset nonce tracking, forcing re-sync with chain.

        Args:
            address: Address to reset. If None, resets all addresses.
        """
        with self._lock:
            if address:
                address = address.lower()
                self._pending_nonces.pop(address, None)
                self._in_flight.pop(address, None)
            else:
                self._pending_nonces.clear()
                self._in_flight.clear()


# Global nonce manager instance (shared across all EVMSigner instances)
_nonce_manager = NonceManager()


def get_nonce_manager() -> NonceManager:
    """Get the global nonce manager instance."""
    return _nonce_manager


class EVMSigner:
    """
    Local EVM signer using web3.py

    Provides transaction signing for Ethereum and BSC chains
    using a local private key.

    Usage:
        # From private key
        signer = EVMSigner.from_private_key("0x...")

        # From environment variable
        signer = EVMSigner.from_env()

        # Sign and send transaction
        result = signer.sign_and_send(web3, tx_dict)
    """

    def __init__(self, account: "LocalAccount"):
        """
        Initialize with eth_account LocalAccount

        Args:
            account: LocalAccount from eth_account
        """
        if not _HAS_WEB3:
            raise RuntimeError(
                "web3 and eth-account are required for EVMSigner. "
                "Install with: pip install web3 eth-account"
            )

        self._account = account

    @property
    def address(self) -> str:
        """Get wallet address (checksummed)"""
        return self._account.address

    @property
    def pubkey(self) -> str:
        """Get public key (alias for address on EVM)"""
        return self._account.address

    def sign_transaction(self, tx_dict: Dict[str, Any]) -> Tuple[bytes, str]:
        """
        Sign a transaction

        Args:
            tx_dict: Transaction dictionary with to, data, value, gas, gasPrice, nonce, chainId

        Returns:
            (raw_tx_bytes, tx_hash_hex)
        """
        signed = self._account.sign_transaction(tx_dict)
        return signed.raw_transaction, signed.hash.hex()

    def sign_message(self, message: bytes) -> bytes:
        """
        Sign a raw message

        Args:
            message: Message bytes to sign

        Returns:
            Signature bytes
        """
        from eth_account.messages import encode_defunct
        signable = encode_defunct(message)
        signed = self._account.sign_message(signable)
        return signed.signature

    def sign_and_send(
        self,
        web3: "Web3",
        tx_dict: Dict[str, Any],
        wait_for_receipt: bool = True,
        timeout: int = 120,
    ) -> Dict[str, Any]:
        """
        Sign and send transaction with thread-safe nonce management.

        Args:
            web3: Web3 instance connected to RPC
            tx_dict: Transaction dictionary
            wait_for_receipt: Wait for transaction receipt
            timeout: Timeout in seconds for receipt

        Returns:
            Dict with status, tx_hash, and optionally receipt
        """
        nonce = None
        nonce_from_manager = False

        try:
            # Ensure required fields
            if "nonce" not in tx_dict:
                # Use thread-safe nonce manager
                nonce = _nonce_manager.get_nonce(web3, self.address)
                tx_dict["nonce"] = nonce
                nonce_from_manager = True
            else:
                nonce = tx_dict["nonce"]

            if "chainId" not in tx_dict:
                tx_dict["chainId"] = web3.eth.chain_id

            # Sign transaction
            signed = self._account.sign_transaction(tx_dict)

            # Send transaction
            tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction)

            if wait_for_receipt:
                receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)

                # Confirm nonce was used successfully
                if nonce_from_manager:
                    _nonce_manager.confirm_nonce(self.address, nonce)

                return {
                    "status": "success" if receipt["status"] == 1 else "failed",
                    "tx_hash": tx_hash.hex(),
                    "block_number": receipt["blockNumber"],
                    "gas_used": receipt["gasUsed"],
                    "effective_gas_price": receipt.get("effectiveGasPrice", 0),
                    "receipt": dict(receipt),
                }

            # For pending transactions, nonce is considered used
            if nonce_from_manager:
                _nonce_manager.confirm_nonce(self.address, nonce)

            return {
                "status": "pending",
                "tx_hash": tx_hash.hex(),
            }

        except Exception as e:
            # Release nonce if transaction failed before being sent
            # Note: If tx was sent but failed on-chain, nonce is still consumed
            error_str = str(e).lower()
            is_pre_send_error = any(keyword in error_str for keyword in [
                "nonce too low",  # Already used
                "replacement transaction",  # Replacing existing
                "insufficient funds",  # Can't pay gas
                "gas too low",  # Invalid gas
                "invalid sender",  # Bad signature
            ])

            if nonce_from_manager and is_pre_send_error:
                _nonce_manager.release_nonce(self.address, nonce)

            logger.error(f"Transaction failed: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "tx_hash": None,
            }

    @classmethod
    def from_private_key(cls, private_key: str) -> "EVMSigner":
        """
        Create signer from private key

        Args:
            private_key: Hex-encoded private key (with or without 0x prefix)

        Returns:
            EVMSigner instance
        """
        if not _HAS_WEB3:
            raise RuntimeError("web3 and eth-account are required")

        # Ensure 0x prefix
        if not private_key.startswith("0x"):
            private_key = "0x" + private_key

        account = Account.from_key(private_key)
        return cls(account)

    @classmethod
    def from_env(cls, env_var: str = "EVM_PRIVATE_KEY") -> "EVMSigner":
        """
        Create signer from environment variable

        Args:
            env_var: Name of environment variable containing private key

        Returns:
            EVMSigner instance

        Raises:
            SignerError: If environment variable is not set
        """
        private_key = os.getenv(env_var, "")
        if not private_key:
            raise SignerError.not_configured()

        return cls.from_private_key(private_key)

    @classmethod
    def from_keystore(
        cls,
        keystore_path: str,
        password: str,
    ) -> "EVMSigner":
        """
        Create signer from encrypted keystore file

        Args:
            keystore_path: Path to keystore JSON file
            password: Password to decrypt keystore

        Returns:
            EVMSigner instance
        """
        if not _HAS_WEB3:
            raise RuntimeError("web3 and eth-account are required")

        with open(keystore_path, "r") as f:
            keystore = f.read()

        private_key = Account.decrypt(keystore, password)
        account = Account.from_key(private_key)
        return cls(account)

    def __repr__(self) -> str:
        return f"EVMSigner(address={self.address})"


def create_web3(
    rpc_url: str,
    chain_id: Optional[int] = None,
    timeout: int = 30,
) -> "Web3":
    """
    Create Web3 instance for a chain

    Args:
        rpc_url: RPC endpoint URL
        chain_id: Chain ID (1 for ETH, 56 for BSC). If None, will detect from RPC.
        timeout: Request timeout in seconds

    Returns:
        Configured Web3 instance
    """
    if not _HAS_WEB3:
        raise RuntimeError("web3 is required. Install with: pip install web3")

    from web3 import HTTPProvider

    # Create provider with timeout
    provider = HTTPProvider(
        rpc_url,
        request_kwargs={"timeout": timeout},
    )

    web3 = Web3(provider)

    # Detect chain ID if not provided
    if chain_id is None:
        try:
            chain_id = web3.eth.chain_id
        except Exception as e:
            logging.getLogger(__name__).warning(
                f"Failed to detect chain ID from RPC, defaulting to 1 (ETH): {e}"
            )
            chain_id = 1  # Default to ETH

    # Add PoA middleware for BSC and other PoA chains
    # BSC uses Proof of Staked Authority
    if chain_id in (56, 97):  # BSC mainnet and testnet
        web3.middleware_onion.inject(geth_poa_middleware, layer=0)

    return web3


def create_evm_signer(
    private_key: Optional[str] = None,
    keystore_path: Optional[str] = None,
    keystore_password: Optional[str] = None,
) -> EVMSigner:
    """
    Create EVM signer based on configuration

    Priority:
    1. private_key: Use provided private key
    2. keystore_path + keystore_password: Load from keystore file
    3. EVM_PRIVATE_KEY environment variable

    Args:
        private_key: Optional hex-encoded private key
        keystore_path: Optional path to keystore file
        keystore_password: Password for keystore file

    Returns:
        EVMSigner instance

    Raises:
        SignerError: If no valid signer configuration found
    """
    # Option 1: Direct private key
    if private_key is not None:
        return EVMSigner.from_private_key(private_key)

    # Option 2: Keystore file
    if keystore_path is not None and keystore_password is not None:
        return EVMSigner.from_keystore(keystore_path, keystore_password)

    # Option 3: Environment variable
    env_key = os.getenv("EVM_PRIVATE_KEY", "")
    if env_key:
        return EVMSigner.from_private_key(env_key)

    raise SignerError.not_configured()


def get_balance(
    web3: "Web3",
    address: str,
    token_address: Optional[str] = None,
) -> int:
    """
    Get balance for an address

    Args:
        web3: Web3 instance
        address: Wallet address
        token_address: Optional ERC20 token address. If None, returns native balance.

    Returns:
        Balance in smallest units (wei for ETH/BNB, raw units for tokens)
    """
    from ..types.evm_tokens import NATIVE_TOKEN_ADDRESS, is_native_token

    if token_address is None or is_native_token(token_address):
        # Native balance
        return web3.eth.get_balance(address)

    # ERC20 balance
    erc20_abi = [
        {
            "constant": True,
            "inputs": [{"name": "_owner", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"name": "balance", "type": "uint256"}],
            "type": "function",
        }
    ]

    contract = web3.eth.contract(
        address=Web3.to_checksum_address(token_address),
        abi=erc20_abi,
    )

    return contract.functions.balanceOf(Web3.to_checksum_address(address)).call()


def get_token_info(
    web3: "Web3",
    token_address: str,
) -> Dict[str, Any]:
    """
    Get token information (symbol, decimals, name)

    Args:
        web3: Web3 instance
        token_address: Token contract address

    Returns:
        Dict with symbol, decimals, name
    """
    erc20_abi = [
        {
            "constant": True,
            "inputs": [],
            "name": "symbol",
            "outputs": [{"name": "", "type": "string"}],
            "type": "function",
        },
        {
            "constant": True,
            "inputs": [],
            "name": "decimals",
            "outputs": [{"name": "", "type": "uint8"}],
            "type": "function",
        },
        {
            "constant": True,
            "inputs": [],
            "name": "name",
            "outputs": [{"name": "", "type": "string"}],
            "type": "function",
        },
    ]

    contract = web3.eth.contract(
        address=Web3.to_checksum_address(token_address),
        abi=erc20_abi,
    )

    try:
        symbol = contract.functions.symbol().call()
    except Exception:
        symbol = "UNKNOWN"

    try:
        decimals = contract.functions.decimals().call()
    except Exception:
        decimals = 18

    try:
        name = contract.functions.name().call()
    except Exception:
        name = ""

    return {
        "symbol": symbol,
        "decimals": decimals,
        "name": name,
        "address": token_address,
    }
