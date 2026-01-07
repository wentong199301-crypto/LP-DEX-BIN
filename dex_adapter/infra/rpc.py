"""
RPC Client for Solana

Provides unified JSON-RPC interface with:
- Multiple endpoint fallback
- Retry logic
- Rate limit handling
- Request timeout management
"""

from __future__ import annotations

import json
import logging
import time
import threading
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass

try:
    import httpx
except ImportError:
    httpx = None

from ..errors import RpcError, ConfigurationError
from ..config import config as global_config

logger = logging.getLogger(__name__)


@dataclass
class RpcClientConfig:
    """
    RPC client runtime configuration

    This is a runtime configuration class that allows per-client overrides
    while pulling defaults from the global config (dex_adapter.config.RpcConfig).

    Usage:
        # Use all defaults from environment
        client = RpcClient(endpoint)

        # Override specific settings
        config = RpcClientConfig(timeout_seconds=60, max_retries=5)
        client = RpcClient(endpoint, config=config)
    """
    timeout_seconds: float = None
    max_retries: int = None
    retry_delay_seconds: float = None
    commitment: str = None

    def __post_init__(self):
        """Apply defaults from global config for any unset values"""
        if self.timeout_seconds is None:
            self.timeout_seconds = global_config.rpc.timeout_seconds
        if self.max_retries is None:
            self.max_retries = global_config.rpc.max_retries
        if self.retry_delay_seconds is None:
            self.retry_delay_seconds = global_config.rpc.retry_delay_seconds
        if self.commitment is None:
            self.commitment = global_config.rpc.commitment


