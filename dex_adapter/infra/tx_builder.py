"""
Transaction builder and sender

Provides utilities for:
- Building versioned transactions
- Adding compute budget instructions
- Sending and confirming transactions
"""

from __future__ import annotations

import base64
import logging
import time
from dataclasses import dataclass, field
from typing import List, Optional, Any, Tuple

try:
    from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price
    from solders.hash import Hash
    from solders.instruction import Instruction, AccountMeta
    from solders.keypair import Keypair
    from solders.message import MessageV0
    from solders.pubkey import Pubkey
    from solders.transaction import VersionedTransaction
except ImportError:
    set_compute_unit_limit = None
    set_compute_unit_price = None
    Hash = None
    Instruction = None
    AccountMeta = None
    Keypair = None
    MessageV0 = None
    Pubkey = None
    VersionedTransaction = None

from .rpc import RpcClient
from .solana_signer import Signer
from ..types import TxResult, TxStatus
from ..errors import TransactionError, RpcError
from ..config import config as global_config

logger = logging.getLogger(__name__)


@dataclass
class TxBuilderConfig:
    """
    Transaction builder runtime configuration

    This is a runtime configuration class that allows per-builder overrides
    while pulling defaults from the global config (dex_adapter.config.TxConfig).

    Usage:
        # Use all defaults from environment
        builder = TxBuilder(rpc, signer)

        # Override specific settings
        config = TxBuilderConfig(compute_units=400_000, skip_preflight=True)
        builder = TxBuilder(rpc, signer, config=config)
    """
    compute_units: int = None
    compute_unit_price: int = None
    skip_preflight: bool = None
    preflight_commitment: str = None
    max_retries: int = None
    confirmation_timeout: float = None
    retry_delay: float = None

    def __post_init__(self):
        """Apply defaults from global config for any unset values"""
        if self.compute_units is None:
            self.compute_units = global_config.tx.compute_units
        if self.compute_unit_price is None:
            self.compute_unit_price = global_config.tx.compute_unit_price
        if self.skip_preflight is None:
            self.skip_preflight = global_config.tx.skip_preflight
        if self.preflight_commitment is None:
            self.preflight_commitment = global_config.tx.preflight_commitment
        if self.max_retries is None:
            self.max_retries = global_config.tx.max_retries
        if self.confirmation_timeout is None:
            self.confirmation_timeout = global_config.tx.confirmation_timeout
        if self.retry_delay is None:
            self.retry_delay = global_config.tx.retry_delay


