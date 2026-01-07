"""
Test RPC Client with Mocks

Tests for RPC client behavior with mocked responses.
"""

import sys
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def test_rpc_config_defaults():
    """Test RpcClientConfig default values from global config"""
    from dex_adapter.infra.rpc import RpcClientConfig

    print("Testing RpcClientConfig defaults...")

    config = RpcClientConfig()

    # Should have defaults from global config
    assert config.timeout_seconds > 0, "Should have positive timeout"
    assert config.max_retries > 0, "Should have positive retries"
    assert config.commitment in ("processed", "confirmed", "finalized"), "Invalid commitment"

    print("  RpcClientConfig defaults: PASSED")


def test_rpc_config_override():
    """Test RpcClientConfig with overrides"""
    from dex_adapter.infra.rpc import RpcClientConfig

    print("Testing RpcClientConfig override...")

    config = RpcClientConfig(
        timeout_seconds=60.0,
        max_retries=5,
        commitment="finalized",
    )

    assert config.timeout_seconds == 60.0, "Should use override timeout"
    assert config.max_retries == 5, "Should use override retries"
    assert config.commitment == "finalized", "Should use override commitment"

    print("  RpcClientConfig override: PASSED")


def test_rpc_client_init():
    """Test RpcClient initialization"""
    print("Testing RpcClient init...")

    try:
        from dex_adapter.infra.rpc import RpcClient, RpcClientConfig

        # Single endpoint
        client = RpcClient("https://api.mainnet-beta.solana.com")
        assert client.endpoint == "https://api.mainnet-beta.solana.com"

        # Multiple endpoints
        client = RpcClient([
            "https://primary.example.com",
            "https://backup.example.com",
        ])
        assert client.endpoint == "https://primary.example.com"

        # Empty endpoints should raise ConfigurationError
        from dex_adapter.errors import ConfigurationError
        try:
            RpcClient([])
            assert False, "Should raise for empty endpoints"
        except ConfigurationError:
            pass

        print("  RpcClient init: PASSED")

    except RuntimeError as e:
        # httpx not installed
        if "httpx" in str(e):
            print("  RpcClient init: SKIPPED (httpx not installed)")
        else:
            raise


def test_rpc_call_success():
    """Test successful RPC call"""
    print("Testing RPC call success...")

    try:
        import httpx
        from dex_adapter.infra.rpc import RpcClient

        # Create mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"blockhash": "test_blockhash", "lastValidBlockHeight": 12345},
        }
        mock_response.raise_for_status = Mock()

        # Mock the httpx client
        with patch.object(httpx.Client, 'post', return_value=mock_response):
            client = RpcClient("https://api.mainnet-beta.solana.com")
            result = client.call("getLatestBlockhash", [{"commitment": "confirmed"}])

            assert result is not None
            assert "blockhash" in result
            assert result["blockhash"] == "test_blockhash"

        print("  RPC call success: PASSED")

    except ImportError:
        print("  RPC call success: SKIPPED (httpx not installed)")


def test_rpc_call_error():
    """Test RPC error handling"""
    print("Testing RPC error handling...")

    try:
        import httpx
        from dex_adapter.infra.rpc import RpcClient
        from dex_adapter.errors import RpcError

        # Create mock error response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32600, "message": "Invalid request"},
        }
        mock_response.raise_for_status = Mock()

        with patch.object(httpx.Client, 'post', return_value=mock_response):
            client = RpcClient("https://api.mainnet-beta.solana.com")

            try:
                client.call("invalidMethod", [])
                assert False, "Should raise RpcError"
            except RpcError as e:
                assert "Invalid request" in str(e)

        print("  RPC error handling: PASSED")

    except ImportError:
        print("  RPC error handling: SKIPPED (httpx not installed)")


def test_rpc_rate_limit():
    """Test rate limit handling"""
    print("Testing rate limit handling...")

    try:
        import httpx
        from dex_adapter.infra.rpc import RpcClient, RpcClientConfig
        from dex_adapter.errors import RpcError

        # Create mock rate limit response, then success
        rate_limit_response = Mock()
        rate_limit_response.status_code = 429

        success_response = Mock()
        success_response.status_code = 200
        success_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": 12345,
        }
        success_response.raise_for_status = Mock()

        # First call returns 429, second returns success
        with patch.object(httpx.Client, 'post', side_effect=[rate_limit_response, success_response]):
            config = RpcClientConfig(retry_delay_seconds=0.01)  # Fast retry for test
            client = RpcClient("https://api.mainnet-beta.solana.com", config)

            # Should retry and succeed
            result = client.call("getSlot", [])
            assert result == 12345

        print("  Rate limit handling: PASSED")

    except ImportError:
        print("  Rate limit handling: SKIPPED (httpx not installed)")


