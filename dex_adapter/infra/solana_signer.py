"""
Transaction signing abstractions

Provides unified signing interface for local signing with keypair.
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Protocol, Tuple, runtime_checkable

try:
    from solders.keypair import Keypair
    from solders.signature import Signature
    from solders.transaction import VersionedTransaction
except ImportError:
    Keypair = None
    Signature = None
    VersionedTransaction = None

from ..errors import SignerError, ConfigurationError
from ..config import config as global_config

logger = logging.getLogger(__name__)


@runtime_checkable
class Signer(Protocol):
    """
    Protocol for transaction signers

    Implementations must provide:
    - pubkey: The signer's public key (base58)
    - sign(): Sign a message/transaction
    """

    @property
    def pubkey(self) -> str:
        """Signer's public key (base58)"""
        ...

    def sign(self, message: bytes) -> bytes:
        """
        Sign a message

        Args:
            message: Message bytes to sign

        Returns:
            64-byte signature
        """
        ...

    def sign_transaction(self, unsigned_tx: bytes) -> Tuple[bytes, str]:
        """
        Sign a transaction

        Args:
            unsigned_tx: Unsigned transaction bytes

        Returns:
            (signed_tx_bytes, signature_base58)
        """
        ...


class LocalSigner:
    """
    Local signer using Solana keypair

    Usage:
        from solders.keypair import Keypair

        keypair = Keypair()  # or load from file
        signer = LocalSigner(keypair)

        signed_tx, sig = signer.sign_transaction(unsigned_tx_bytes)
    """

    def __init__(self, keypair: "Keypair"):
        """
        Initialize with keypair

        Args:
            keypair: solders.keypair.Keypair instance
        """
        if Keypair is None:
            raise RuntimeError("solders is required for LocalSigner. Install with: pip install solders")

        self._keypair = keypair

    @property
    def pubkey(self) -> str:
        """Public key as base58 string"""
        return str(self._keypair.pubkey())

    def sign(self, message: bytes) -> bytes:
        """Sign message bytes"""
        sig = self._keypair.sign_message(message)
        return bytes(sig)

    def sign_transaction(self, unsigned_tx: bytes) -> Tuple[bytes, str]:
        """
        Sign versioned transaction

        Args:
            unsigned_tx: Unsigned VersionedTransaction bytes

        Returns:
            (signed_tx_bytes, signature_base58)
        """
        if VersionedTransaction is None:
            raise RuntimeError("solders is required")

        # Parse unsigned transaction
        tx = VersionedTransaction.from_bytes(unsigned_tx)
        message = tx.message

        # Get message bytes for signing
        # For MessageV0 (versioned transactions), we need to include the version prefix (0x80)
        # The raw transaction format is: [sig_count][signatures][version_prefix][message]
        # We need to sign [version_prefix][message], not just [message]
        from solders.message import MessageV0
        message_bytes = bytes(message)
        if isinstance(message, MessageV0):
            # Include version prefix 0x80 for MessageV0
            message_bytes = bytes([0x80]) + message_bytes

        signature = self._keypair.sign_message(message_bytes)

        # Build properly signed transaction
        num_required_signatures = message.header.num_required_signatures

        # Find which signer slot corresponds to our public key
        # The first num_required_signatures accounts in account_keys are signers
        from solders.pubkey import Pubkey
        our_pubkey = self._keypair.pubkey()

        # Get account keys from message (handles both legacy and v0 messages)
        if hasattr(message, 'account_keys'):
            # Legacy message
            account_keys = message.account_keys
        else:
            # MessageV0 - static account keys are the signers
            account_keys = message.account_keys

        # Find our position in the signer list
        signer_index = None
        for i in range(num_required_signatures):
            if i < len(account_keys) and account_keys[i] == our_pubkey:
                signer_index = i
                break

        if signer_index is None:
            raise SignerError(
                f"Wallet {our_pubkey} is not in the required signers list. "
                f"Expected signers: {[str(account_keys[i]) for i in range(min(num_required_signatures, len(account_keys)))]}"
            )

        # Create signature list with our signature at the correct position
        # and null signatures for other required signers
        null_sig = Signature.default()
        signatures = [null_sig] * num_required_signatures
        signatures[signer_index] = signature

        # Build the signed transaction
        signed_tx = VersionedTransaction.populate(message, signatures)

        return bytes(signed_tx), str(signature)

    @classmethod
    def from_bytes(cls, secret_key: bytes) -> "LocalSigner":
        """Create signer from secret key bytes (64 bytes)"""
        if Keypair is None:
            raise RuntimeError("solders is required")
        keypair = Keypair.from_bytes(secret_key)
        return cls(keypair)

    @classmethod
    def from_base58(cls, secret_key: str) -> "LocalSigner":
        """Create signer from base58 secret key"""
        if Keypair is None:
            raise RuntimeError("solders is required")
        import base58
        secret_bytes = base58.b58decode(secret_key)
        return cls.from_bytes(secret_bytes)

    @classmethod
    def from_file(cls, path: str) -> "LocalSigner":
        """
        Create signer from keypair file

        Supports:
        - JSON array format (Solana CLI): [1,2,3,...]
        - Raw bytes file (64 bytes)
        """
        import json

        with open(path, "rb") as f:
            content = f.read()

        # Try JSON format first
        try:
            data = json.loads(content.decode("utf-8"))
            if isinstance(data, list):
                secret_bytes = bytes(data)
                return cls.from_bytes(secret_bytes)
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

        # Try raw bytes
        if len(content) == 64:
            return cls.from_bytes(content)

        raise ConfigurationError.invalid("keypair_file", f"Cannot parse keypair file: {path}")


def create_signer(
    keypair: Optional["Keypair"] = None,
    keypair_path: Optional[str] = None,
) -> Signer:
    """
    Create signer based on configuration

    Priority:
    1. keypair: Use LocalSigner with provided keypair
    2. keypair_path: Load keypair from file
    3. Environment: Check SOLANA_KEYPAIR_PATH env var

    Args:
        keypair: Optional Keypair instance
        keypair_path: Optional path to keypair file

    Returns:
        Signer instance

    Raises:
        SignerError: If no valid signer configuration found
    """
    # Option 1: Direct keypair
    if keypair is not None:
        return LocalSigner(keypair)

    # Option 2: Keypair from file
    if keypair_path is not None:
        return LocalSigner.from_file(keypair_path)

    # Option 3: Check global config for keypair path
    if global_config.signer.keypair_path and os.path.isfile(global_config.signer.keypair_path):
        return LocalSigner.from_file(global_config.signer.keypair_path)

    raise SignerError.not_configured()