class TxBuilder:
    """
    Transaction builder and sender

    Handles:
    - Building versioned transactions with compute budget
    - Signing via local or remote signer
    - Sending with retry logic
    - Confirmation polling

    Usage:
        builder = TxBuilder(rpc, signer)

        # Build and send
        result = builder.build_and_send(instructions)

        # Or step by step
        tx_bytes = builder.build(instructions)
        signed_bytes, sig = builder.sign(tx_bytes)
        result = builder.send(signed_bytes)
    """

    def __init__(
        self,
        rpc: RpcClient,
        signer: Signer,
        config: Optional[TxBuilderConfig] = None,
    ):
        """
        Initialize transaction builder

        Args:
            rpc: RPC client
            signer: Transaction signer
            config: Transaction configuration
        """
        self._rpc = rpc
        self._signer = signer
        self._config = config or TxBuilderConfig()

        if VersionedTransaction is None:
            raise RuntimeError("solders is required for TxBuilder")

    @property
    def pubkey(self) -> str:
        """Signer's public key"""
        return self._signer.pubkey

    def build(
        self,
        instructions: List["Instruction"],
        payer: Optional[str] = None,
        compute_units: Optional[int] = None,
        compute_unit_price: Optional[int] = None,
        recent_blockhash: Optional[str] = None,
    ) -> bytes:
        """
        Build unsigned versioned transaction

        Args:
            instructions: List of instructions
            payer: Fee payer pubkey (defaults to signer)
            compute_units: Compute unit limit
            compute_unit_price: Priority fee in microlamports per CU
            recent_blockhash: Optional blockhash (fetched if not provided)

        Returns:
            Unsigned transaction bytes
        """
        # Add compute budget instructions at the beginning
        all_instructions = []

        cu_limit = compute_units or self._config.compute_units
        cu_price = compute_unit_price or self._config.compute_unit_price

        if cu_limit > 0:
            all_instructions.append(set_compute_unit_limit(cu_limit))

        if cu_price > 0:
            all_instructions.append(set_compute_unit_price(cu_price))

        all_instructions.extend(instructions)

        # Get blockhash if not provided
        if recent_blockhash is None:
            blockhash_info = self._rpc.get_latest_blockhash()
            recent_blockhash = blockhash_info.get("blockhash")

        if not recent_blockhash:
            raise TransactionError.send_failed("Failed to get recent blockhash")

        # Build message
        payer_pubkey = Pubkey.from_string(payer or self.pubkey)
        message = MessageV0.try_compile(
            payer_pubkey,
            all_instructions,
            [],  # Address lookup tables
            Hash.from_string(recent_blockhash),
        )

        # Create unsigned transaction with placeholder signatures
        # VersionedTransaction requires signatures array to match num_required_signatures
        from solders.signature import Signature
        num_signers = message.header.num_required_signatures
        null_signatures = [Signature.default()] * num_signers
        tx = VersionedTransaction.populate(message, null_signatures)

        return bytes(tx)

    def sign(
        self,
        unsigned_tx: bytes,
        additional_signers: Optional[List["Keypair"]] = None,
    ) -> Tuple[bytes, str]:
        """
        Sign transaction

        Args:
            unsigned_tx: Unsigned transaction bytes
            additional_signers: Optional list of additional keypairs to sign with

        Returns:
            (signed_tx_bytes, signature_base58)
        """
        if not additional_signers:
            return self._signer.sign_transaction(unsigned_tx)

        # For multi-signer transactions, we need to handle signing carefully
        from solders.signature import Signature

        # Parse the unsigned transaction to get the message
        tx = VersionedTransaction.from_bytes(unsigned_tx)
        message = tx.message

        # Get message bytes for signing
        # For MessageV0, we need to include the version prefix (0x80)
        message_bytes = bytes(message)
        if isinstance(message, MessageV0):
            message_bytes = bytes([0x80]) + message_bytes

        # Get account keys from the message
        # The message header tells us how many signers are required
        account_keys = list(message.account_keys)
        num_required_signatures = message.header.num_required_signatures

        logger.debug(f"Transaction requires {num_required_signatures} signatures")
        logger.debug(f"First {num_required_signatures} account keys (signers): {[str(k) for k in account_keys[:num_required_signatures]]}")

        # Create a list of null signatures for all required signers
        null_sig = Signature.default()
        signatures = [null_sig] * num_required_signatures

        # Find the wallet's signer index
        signer_pubkey_str = self._signer.pubkey
        wallet_signer_index = None
        for i in range(num_required_signatures):
            # Compare as strings to avoid Pubkey object comparison issues
            if str(account_keys[i]) == signer_pubkey_str:
                wallet_signer_index = i
                break

        if wallet_signer_index is None:
            # Log available signers for debugging
            available = [str(account_keys[i]) for i in range(num_required_signatures)]
            logger.error(f"Wallet pubkey {signer_pubkey_str} not in signers: {available}")
            raise TransactionError.send_failed(
                f"Wallet pubkey {self._signer.pubkey} not found in transaction signers. "
                f"Required signers: {available}"
            )

        # Get wallet signature - handle both LocalSigner and RemoteSigner
        # Try sign() first (LocalSigner), fall back to sign_transaction (RemoteSigner)
        wallet_signature = None
        try:
            # LocalSigner has sign() that works on raw message bytes
            sig_bytes = self._signer.sign(message_bytes)
            wallet_signature = Signature.from_bytes(sig_bytes)
        except NotImplementedError:
            # RemoteSigner only supports sign_transaction
            # Call sign_transaction and extract the signature from the result
            signed_tx_bytes, sig_str = self._signer.sign_transaction(unsigned_tx)

            # Parse the signed transaction to get the wallet's signature
            partially_signed_tx = VersionedTransaction.from_bytes(signed_tx_bytes)
            partial_sigs = list(partially_signed_tx.signatures)

            # Find the wallet's signature by matching its position in account keys
            # The wallet may not be at index 0 if a custom payer was specified
            if len(partial_sigs) > 0:
                # Check if the wallet is at its expected index in the partial signatures
                if wallet_signer_index < len(partial_sigs):
                    candidate_sig = partial_sigs[wallet_signer_index]
                    # Verify it's not a null signature
                    if candidate_sig != null_sig:
                        wallet_signature = candidate_sig
                    else:
                        # Fall back to first non-null signature (remote signer typically signs one)
                        for sig in partial_sigs:
                            if sig != null_sig:
                                wallet_signature = sig
                                break
                else:
                    # Partial sig list is shorter, find the first non-null
                    for sig in partial_sigs:
                        if sig != null_sig:
                            wallet_signature = sig
                            break

        if wallet_signature is None:
            raise TransactionError.send_failed("Failed to obtain wallet signature")

        signatures[wallet_signer_index] = wallet_signature

        # Sign with additional signers (these are local keypairs)
        for keypair in additional_signers:
            kp_pubkey = keypair.pubkey()
            kp_pubkey_str = str(kp_pubkey)
            found = False
            for i in range(num_required_signatures):
                # Compare as strings to avoid Pubkey object comparison issues
                if str(account_keys[i]) == kp_pubkey_str:
                    sig = keypair.sign_message(message_bytes)
                    signatures[i] = sig
                    found = True
                    logger.debug(f"Additional signer {kp_pubkey_str[:16]}... signed at index {i}")
                    break
            if not found:
                logger.warning(f"Additional signer {kp_pubkey_str} not found in required signers")

        # Verify all signatures are present
        missing_signers = []
        for i, sig in enumerate(signatures):
            if sig == null_sig:
                missing_signers.append(str(account_keys[i]))

        if missing_signers:
            raise TransactionError(
                f"Missing signatures for required signers: {', '.join(missing_signers)}",
                signature=None,
            )

        # Build the signed transaction with all signatures
        signed_tx = VersionedTransaction.populate(message, signatures)

        return bytes(signed_tx), str(wallet_signature)

    def send(
        self,
        signed_tx: bytes,
        skip_preflight: Optional[bool] = None,
        wait_confirmation: bool = True,
    ) -> TxResult:
        """
        Send signed transaction

        Args:
            signed_tx: Signed transaction bytes
            skip_preflight: Skip simulation (default from config)
            wait_confirmation: Wait for confirmation

        Returns:
            TxResult with status and signature
        """
        skip = skip_preflight if skip_preflight is not None else self._config.skip_preflight

        signature: Optional[str] = None

        for attempt in range(self._config.max_retries):
            try:
                signature = self._rpc.send_transaction(
                    signed_tx,
                    skip_preflight=skip,
                    preflight_commitment=self._config.preflight_commitment,
                )

                logger.info(f"Transaction sent: {signature}")

                if wait_confirmation:
                    confirmed = self._rpc.confirm_transaction(
                        signature,
                        commitment=self._config.preflight_commitment,
                        timeout_seconds=self._config.confirmation_timeout,
                    )

                    if confirmed is True:
                        return TxResult.success(signature)
                    elif confirmed is False:
                        # Transaction failed on-chain
                        return TxResult.failed(
                            "Transaction failed on-chain (check explorer for details)",
                            signature=signature,
                        )
                    else:
                        # confirmed is None - timeout/dropped
                        return TxResult.timeout(signature)
                else:
                    return TxResult(
                        status=TxStatus.PENDING,
                        signature=signature,
                    )

            except RpcError as e:
                if e.recoverable and attempt < self._config.max_retries - 1:
                    logger.warning(f"Send failed (attempt {attempt + 1}), retrying: {e}")
                    time.sleep(self._config.retry_delay)
                    continue
                raise TransactionError.send_failed(str(e))

            except Exception as e:
                raise TransactionError.send_failed(str(e))

        # This should only be reached if max_retries is 0 (misconfiguration)
        raise TransactionError.send_failed("No send attempts made (max_retries=0)")

    def simulate(
        self,
        unsigned_tx: bytes,
    ) -> dict:
        """
        Simulate transaction execution

        Args:
            unsigned_tx: Unsigned transaction bytes

        Returns:
            Simulation result
        """
        return self._rpc.simulate_transaction(unsigned_tx)

    def build_and_send(
        self,
        instructions: List["Instruction"],
        compute_units: Optional[int] = None,
        compute_unit_price: Optional[int] = None,
        skip_preflight: Optional[bool] = None,
        wait_confirmation: bool = True,
        simulate_first: bool = False,
        additional_signers: Optional[List["Keypair"]] = None,
    ) -> TxResult:
        """
        Build, sign, and send transaction in one call

        Args:
            instructions: List of instructions
            compute_units: Compute unit limit
            compute_unit_price: Priority fee
            skip_preflight: Skip simulation
            wait_confirmation: Wait for confirmation
            simulate_first: Run simulation before sending
            additional_signers: Optional list of additional keypairs to sign with

        Returns:
            TxResult
        """
        # Build unsigned transaction
        unsigned_tx = self.build(
            instructions,
            compute_units=compute_units,
            compute_unit_price=compute_unit_price,
        )

        # Optional simulation
        if simulate_first:
            sim_result = self.simulate(unsigned_tx)
            if sim_result.get("value", {}).get("err"):
                error_msg = str(sim_result["value"]["err"])
                logs = sim_result.get("value", {}).get("logs", [])
                raise TransactionError.simulation_failed(error_msg, logs)

        # Sign (with additional signers if provided)
        signed_tx, signature = self.sign(unsigned_tx, additional_signers)

        # Send
        return self.send(
            signed_tx,
            skip_preflight=skip_preflight,
            wait_confirmation=wait_confirmation,
        )


def create_instruction(
    program_id: str,
    accounts: List[dict],
    data: bytes,
) -> "Instruction":
    """
    Helper to create instruction from simple types

    Args:
        program_id: Program ID (base58)
        accounts: List of account dicts with keys:
            - pubkey: Account pubkey (base58)
            - is_signer: Whether account is signer
            - is_writable: Whether account is writable
        data: Instruction data bytes

    Returns:
        solders Instruction
    """
    if Instruction is None:
        raise RuntimeError("solders is required")

    account_metas = [
        AccountMeta(
            pubkey=Pubkey.from_string(acc["pubkey"]),
            is_signer=acc.get("is_signer", False),
            is_writable=acc.get("is_writable", False),
        )
        for acc in accounts
    ]

    return Instruction(
        program_id=Pubkey.from_string(program_id),
        accounts=account_metas,
        data=data,
    )