def test_rpc_timeout():
    """Test timeout handling"""
    print("Testing timeout handling...")

    try:
        import httpx
        from dex_adapter.infra.rpc import RpcClient, RpcClientConfig
        from dex_adapter.errors import RpcError

        with patch.object(httpx.Client, 'post', side_effect=httpx.TimeoutException("Timeout")):
            config = RpcClientConfig(timeout_seconds=1.0, max_retries=1, retry_delay_seconds=0.01)
            client = RpcClient("https://api.mainnet-beta.solana.com", config)

            try:
                client.call("getSlot", [])
                assert False, "Should raise RpcError for timeout"
            except RpcError as e:
                assert e.recoverable, "Timeout should be recoverable"
                # The error message is "RPC request timed out after Xs"
                assert "timed out" in str(e).lower()

        print("  Timeout handling: PASSED")

    except ImportError:
        print("  Timeout handling: SKIPPED (httpx not installed)")


def test_rpc_endpoint_rotation():
    """Test endpoint rotation on failure"""
    print("Testing endpoint rotation...")

    try:
        import httpx
        from dex_adapter.infra.rpc import RpcClient, RpcClientConfig
        from dex_adapter.errors import RpcError

        # First endpoint fails, second succeeds
        fail_response = Mock()
        fail_response.status_code = 500
        fail_response.raise_for_status = Mock(side_effect=httpx.HTTPStatusError("Server Error", request=Mock(), response=fail_response))

        success_response = Mock()
        success_response.status_code = 200
        success_response.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": 12345}
        success_response.raise_for_status = Mock()

        # With max_retries=2, each endpoint gets 2 attempts
        # Endpoint 1: attempt 1 (fail), attempt 2 (fail) -> rotate
        # Endpoint 2: attempt 1 (fail), attempt 2 (success)
        # Total: 4 calls
        with patch.object(httpx.Client, 'post', side_effect=[fail_response, fail_response, fail_response, success_response]):
            config = RpcClientConfig(max_retries=2, retry_delay_seconds=0.01)
            client = RpcClient([
                "https://failing.example.com",
                "https://working.example.com",
            ], config)

            result = client.call("getSlot", [])
            assert result == 12345
            assert client.endpoint == "https://working.example.com"

        print("  Endpoint rotation: PASSED")

    except ImportError:
        print("  Endpoint rotation: SKIPPED (httpx not installed)")


def test_get_account_info():
    """Test get_account_info method"""
    print("Testing get_account_info...")

    try:
        import httpx
        from dex_adapter.infra.rpc import RpcClient

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "value": {
                    "data": ["base64data", "base64"],
                    "executable": False,
                    "lamports": 1000000,
                    "owner": "11111111111111111111111111111111",
                }
            },
        }
        mock_response.raise_for_status = Mock()

        with patch.object(httpx.Client, 'post', return_value=mock_response):
            client = RpcClient("https://api.mainnet-beta.solana.com")
            result = client.get_account_info("SomeAccountAddress")

            assert result is not None
            assert "lamports" in result
            assert result["lamports"] == 1000000

        print("  get_account_info: PASSED")

    except ImportError:
        print("  get_account_info: SKIPPED (httpx not installed)")


def test_get_account_info_not_found():
    """Test get_account_info for non-existent account"""
    print("Testing get_account_info not found...")

    try:
        import httpx
        from dex_adapter.infra.rpc import RpcClient

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"value": None},
        }
        mock_response.raise_for_status = Mock()

        with patch.object(httpx.Client, 'post', return_value=mock_response):
            client = RpcClient("https://api.mainnet-beta.solana.com")
            result = client.get_account_info("NonExistentAccount")

            assert result is None

        print("  get_account_info not found: PASSED")

    except ImportError:
        print("  get_account_info not found: SKIPPED (httpx not installed)")


def main():
    """Run all RPC mock tests"""
    print("=" * 60)
    print("RPC Mock Tests")
    print("=" * 60)

    tests = [
        test_rpc_config_defaults,
        test_rpc_config_override,
        test_rpc_client_init,
        test_rpc_call_success,
        test_rpc_call_error,
        test_rpc_rate_limit,
        test_rpc_timeout,
        test_rpc_endpoint_rotation,
        test_get_account_info,
        test_get_account_info_not_found,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