class RpcClient:
    """
    Unified Solana RPC client

    Supports:
    - Multiple RPC endpoints with automatic fallback
    - Retry logic for transient failures
    - Rate limit handling with backoff
    - Configurable timeouts

    Usage:
        # Single endpoint
        rpc = RpcClient("https://api.mainnet-beta.solana.com")

        # Multiple endpoints with fallback
        rpc = RpcClient([
            "https://primary-rpc.example.com",
            "https://backup-rpc.example.com",
        ])

        # Get account info
        data = rpc.get_account_info("AccountAddress...")

        # Custom RPC call
        result = rpc.call("getSlot", [])
    """

    def __init__(
        self,
        endpoint: Union[str, List[str]],
        config: Optional[RpcClientConfig] = None,
    ):
        """
        Initialize RPC client

        Args:
            endpoint: RPC endpoint URL or list of URLs (for fallback)
            config: RPC configuration options
        """
        if httpx is None:
            raise RuntimeError("httpx is required for RPC calls. Install with: pip install httpx")

        self._endpoints = [endpoint] if isinstance(endpoint, str) else list(endpoint)
        if not self._endpoints:
            raise ConfigurationError.missing("RPC endpoint")

        self._config = config or RpcClientConfig()
        self._current_endpoint_idx = 0
        self._client: Optional[httpx.Client] = None
        self._client_lock = threading.Lock()

    @property
    def endpoint(self) -> str:
        """Current active endpoint"""
        return self._endpoints[self._current_endpoint_idx]

    @property
    def commitment(self) -> str:
        """Default commitment level"""
        return self._config.commitment

    def _get_client(self) -> httpx.Client:
        """Get or create HTTP client (thread-safe)"""
        if self._client is None:
            with self._client_lock:
                # Double-check after acquiring lock
                if self._client is None:
                    self._client = httpx.Client(
                        timeout=self._config.timeout_seconds,
                        headers={"Content-Type": "application/json"},
                    )
        return self._client

    def _rotate_endpoint(self):
        """Rotate to next endpoint on failure"""
        if len(self._endpoints) > 1:
            self._current_endpoint_idx = (self._current_endpoint_idx + 1) % len(self._endpoints)
            logger.info(f"Rotating to RPC endpoint: {self.endpoint}")

    def call(
        self,
        method: str,
        params: List[Any],
        timeout: Optional[float] = None,
    ) -> Any:
        """
        Make JSON-RPC call

        Args:
            method: RPC method name
            params: RPC parameters
            timeout: Optional timeout override

        Returns:
            RPC result

        Raises:
            RpcError: On RPC failure
        """
        client = self._get_client()
        request_id = 1
        body = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        last_error: Optional[Exception] = None
        endpoints_tried = 0
        max_endpoints = len(self._endpoints)

        while endpoints_tried < max_endpoints:
            for attempt in range(self._config.max_retries):
                try:
                    timeout_val = timeout or self._config.timeout_seconds

                    response = client.post(
                        self.endpoint,
                        json=body,
                        timeout=timeout_val,
                    )

                    # Handle rate limiting
                    if response.status_code == 429:
                        logger.warning(f"Rate limited by {self.endpoint}")
                        time.sleep(self._config.retry_delay_seconds * (attempt + 1))
                        continue

                    response.raise_for_status()
                    result = response.json()

                    # Check for RPC error
                    if "error" in result:
                        error = result["error"]
                        error_msg = error.get("message", str(error))
                        error_code = error.get("code")
                        rpc_error = RpcError(
                            f"RPC error: {error_msg}",
                            endpoint=self.endpoint,
                        )
                        # Preserve RPC error code in details for debugging
                        if rpc_error.details is None:
                            rpc_error.details = {}
                        rpc_error.details["rpc_error_code"] = error_code
                        rpc_error.details["rpc_error_data"] = error.get("data")
                        raise rpc_error

                    return result.get("result")

                except httpx.TimeoutException as e:
                    last_error = RpcError.timeout(self.endpoint, timeout_val)
                    logger.warning(f"RPC timeout (attempt {attempt + 1}): {self.endpoint}")

                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:
                        last_error = RpcError.rate_limited(self.endpoint)
                    else:
                        last_error = RpcError(
                            f"HTTP error {e.response.status_code}",
                            endpoint=self.endpoint,
                        )
                    logger.warning(f"RPC HTTP error (attempt {attempt + 1}): {e}")

                except httpx.RequestError as e:
                    last_error = RpcError.connection_failed(self.endpoint, e)
                    logger.warning(f"RPC connection error (attempt {attempt + 1}): {e}")

                except RpcError:
                    raise

                except Exception as e:
                    last_error = RpcError(
                        f"Unexpected error: {e}",
                        endpoint=self.endpoint,
                        original_error=e,
                    )

                # Wait before retry
                if attempt < self._config.max_retries - 1:
                    time.sleep(self._config.retry_delay_seconds * (attempt + 1))

            # All retries failed, try next endpoint
            self._rotate_endpoint()
            endpoints_tried += 1

        # All endpoints failed
        raise last_error or RpcError("All RPC endpoints failed")

    def get_account_info(
        self,
        address: str,
        encoding: str = "base64",
        commitment: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get account information

        Args:
            address: Account address (base58)
            encoding: Data encoding ("base64", "jsonParsed", etc.)
            commitment: Commitment level

        Returns:
            Account info or None if not found
        """
        params = [
            address,
            {
                "encoding": encoding,
                "commitment": commitment or self.commitment,
            },
        ]
        result = self.call("getAccountInfo", params)
        return result.get("value") if result else None

    def get_multiple_accounts(
        self,
        addresses: List[str],
        encoding: str = "base64",
        commitment: Optional[str] = None,
    ) -> List[Optional[Dict[str, Any]]]:
        """
        Get multiple account information in one call

        Args:
            addresses: List of account addresses
            encoding: Data encoding
            commitment: Commitment level

        Returns:
            List of account info (None for accounts not found)
        """
        params = [
            addresses,
            {
                "encoding": encoding,
                "commitment": commitment or self.commitment,
            },
        ]
        result = self.call("getMultipleAccounts", params)
        return result.get("value", []) if result else []

    def get_latest_blockhash(
        self,
        commitment: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get latest blockhash

        Returns:
            Dict with blockhash and lastValidBlockHeight
        """
        params = [{"commitment": commitment or self.commitment}]
        result = self.call("getLatestBlockhash", params)
        return result.get("value", {})

    def get_balance(
        self,
        address: str,
        commitment: Optional[str] = None,
    ) -> int:
        """
        Get SOL balance in lamports

        Args:
            address: Account address

        Returns:
            Balance in lamports
        """
        params = [address, {"commitment": commitment or self.commitment}]
        result = self.call("getBalance", params)
        return result.get("value", 0)

    def get_token_account_balance(
        self,
        token_account: str,
        commitment: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get SPL token account balance

        Args:
            token_account: Token account address

        Returns:
            Balance info with amount, decimals, uiAmount
        """
        params = [token_account, {"commitment": commitment or self.commitment}]
        result = self.call("getTokenAccountBalance", params)
        return result.get("value", {})

    def get_token_accounts_by_owner(
        self,
        owner: str,
        mint: Optional[str] = None,
        program_id: Optional[str] = None,
        encoding: str = "jsonParsed",
        commitment: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get token accounts owned by address

        Args:
            owner: Owner address
            mint: Optional mint filter
            program_id: Optional program filter
            encoding: Data encoding

        Returns:
            List of token account info
        """
        filter_param = {}
        if mint:
            filter_param["mint"] = mint
        elif program_id:
            filter_param["programId"] = program_id
        else:
            # Default to SPL Token program
            filter_param["programId"] = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"

        params = [
            owner,
            filter_param,
            {
                "encoding": encoding,
                "commitment": commitment or self.commitment,
            },
        ]
        result = self.call("getTokenAccountsByOwner", params)
        return result.get("value", [])

    def send_transaction(
        self,
        transaction: bytes,
        skip_preflight: bool = False,
        preflight_commitment: Optional[str] = None,
        max_retries: Optional[int] = None,
    ) -> str:
        """
        Send signed transaction

        Args:
            transaction: Signed transaction bytes
            skip_preflight: Skip preflight simulation
            preflight_commitment: Preflight commitment level
            max_retries: Max send retries

        Returns:
            Transaction signature (base58)
        """
        import base64 as b64

        # Always use base64 encoding (standard for Solana RPC)
        tx_data = b64.b64encode(transaction).decode("ascii")

        params = [
            tx_data,
            {
                "skipPreflight": skip_preflight,
                "preflightCommitment": preflight_commitment or self.commitment,
                "encoding": "base64",
            },
        ]
        if max_retries is not None:
            params[1]["maxRetries"] = max_retries

        return self.call("sendTransaction", params)

    def simulate_transaction(
        self,
        transaction: bytes,
        commitment: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Simulate transaction execution

        Args:
            transaction: Transaction bytes (can be unsigned)
            commitment: Commitment level

        Returns:
            Simulation result
        """
        import base64 as b64

        # Always use base64 encoding (standard for Solana RPC)
        tx_data = b64.b64encode(transaction).decode("ascii")

        params = [
            tx_data,
            {
                "commitment": commitment or self.commitment,
                "encoding": "base64",
                "sigVerify": False,
                "replaceRecentBlockhash": True,
            },
        ]
        return self.call("simulateTransaction", params)

    def confirm_transaction(
        self,
        signature: str,
        commitment: Optional[str] = None,
        timeout_seconds: float = 60.0,
    ) -> Optional[bool]:
        """
        Wait for transaction confirmation

        Args:
            signature: Transaction signature
            commitment: Commitment level
            timeout_seconds: Max wait time

        Returns:
            True if confirmed successfully
            False if transaction failed on-chain (has error)
            None if timeout (transaction never landed or status unknown)
        """
        start_time = time.time()
        last_status = None

        while time.time() - start_time < timeout_seconds:
            try:
                result = self.call(
                    "getSignatureStatuses",
                    [[signature]],
                )
                if result and result.get("value"):
                    status = result["value"][0]
                    if status:
                        last_status = status
                        if status.get("err"):
                            # Transaction failed on-chain
                            logger.warning(
                                f"Transaction {signature} failed on-chain: {status.get('err')}"
                            )
                            return False
                        conf = status.get("confirmationStatus")
                        if conf in ("confirmed", "finalized"):
                            return True
            except RpcError as e:
                logger.debug(f"Error checking transaction status: {e}")

            time.sleep(1.0)

        # Timeout - transaction never landed or didn't reach confirmation
        if last_status is None:
            logger.warning(
                f"Transaction {signature} was never seen on chain (dropped/expired)"
            )
        else:
            logger.warning(
                f"Transaction {signature} timeout. Last status: {last_status.get('confirmationStatus', 'unknown')}"
            )

        return None

    def get_token_largest_accounts(
        self,
        mint: str,
        commitment: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get the 20 largest token accounts for a mint

        Args:
            mint: Token mint address
            commitment: Commitment level

        Returns:
            List of account info with address and amount
        """
        params = [mint, {"commitment": commitment or self.commitment}]
        result = self.call("getTokenLargestAccounts", params)
        return result.get("value", []) if result else []

    def get_slot(self, commitment: Optional[str] = None) -> int:
        """Get current slot"""
        params = [{"commitment": commitment or self.commitment}]
        return self.call("getSlot", params)

    def get_block_height(self, commitment: Optional[str] = None) -> int:
        """Get current block height"""
        params = [{"commitment": commitment or self.commitment}]
        return self.call("getBlockHeight", params)

    def get_program_accounts(
        self,
        program_id: str,
        filters: Optional[List[Dict[str, Any]]] = None,
        encoding: str = "base64",
        commitment: Optional[str] = None,
        with_context: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Get all accounts owned by a program

        Args:
            program_id: Program ID (base58)
            filters: Optional filters (memcmp, dataSize)
            encoding: Data encoding ("base64", "jsonParsed", etc.)
            commitment: Commitment level
            with_context: Include context in response

        Returns:
            List of account info dicts with pubkey and account fields

        Example filters:
            [
                {"memcmp": {"offset": 0, "bytes": "base58_data"}},
                {"dataSize": 200}
            ]
        """
        config: Dict[str, Any] = {
            "encoding": encoding,
            "commitment": commitment or self.commitment,
        }
        if filters:
            config["filters"] = filters
        if with_context:
            config["withContext"] = True

        params = [program_id, config]
        result = self.call("getProgramAccounts", params)

        if with_context:
            return result.get("value", []) if result else []
        return result or []

    def close(self):
        """Close HTTP client"""
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
