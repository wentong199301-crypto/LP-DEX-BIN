"""
1inch Swap Adapter

Provides swap functionality for Ethereum and BSC chains via 1inch aggregator.
"""

import logging
from decimal import Decimal
from typing import Optional, Dict, Any

try:
    from web3 import Web3
    _HAS_WEB3 = True
except ImportError:
    Web3 = None
    _HAS_WEB3 = False

from ...types.result import QuoteResult, TxResult, TxStatus
from ...types.evm_tokens import (
    resolve_token_address,
    get_token_decimals,
    NATIVE_TOKEN_ADDRESS,
    is_native_token,
    get_native_symbol,
)
from ...infra.evm_signer import EVMSigner, create_web3, get_balance
from ...errors import SignerError, ConfigurationError, TransactionError
from ...config import config as global_config

from .api import OneInchAPI

logger = logging.getLogger(__name__)


class OneInchAdapter:
    """
    1inch Swap Adapter for ETH and BSC

    Provides swap functionality via 1inch aggregator.
    Uses web3.py for transaction signing and sending.

    Usage:
        # For Ethereum
        signer = EVMSigner.from_env()
        adapter = OneInchAdapter(chain_id=1, signer=signer)

        # For BSC
        adapter = OneInchAdapter(chain_id=56, signer=signer)

        # Get quote
        quote = adapter.quote("ETH", "USDC", Decimal("1.0"))

        # Execute swap
        result = adapter.swap("ETH", "USDC", Decimal("1.0"))
    """

    name = "oneinch"

    def __init__(
        self,
        chain_id: int = 1,
        signer: Optional[EVMSigner] = None,
        rpc_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        """
        Initialize 1inch adapter

        Args:
            chain_id: Chain ID (1 for ETH, 56 for BSC)
            signer: Optional EVM signer for executing swaps
            rpc_url: Optional RPC URL (uses config default if not provided)
            api_key: Optional 1inch API key (uses config if not provided)
        """
        if not _HAS_WEB3:
            raise RuntimeError(
                "web3 is required for OneInchAdapter. "
                "Install with: pip install web3"
            )

        self._chain_id = chain_id
        self._signer = signer

        # Validate chain ID
        if chain_id not in (1, 56):
            raise ConfigurationError.invalid(
                "chain_id",
                f"Unsupported chain ID: {chain_id}. Supported: 1 (ETH), 56 (BSC)"
            )

        # Determine RPC URL
        if rpc_url:
            self._rpc_url = rpc_url
        elif chain_id == 1:
            self._rpc_url = global_config.oneinch.eth_rpc_url
        else:  # chain_id == 56
            self._rpc_url = global_config.oneinch.bsc_rpc_url

        # Initialize web3 and API
        self._web3 = create_web3(self._rpc_url, chain_id)
        self._api = OneInchAPI(chain_id=chain_id, api_key=api_key)

        logger.info(f"Initialized OneInchAdapter for chain {self.chain_name} ({chain_id})")

    @property
    def chain_id(self) -> int:
        """Chain ID"""
        return self._chain_id

    @property
    def chain_name(self) -> str:
        """Human-readable chain name"""
        return "Ethereum" if self._chain_id == 1 else "BSC"

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

    def quote(
        self,
        from_token: str,
        to_token: str,
        amount: Decimal,
        slippage_bps: int = 50,
    ) -> QuoteResult:
        """
        Get swap quote

        Args:
            from_token: Input token (symbol like "ETH" or address)
            to_token: Output token (symbol like "USDC" or address)
            amount: Amount in UI units (e.g., 1.5 ETH)
            slippage_bps: Slippage tolerance in basis points (50 = 0.5%)

        Returns:
            QuoteResult with swap details
        """
        # Resolve token addresses
        from_address = resolve_token_address(from_token, self._chain_id)
        to_address = resolve_token_address(to_token, self._chain_id)

        # Get decimals and convert to raw amount
        from_decimals = self._get_decimals(from_token)
        raw_amount = int(amount * Decimal(10 ** from_decimals))

        # Get quote from API
        quote = self._api.get_quote(
            src_token=from_address,
            dst_token=to_address,
            amount=raw_amount,
            include_gas=True,
        )

        # Calculate min output with slippage
        slippage_factor = Decimal(1) - Decimal(slippage_bps) / Decimal(10000)
        min_out = int(Decimal(quote.to_amount) * slippage_factor)

        # Update quote with slippage info
        quote.min_to_amount = min_out
        quote.slippage_bps = slippage_bps

        return quote

    def swap(
        self,
        from_token: str,
        to_token: str,
        amount: Decimal,
        slippage_bps: int = 50,
        wait_confirmation: bool = True,
    ) -> TxResult:
        """
        Execute swap

        Args:
            from_token: Input token (symbol or address)
            to_token: Output token (symbol or address)
            amount: Amount in UI units
            slippage_bps: Slippage tolerance in basis points
            wait_confirmation: Wait for transaction confirmation

        Returns:
            TxResult with transaction status
        """
        if not self._signer:
            raise SignerError.not_configured()

        # Resolve token addresses
        from_address = resolve_token_address(from_token, self._chain_id)
        to_address = resolve_token_address(to_token, self._chain_id)

        # Get decimals and convert amount
        from_decimals = self._get_decimals(from_token)
        raw_amount = int(amount * Decimal(10 ** from_decimals))

        # Check and handle token approval (if not native token)
        if not is_native_token(from_address):
            approval_result = self._ensure_approval(from_address, raw_amount)
            if approval_result and not approval_result.is_success:
                return approval_result

        # Convert slippage from bps to decimal (50 bps = 0.5% = 0.005)
        slippage_decimal = slippage_bps / 10000.0

        try:
            # Get swap transaction data
            swap_data = self._api.get_swap(
                src_token=from_address,
                dst_token=to_address,
                amount=raw_amount,
                from_address=self._signer.address,
                slippage=slippage_decimal,
            )

            # Build transaction
            gas_estimate = swap_data["gas"]
            gas_with_buffer = int(gas_estimate * global_config.oneinch.gas_limit_multiplier)

            tx_dict = {
                "to": Web3.to_checksum_address(swap_data["to"]),
                "data": swap_data["data"],
                "value": swap_data["value"],
                "gas": gas_with_buffer,
                "nonce": self._web3.eth.get_transaction_count(self._signer.address),
                "chainId": self._chain_id,
            }

            # Use EIP-1559 for Ethereum, legacy for BSC
            if self._chain_id == 1:
                latest_block = self._web3.eth.get_block("latest")
                base_fee = latest_block.get("baseFeePerGas", 0)
                max_priority_fee = self._web3.to_wei(2, "gwei")
                max_fee = int(base_fee * 2) + max_priority_fee
                tx_dict["maxFeePerGas"] = max_fee
                tx_dict["maxPriorityFeePerGas"] = max_priority_fee
            else:
                tx_dict["gasPrice"] = self._web3.eth.gas_price

            # Sign and send
            result = self._signer.sign_and_send(
                self._web3,
                tx_dict,
                wait_for_receipt=wait_confirmation,
            )

            return self._result_to_tx_result(result)

        except Exception as e:
            logger.error(f"Swap failed: {e}")
            return TxResult.failed(str(e))

    def execute_quote(
        self,
        quote: QuoteResult,
        wait_confirmation: bool = True,
    ) -> TxResult:
        """
        Execute a previously obtained quote

        Args:
            quote: Quote from quote() method
            wait_confirmation: Wait for confirmation

        Returns:
            TxResult
        """
        if not self._signer:
            raise SignerError.not_configured()

        # Convert slippage from bps to decimal (50 bps = 0.5% = 0.005)
        slippage_decimal = quote.slippage_bps / 10000.0

        # Check and handle token approval (if not native token)
        if not is_native_token(quote.from_token):
            approval_result = self._ensure_approval(quote.from_token, quote.from_amount)
            if approval_result and not approval_result.is_success:
                return approval_result

        try:
            # Get swap transaction data
            swap_data = self._api.get_swap(
                src_token=quote.from_token,
                dst_token=quote.to_token,
                amount=quote.from_amount,
                from_address=self._signer.address,
                slippage=slippage_decimal,
            )

            # Build transaction
            gas_estimate = swap_data["gas"]
            gas_with_buffer = int(gas_estimate * global_config.oneinch.gas_limit_multiplier)

            tx_dict = {
                "to": Web3.to_checksum_address(swap_data["to"]),
                "data": swap_data["data"],
                "value": swap_data["value"],
                "gas": gas_with_buffer,
                "nonce": self._web3.eth.get_transaction_count(self._signer.address),
                "chainId": self._chain_id,
            }

            # Use EIP-1559 for Ethereum, legacy for BSC
            if self._chain_id == 1:
                latest_block = self._web3.eth.get_block("latest")
                base_fee = latest_block.get("baseFeePerGas", 0)
                max_priority_fee = self._web3.to_wei(2, "gwei")
                max_fee = int(base_fee * 2) + max_priority_fee
                tx_dict["maxFeePerGas"] = max_fee
                tx_dict["maxPriorityFeePerGas"] = max_priority_fee
            else:
                tx_dict["gasPrice"] = self._web3.eth.gas_price

            # Sign and send
            result = self._signer.sign_and_send(
                self._web3,
                tx_dict,
                wait_for_receipt=wait_confirmation,
            )

            return self._result_to_tx_result(result)

        except Exception as e:
            logger.error(f"Execute quote failed: {e}")
            return TxResult.failed(str(e))

    def _ensure_approval(
        self,
        token_address: str,
        amount: int,
    ) -> Optional[TxResult]:
        """
        Ensure token is approved for 1inch router

        Args:
            token_address: Token address to approve
            amount: Amount needed

        Returns:
            TxResult if approval was needed, None if already approved
        """
        try:
            # Check current allowance
            allowance = self._api.get_allowance(token_address, self._signer.address)

            if allowance >= amount:
                logger.debug(f"Token {token_address} already approved (allowance: {allowance})")
                return None  # Already approved

            logger.info(f"Approving token {token_address} for 1inch router...")

            # Get approval transaction (unlimited approval)
            approve_tx = self._api.get_approve_transaction(token_address, amount=None)

            # Estimate gas for approval (some tokens like proxy-based may need more)
            approve_tx_for_estimate = {
                "from": self._signer.address,
                "to": Web3.to_checksum_address(approve_tx["to"]),
                "data": approve_tx["data"],
                "value": approve_tx["value"],
            }
            try:
                estimated_gas = self._web3.eth.estimate_gas(approve_tx_for_estimate)
                # Add 20% buffer for safety
                gas_limit = int(estimated_gas * 1.2)
            except Exception:
                # Fallback to standard ERC20 approve gas with buffer
                gas_limit = 150000

            tx_dict = {
                "to": Web3.to_checksum_address(approve_tx["to"]),
                "data": approve_tx["data"],
                "value": approve_tx["value"],
                "gas": gas_limit,
                "nonce": self._web3.eth.get_transaction_count(self._signer.address),
                "chainId": self._chain_id,
            }

            # Use EIP-1559 for Ethereum, legacy for BSC
            if self._chain_id == 1:
                latest_block = self._web3.eth.get_block("latest")
                base_fee = latest_block.get("baseFeePerGas", 0)
                max_priority_fee = self._web3.to_wei(2, "gwei")
                max_fee = int(base_fee * 2) + max_priority_fee
                tx_dict["maxFeePerGas"] = max_fee
                tx_dict["maxPriorityFeePerGas"] = max_priority_fee
            else:
                tx_dict["gasPrice"] = self._web3.eth.gas_price

            result = self._signer.sign_and_send(
                self._web3,
                tx_dict,
                wait_for_receipt=True,
                timeout=60,
            )

            if result["status"] == "success":
                logger.info(f"Token approval successful: {result['tx_hash']}")
                return TxResult.success(signature=result["tx_hash"])
            else:
                logger.error(f"Token approval failed: {result.get('error', 'Unknown error')}")
                return TxResult.failed(f"Approval failed: {result.get('error', 'Unknown error')}")

        except Exception as e:
            logger.error(f"Token approval error: {e}")
            return TxResult.failed(f"Approval error: {e}")

    def _result_to_tx_result(self, result: Dict[str, Any]) -> TxResult:
        """Convert signer result to TxResult"""
        if result["status"] == "success":
            return TxResult.success(
                signature=result["tx_hash"],
                # Note: gas_used is available in result but not stored in TxResult
                # since fee_lamports is Solana-specific terminology
            )
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

    def get_balance(self, token: str) -> Decimal:
        """
        Get token balance

        Args:
            token: Token symbol or address

        Returns:
            Balance in UI units
        """
        if not self._signer:
            raise SignerError.not_configured()

        token_address = resolve_token_address(token, self._chain_id)
        decimals = self._get_decimals(token)

        raw_balance = get_balance(
            self._web3,
            self._signer.address,
            token_address if not is_native_token(token_address) else None,
        )

        return Decimal(raw_balance) / Decimal(10 ** decimals)

    def get_native_balance(self) -> Decimal:
        """Get native token balance (ETH or BNB)"""
        native = get_native_symbol(self._chain_id)
        return self.get_balance(native)

    def get_token_balance(self, token: str) -> Decimal:
        """Get ERC20 token balance"""
        return self.get_balance(token)

    def estimate_gas(
        self,
        from_token: str,
        to_token: str,
        amount: Decimal,
    ) -> int:
        """
        Estimate gas for a swap

        Args:
            from_token: Input token
            to_token: Output token
            amount: Amount in UI units

        Returns:
            Estimated gas units
        """
        quote = self.quote(from_token, to_token, amount)
        return quote.fee_amount or 200000  # Default gas estimate

    def close(self):
        """Close API client"""
        self._api.close()

    def __enter__(self) -> "OneInchAdapter":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __repr__(self) -> str:
        addr = self.address[:10] + "..." if self.address else "None"
        return f"OneInchAdapter(chain={self.chain_name}, address={addr})"
