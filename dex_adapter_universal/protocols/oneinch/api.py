"""
1inch API Client

REST API client for 1inch swap aggregator (v6.0).
Supports Ethereum (Chain ID 1) and BSC (Chain ID 56).
"""

import logging
from decimal import Decimal
from typing import Optional, Dict, Any, List

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    httpx = None
    _HAS_HTTPX = False

from ...types.result import QuoteResult
from ...config import config as global_config

logger = logging.getLogger(__name__)


class OneInchAPI:
    """
    1inch REST API client (v6.0)

    Provides:
    - Swap quotes
    - Swap transaction building
    - Token approvals

    Usage:
        api = OneInchAPI(chain_id=1)  # Ethereum
        quote = api.get_quote("0x...", "0x...", 1000000000000000000)
        swap_data = api.get_swap("0x...", "0x...", 1000000000000000000, "0xYourAddress")

    Note:
        Requires a 1inch API key. Set ONEINCH_API_KEY environment variable.
    """

    def __init__(
        self,
        chain_id: int = 1,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
    ):
        """
        Initialize 1inch API client

        Args:
            chain_id: Chain ID (1 for ETH, 56 for BSC)
            api_key: 1inch API key (or set ONEINCH_API_KEY env var)
            base_url: API base URL
            timeout: Request timeout in seconds
            max_retries: Max retry attempts
        """
        if not _HAS_HTTPX:
            raise RuntimeError("httpx is required for 1inch API. Install with: pip install httpx")

        self._chain_id = chain_id
        self._api_key = api_key or global_config.oneinch.api_key
        self._base_url = base_url or global_config.oneinch.base_url
        self._timeout = timeout or global_config.oneinch.timeout
        self._max_retries = max_retries or global_config.oneinch.max_retries
        self._client: Optional[httpx.Client] = None

        if not self._api_key:
            from ...errors import ConfigurationError
            raise ConfigurationError.missing(
                "ONEINCH_API_KEY",
                "1inch API key is required. Set ONEINCH_API_KEY environment variable."
            )

    @property
    def chain_id(self) -> int:
        """Chain ID this client is configured for"""
        return self._chain_id

    def _get_client(self) -> httpx.Client:
        """Get or create HTTP client with auth headers"""
        if self._client is None:
            headers = {
                "Accept": "application/json",
            }
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"

            self._client = httpx.Client(
                timeout=self._timeout,
                headers=headers,
            )
        return self._client

    def _build_url(self, endpoint: str) -> str:
        """Build full API URL"""
        return f"{self._base_url}/{self._chain_id}/{endpoint}"

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Make HTTP request with retries

        Args:
            method: HTTP method (GET, POST)
            endpoint: API endpoint
            params: Query parameters
            json_data: JSON body for POST

        Returns:
            Response JSON

        Raises:
            RuntimeError: If all retries fail
        """
        client = self._get_client()
        url = self._build_url(endpoint)
        last_error: Optional[Exception] = None

        for attempt in range(self._max_retries):
            try:
                if method.upper() == "GET":
                    response = client.get(url, params=params)
                else:
                    response = client.post(url, params=params, json=json_data)

                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                error_msg = f"HTTP {e.response.status_code}"
                try:
                    error_data = e.response.json()
                    if "error" in error_data:
                        error_msg = error_data["error"]
                    elif "description" in error_data:
                        error_msg = error_data["description"]
                    elif "message" in error_data:
                        error_msg = error_data["message"]
                    else:
                        error_msg = str(error_data)
                except Exception:
                    error_msg = e.response.text[:500] if e.response.text else error_msg

                logger.warning(f"1inch API error (attempt {attempt + 1}): {error_msg}")
                last_error = RuntimeError(f"1inch API error: {error_msg}")

                # Don't retry client errors (4xx)
                if 400 <= e.response.status_code < 500:
                    raise last_error

            except httpx.TimeoutException:
                logger.warning(f"1inch API timeout (attempt {attempt + 1})")
                last_error = RuntimeError("1inch API timeout")

            except httpx.RequestError as e:
                logger.warning(f"1inch API request error (attempt {attempt + 1}): {e}")
                last_error = RuntimeError(f"1inch API request error: {e}")

        raise last_error or RuntimeError("1inch API request failed")

    def get_quote(
        self,
        src_token: str,
        dst_token: str,
        amount: int,
        fee: Optional[float] = None,
        protocols: Optional[str] = None,
        include_tokens_info: bool = False,
        include_protocols: bool = False,
        include_gas: bool = False,
    ) -> QuoteResult:
        """
        Get swap quote from 1inch

        Args:
            src_token: Source token address
            dst_token: Destination token address
            amount: Amount in smallest units (wei)
            fee: Optional partner fee percentage
            protocols: Optional comma-separated protocol list
            include_tokens_info: Include token information in response
            include_protocols: Include protocols used in response
            include_gas: Include gas estimate in response

        Returns:
            QuoteResult with swap details
        """
        params = {
            "src": src_token,
            "dst": dst_token,
            "amount": str(amount),
        }

        if fee is not None:
            params["fee"] = str(fee)
        if protocols:
            params["protocols"] = protocols
        if include_tokens_info:
            params["includeTokensInfo"] = "true"
        if include_protocols:
            params["includeProtocols"] = "true"
        if include_gas:
            params["includeGas"] = "true"

        data = self._make_request("GET", "quote", params=params)

        dst_amount = int(data.get("dstAmount", 0))

        # Extract route information if available
        route: List[str] = []
        if "protocols" in data:
            for path in data["protocols"]:
                for step in path:
                    for swap in step:
                        if "name" in swap:
                            route.append(swap["name"])

        # Calculate gas estimate if available
        gas_estimate = 0
        if "gas" in data:
            gas_estimate = int(data["gas"])

        return QuoteResult(
            from_token=src_token,
            to_token=dst_token,
            from_amount=amount,
            to_amount=dst_amount,
            price_impact=Decimal("0"),  # 1inch doesn't provide price impact in quote
            fee_amount=gas_estimate,
            route=route,
            raw_response=data,
        )

    def get_swap(
        self,
        src_token: str,
        dst_token: str,
        amount: int,
        from_address: str,
        slippage: float = 1.0,
        disable_estimate: bool = False,
        protocols: Optional[str] = None,
        receiver: Optional[str] = None,
        referrer: Optional[str] = None,
        fee: Optional[float] = None,
        permit: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get swap transaction data from 1inch

        Args:
            src_token: Source token address
            dst_token: Destination token address
            amount: Amount in smallest units (wei)
            from_address: Sender wallet address
            slippage: Slippage tolerance in percent (e.g., 1.0 = 1%)
            disable_estimate: Disable gas estimation (faster but may fail)
            protocols: Optional comma-separated protocol list
            receiver: Optional receiver address (defaults to from_address)
            referrer: Optional referrer address for fees
            fee: Optional fee percentage
            permit: Optional permit signature for gasless approvals

        Returns:
            Dict with tx fields: to, data, value, gas, and swap info
        """
        params = {
            "src": src_token,
            "dst": dst_token,
            "amount": str(amount),
            "from": from_address,
            "slippage": str(slippage),
        }

        if disable_estimate:
            params["disableEstimate"] = "true"
        if protocols:
            params["protocols"] = protocols
        if receiver:
            params["receiver"] = receiver
        if referrer:
            params["referrer"] = referrer
        if fee is not None:
            params["fee"] = str(fee)
        if permit:
            params["permit"] = permit

        data = self._make_request("GET", "swap", params=params)

        tx = data.get("tx", {})

        return {
            "to": tx.get("to"),
            "data": tx.get("data"),
            "value": int(tx.get("value", 0)),
            "gas": int(tx.get("gas", 0)),
            "gas_price": int(tx.get("gasPrice", 0)) if tx.get("gasPrice") else None,
            "dst_amount": int(data.get("dstAmount", 0)),
            "src_token": data.get("srcToken", {}).get("address", src_token),
            "dst_token": data.get("dstToken", {}).get("address", dst_token),
            "raw_response": data,
        }

    def get_approve_spender(self) -> str:
        """
        Get the 1inch router address for token approvals

        Returns:
            1inch router/aggregator contract address
        """
        data = self._make_request("GET", "approve/spender")
        return data.get("address", "")

    def get_approve_transaction(
        self,
        token_address: str,
        amount: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Get token approval transaction data

        Args:
            token_address: Token to approve
            amount: Amount to approve (None for unlimited/max uint256)

        Returns:
            Dict with tx fields: to, data, value
        """
        params = {"tokenAddress": token_address}
        if amount is not None:
            params["amount"] = str(amount)

        data = self._make_request("GET", "approve/transaction", params=params)

        return {
            "to": data.get("to"),
            "data": data.get("data"),
            "value": int(data.get("value", 0)),
            "gas_limit": int(data.get("gasLimit", 0)) if data.get("gasLimit") else None,
        }

    def get_allowance(
        self,
        token_address: str,
        wallet_address: str,
    ) -> int:
        """
        Check current token allowance for 1inch router

        Args:
            token_address: Token address
            wallet_address: Wallet address

        Returns:
            Current allowance amount
        """
        params = {
            "tokenAddress": token_address,
            "walletAddress": wallet_address,
        }

        data = self._make_request("GET", "approve/allowance", params=params)
        return int(data.get("allowance", 0))

    def get_tokens(self) -> Dict[str, Any]:
        """
        Get list of supported tokens

        Returns:
            Dict mapping token addresses to token info
        """
        data = self._make_request("GET", "tokens")
        return data.get("tokens", {})

    def get_liquidity_sources(self) -> List[Dict[str, Any]]:
        """
        Get list of liquidity sources (protocols)

        Returns:
            List of protocol information
        """
        data = self._make_request("GET", "liquidity-sources")
        return data.get("protocols", [])

    def close(self):
        """Close HTTP client"""
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self) -> "OneInchAPI":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __repr__(self) -> str:
        return f"OneInchAPI(chain_id={self._chain_id})"
