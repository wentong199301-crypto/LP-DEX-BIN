"""
Jupiter API Client

REST API client for Jupiter swap aggregator.
"""

import logging
from decimal import Decimal
from typing import Optional, Dict, Any, List

try:
    import httpx
except ImportError:
    httpx = None

from ...types import QuoteResult
from ...config import config as global_config
from ...errors import RpcError

logger = logging.getLogger(__name__)


class JupiterAPI:
    """
    Jupiter REST API client

    Provides:
    - Swap quotes
    - Swap transaction building

    Usage:
        api = JupiterAPI()
        quote = api.get_quote("SOL_MINT", "USDC_MINT", 1000000000)
        tx_bytes = api.get_swap_transaction(quote, user_pubkey)
    """

    def __init__(
        self,
        timeout: float = None,
        max_retries: int = None,
        quote_url: str = None,
        swap_url: str = None,
        token_list_url: str = None,
    ):
        """
        Initialize Jupiter API client

        Args:
            timeout: Request timeout in seconds (default from config)
            max_retries: Max retry attempts (default from config)
            quote_url: Quote API URL (default from config)
            swap_url: Swap API URL (default from config)
            token_list_url: Token list API URL (default from config)
        """
        if httpx is None:
            raise RuntimeError("httpx is required for Jupiter API")

        self._timeout = timeout if timeout is not None else global_config.jupiter.timeout
        self._max_retries = max_retries if max_retries is not None else global_config.jupiter.max_retries
        self._quote_url = quote_url if quote_url is not None else global_config.jupiter.quote_url
        self._swap_url = swap_url if swap_url is not None else global_config.jupiter.swap_url
        self._token_list_url = token_list_url if token_list_url is not None else global_config.jupiter.token_list_url
        self._client: Optional[httpx.Client] = None

    def _get_client(self) -> httpx.Client:
        """Get or create HTTP client"""
        if self._client is None:
            self._client = httpx.Client(timeout=self._timeout)
        return self._client

    def get_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,
        slippage_bps: int = 50,
        swap_mode: str = "ExactIn",
        only_direct_routes: bool = False,
        as_legacy_transaction: bool = False,
    ) -> QuoteResult:
        """
        Get swap quote from Jupiter

        Args:
            input_mint: Input token mint address
            output_mint: Output token mint address
            amount: Amount in smallest units (lamports for SOL)
            slippage_bps: Slippage tolerance in basis points
            swap_mode: "ExactIn" or "ExactOut"
            only_direct_routes: Only use direct routes
            as_legacy_transaction: Request legacy transaction format

        Returns:
            QuoteResult with swap details
        """
        client = self._get_client()

        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": str(amount),
            "slippageBps": slippage_bps,
            "swapMode": swap_mode,
            "onlyDirectRoutes": str(only_direct_routes).lower(),
            "asLegacyTransaction": str(as_legacy_transaction).lower(),
        }

        for attempt in range(self._max_retries):
            try:
                response = client.get(self._quote_url, params=params)
                response.raise_for_status()
                data = response.json()

                # Parse response
                in_amount = int(data.get("inAmount", amount))
                out_amount = int(data.get("outAmount", 0))
                price_impact = Decimal(str(data.get("priceImpactPct", 0)))

                # Get route info
                route_plan = data.get("routePlan", [])
                route = [step.get("swapInfo", {}).get("label", "") for step in route_plan]

                # Calculate min output with slippage
                slippage_factor = Decimal(1) - Decimal(slippage_bps) / Decimal(10000)
                min_out = int(Decimal(out_amount) * slippage_factor)

                return QuoteResult(
                    from_token=input_mint,
                    to_token=output_mint,
                    from_amount=in_amount,
                    to_amount=out_amount,
                    price_impact=price_impact,
                    route=route,
                    min_to_amount=min_out,
                    slippage_bps=slippage_bps,
                    raw_response=data,  # Store full response for swap transaction
                )

            except httpx.HTTPStatusError as e:
                logger.warning(f"Jupiter quote failed (attempt {attempt + 1}): {e}")
                if attempt == self._max_retries - 1:
                    raise
            except Exception as e:
                logger.error(f"Jupiter quote error: {e}")
                raise

        raise RuntimeError("Failed to get Jupiter quote")

    def get_swap_transaction(
        self,
        quote: QuoteResult,
        user_pubkey: str,
        wrap_and_unwrap_sol: bool = True,
        compute_unit_price_micro_lamports: Optional[int] = None,
        as_legacy_transaction: bool = False,
    ) -> bytes:
        """
        Get swap transaction from Jupiter

        Args:
            quote: Quote result from get_quote()
            user_pubkey: User wallet public key
            wrap_and_unwrap_sol: Auto wrap/unwrap SOL
            compute_unit_price_micro_lamports: Priority fee
            as_legacy_transaction: Use legacy transaction format

        Returns:
            Serialized transaction bytes (base64 decoded)
        """
        import base64

        client = self._get_client()

        # Use stored raw response if available, otherwise re-fetch
        # (re-fetching can result in different route/price than user approved)
        if quote.raw_response:
            quote_data = quote.raw_response
        else:
            # Fallback: re-fetch quote (not recommended - may differ from original)
            logger.warning("Re-fetching quote - original response not available")
            quote_params = {
                "inputMint": quote.from_token,
                "outputMint": quote.to_token,
                "amount": str(quote.from_amount),
                "slippageBps": quote.slippage_bps,
            }
            quote_response = client.get(self._quote_url, params=quote_params)
            quote_response.raise_for_status()
            quote_data = quote_response.json()

        # Build swap request
        swap_request = {
            "quoteResponse": quote_data,
            "userPublicKey": user_pubkey,
            "wrapAndUnwrapSol": wrap_and_unwrap_sol,
            "asLegacyTransaction": as_legacy_transaction,
            "dynamicComputeUnitLimit": True,
        }

        if compute_unit_price_micro_lamports:
            swap_request["computeUnitPriceMicroLamports"] = compute_unit_price_micro_lamports

        for attempt in range(self._max_retries):
            try:
                response = client.post(self._swap_url, json=swap_request)
                response.raise_for_status()
                data = response.json()

                swap_transaction = data.get("swapTransaction")
                if not swap_transaction:
                    raise RpcError("No swap transaction in response from Jupiter API")

                return base64.b64decode(swap_transaction)

            except httpx.HTTPStatusError as e:
                logger.warning(f"Jupiter swap tx failed (attempt {attempt + 1}): {e}")
                if attempt == self._max_retries - 1:
                    raise
            except Exception as e:
                logger.error(f"Jupiter swap tx error: {e}")
                raise

        raise RuntimeError("Failed to get Jupiter swap transaction")

    def get_token_list(self) -> List[Dict[str, Any]]:
        """Get list of tradable tokens"""
        client = self._get_client()

        try:
            response = client.get(self._token_list_url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get token list: {e}")
            return []

    def close(self):
        """Close HTTP client"""
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
