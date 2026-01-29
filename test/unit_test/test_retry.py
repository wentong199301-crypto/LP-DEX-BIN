"""
Unit tests for retry logic module
"""

import unittest
from unittest.mock import MagicMock, patch
import time

from dex_adapter_universal.infra.retry import (
    execute_with_retry,
    execute_swap_with_retry,
    classify_error,
    CorrelationContext,
    generate_correlation_id,
    get_correlation_id,
    set_correlation_id,
    RECOVERABLE_KEYWORDS,
    SLIPPAGE_KEYWORDS,
)
from dex_adapter_universal.types import TxResult, TxStatus
from dex_adapter_universal.errors import ErrorCode


class TestClassifyError(unittest.TestCase):
    """Tests for error classification"""

    def test_timeout_error_is_recoverable(self):
        """Timeout errors should be classified as recoverable"""
        error = Exception("Connection timeout after 30 seconds")
        is_recoverable, is_slippage, error_code = classify_error(error)

        self.assertTrue(is_recoverable)
        self.assertFalse(is_slippage)
        self.assertEqual(error_code, ErrorCode.RPC_TIMEOUT)

    def test_network_error_is_recoverable(self):
        """Network errors should be classified as recoverable"""
        error = Exception("Network connection failed: ECONNRESET")
        is_recoverable, is_slippage, error_code = classify_error(error)

        self.assertTrue(is_recoverable)
        self.assertFalse(is_slippage)

    def test_rate_limit_error_is_recoverable(self):
        """Rate limit errors should be classified as recoverable"""
        error = Exception("Too many requests, rate limit exceeded")
        is_recoverable, is_slippage, error_code = classify_error(error)

        self.assertTrue(is_recoverable)
        self.assertFalse(is_slippage)
        self.assertEqual(error_code, ErrorCode.RPC_RATE_LIMITED)

    def test_slippage_error_is_identified(self):
        """Slippage errors should be identified and classified as recoverable"""
        error = Exception("Slippage exceeded maximum tolerance")
        is_recoverable, is_slippage, error_code = classify_error(error)

        self.assertTrue(is_recoverable)
        self.assertTrue(is_slippage)
        self.assertEqual(error_code, ErrorCode.SLIPPAGE_EXCEEDED)

    def test_price_impact_is_slippage(self):
        """Price impact errors should be classified as slippage"""
        error = Exception("Price impact too high")
        is_recoverable, is_slippage, error_code = classify_error(error)

        self.assertTrue(is_slippage)

    def test_unknown_error_not_recoverable(self):
        """Unknown errors should not be classified as recoverable"""
        error = Exception("Unexpected error in smart contract execution")
        is_recoverable, is_slippage, error_code = classify_error(error)

        self.assertFalse(is_recoverable)
        self.assertFalse(is_slippage)
        self.assertIsNone(error_code)

    def test_blockhash_error_is_recoverable(self):
        """Blockhash errors should be recoverable"""
        error = Exception("Blockhash not found")
        is_recoverable, is_slippage, error_code = classify_error(error)

        self.assertTrue(is_recoverable)
        self.assertFalse(is_slippage)

    def test_503_error_is_recoverable(self):
        """HTTP 503 errors should be recoverable"""
        error = Exception("Service temporarily unavailable: 503")
        is_recoverable, is_slippage, error_code = classify_error(error)

        self.assertTrue(is_recoverable)


class TestExecuteWithRetry(unittest.TestCase):
    """Tests for execute_with_retry function"""

    @patch("dex_adapter_universal.infra.retry.global_config")
    def test_success_on_first_attempt(self, mock_config):
        """Operation that succeeds on first attempt"""
        mock_config.tx.lp_max_retries = 5
        mock_config.tx.retry_delay = 0.1

        mock_operation = MagicMock(return_value=TxResult.success("test_signature"))

        result = execute_with_retry(mock_operation, "test_operation")

        self.assertTrue(result.is_success)
        self.assertEqual(result.signature, "test_signature")
        self.assertEqual(mock_operation.call_count, 1)

    @patch("dex_adapter_universal.infra.retry.global_config")
    @patch("dex_adapter_universal.infra.retry.time.sleep")
    def test_success_after_retries(self, mock_sleep, mock_config):
        """Operation that succeeds after retries"""
        mock_config.tx.lp_max_retries = 5
        mock_config.tx.retry_delay = 0.1

        # Fail twice then succeed
        mock_operation = MagicMock(side_effect=[
            TxResult.failed("timeout error", recoverable=True),
            TxResult.failed("timeout error", recoverable=True),
            TxResult.success("test_signature"),
        ])

        result = execute_with_retry(mock_operation, "test_operation")

        self.assertTrue(result.is_success)
        self.assertEqual(mock_operation.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("dex_adapter_universal.infra.retry.global_config")
    def test_non_recoverable_error_no_retry(self, mock_config):
        """Non-recoverable error should not trigger retry"""
        mock_config.tx.lp_max_retries = 5
        mock_config.tx.retry_delay = 0.1

        mock_operation = MagicMock(return_value=TxResult.failed("contract reverted", recoverable=False))

        result = execute_with_retry(mock_operation, "test_operation")

        self.assertFalse(result.is_success)
        self.assertEqual(mock_operation.call_count, 1)

    @patch("dex_adapter_universal.infra.retry.global_config")
    @patch("dex_adapter_universal.infra.retry.time.sleep")
    def test_max_retries_exceeded(self, mock_sleep, mock_config):
        """Should fail after max retries exceeded"""
        mock_config.tx.lp_max_retries = 3
        mock_config.tx.retry_delay = 0.1

        mock_operation = MagicMock(return_value=TxResult.failed("timeout error", recoverable=True))

        result = execute_with_retry(mock_operation, "test_operation")

        self.assertFalse(result.is_success)
        self.assertEqual(mock_operation.call_count, 3)
        self.assertTrue(result.recoverable)

    @patch("dex_adapter_universal.infra.retry.global_config")
    @patch("dex_adapter_universal.infra.retry.time.sleep")
    def test_exception_handling(self, mock_sleep, mock_config):
        """Exceptions should be caught and classified"""
        mock_config.tx.lp_max_retries = 3
        mock_config.tx.retry_delay = 0.1

        # Exception on first call, success on second
        mock_operation = MagicMock(side_effect=[
            Exception("Connection timeout"),
            TxResult.success("test_signature"),
        ])

        result = execute_with_retry(mock_operation, "test_operation")

        self.assertTrue(result.is_success)
        self.assertEqual(mock_operation.call_count, 2)

    @patch("dex_adapter_universal.infra.retry.global_config")
    @patch("dex_adapter_universal.infra.retry.time.sleep")
    def test_slippage_exception_retry(self, mock_sleep, mock_config):
        """Slippage exceptions should trigger retry"""
        mock_config.tx.lp_max_retries = 3
        mock_config.tx.retry_delay = 0.1

        mock_operation = MagicMock(side_effect=[
            Exception("Slippage exceeded"),
            TxResult.success("test_signature"),
        ])

        result = execute_with_retry(mock_operation, "test_operation")

        self.assertTrue(result.is_success)
        self.assertEqual(mock_operation.call_count, 2)

    @patch("dex_adapter_universal.infra.retry.global_config")
    def test_custom_max_retries(self, mock_config):
        """Custom max_retries should override config"""
        mock_config.tx.lp_max_retries = 10
        mock_config.tx.retry_delay = 0.1

        mock_operation = MagicMock(return_value=TxResult.failed("error", recoverable=True))

        result = execute_with_retry(mock_operation, "test_operation", max_retries=2)

        self.assertEqual(mock_operation.call_count, 2)

    @patch("dex_adapter_universal.infra.retry.global_config")
    def test_non_recoverable_exception(self, mock_config):
        """Non-recoverable exceptions should not trigger retry"""
        mock_config.tx.lp_max_retries = 5
        mock_config.tx.retry_delay = 0.1

        mock_operation = MagicMock(side_effect=Exception("Unknown smart contract error"))

        result = execute_with_retry(mock_operation, "test_operation")

        self.assertFalse(result.is_success)
        self.assertEqual(mock_operation.call_count, 1)


class TestRetryKeywords(unittest.TestCase):
    """Tests for retry keyword lists"""

    def test_recoverable_keywords_present(self):
        """Verify essential recoverable keywords are present"""
        essential_keywords = ["timeout", "connection", "network", "rate limit", "blockhash"]
        for keyword in essential_keywords:
            self.assertIn(keyword, RECOVERABLE_KEYWORDS)

    def test_slippage_keywords_present(self):
        """Verify essential slippage keywords are present"""
        essential_keywords = ["slippage", "price moved", "insufficient output"]
        for keyword in essential_keywords:
            self.assertIn(keyword, SLIPPAGE_KEYWORDS)


class TestCorrelationContext(unittest.TestCase):
    """Tests for correlation ID context management"""

    def test_generate_correlation_id(self):
        """Test correlation ID generation"""
        cid1 = generate_correlation_id()
        cid2 = generate_correlation_id()

        # Should be 12 hex characters
        self.assertEqual(len(cid1), 12)
        self.assertTrue(all(c in "0123456789abcdef" for c in cid1))

        # Should be unique
        self.assertNotEqual(cid1, cid2)

    def test_correlation_context_basic(self):
        """Test basic correlation context usage"""
        # Before context, should be None
        self.assertIsNone(get_correlation_id())

        with CorrelationContext() as cid:
            # Inside context, should have a correlation ID
            self.assertIsNotNone(get_correlation_id())
            self.assertEqual(get_correlation_id(), cid)
            self.assertEqual(len(cid), 12)

        # After context, should be None again
        self.assertIsNone(get_correlation_id())

    def test_correlation_context_with_prefix(self):
        """Test correlation context with custom prefix"""
        with CorrelationContext("swap") as cid:
            self.assertTrue(cid.startswith("swap_"))
            self.assertEqual(get_correlation_id(), cid)

    def test_nested_correlation_context(self):
        """Test nested correlation contexts"""
        with CorrelationContext("outer") as outer_cid:
            self.assertEqual(get_correlation_id(), outer_cid)

            with CorrelationContext("inner") as inner_cid:
                # Inner context should override
                self.assertEqual(get_correlation_id(), inner_cid)
                self.assertNotEqual(get_correlation_id(), outer_cid)

            # After inner context, should restore outer
            self.assertEqual(get_correlation_id(), outer_cid)

        # After all contexts, should be None
        self.assertIsNone(get_correlation_id())

    def test_set_correlation_id_manual(self):
        """Test manual correlation ID setting"""
        token = set_correlation_id("test_cid_12345")
        try:
            self.assertEqual(get_correlation_id(), "test_cid_12345")
        finally:
            # Reset
            from dex_adapter_universal.infra.retry import _correlation_id
            _correlation_id.reset(token)

        self.assertIsNone(get_correlation_id())


class TestExecuteSwapWithRetry(unittest.TestCase):
    """Tests for execute_swap_with_retry function"""

    @patch("dex_adapter_universal.infra.retry.global_config")
    def test_success_on_first_attempt(self, mock_config):
        """Operation that succeeds on first attempt"""
        mock_config.tx.swap_max_retries = 5
        mock_config.tx.retry_delay = 0.1

        call_count = [0]

        def mock_operation(attempt: int) -> TxResult:
            call_count[0] += 1
            return TxResult.success("test_signature")

        result = execute_swap_with_retry(mock_operation, "swap(SOL->USDC)")

        self.assertTrue(result.is_success)
        self.assertEqual(result.signature, "test_signature")
        self.assertEqual(call_count[0], 1)

    @patch("dex_adapter_universal.infra.retry.global_config")
    @patch("dex_adapter_universal.infra.retry.time.sleep")
    def test_success_after_retries(self, mock_sleep, mock_config):
        """Operation that succeeds after retries"""
        mock_config.tx.swap_max_retries = 5
        mock_config.tx.retry_delay = 0.1

        call_count = [0]

        def mock_operation(attempt: int) -> TxResult:
            call_count[0] += 1
            if attempt < 2:
                return TxResult.failed("timeout error", recoverable=True)
            return TxResult.success("test_signature")

        result = execute_swap_with_retry(mock_operation, "swap(SOL->USDC)")

        self.assertTrue(result.is_success)
        self.assertEqual(call_count[0], 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("dex_adapter_universal.infra.retry.global_config")
    @patch("dex_adapter_universal.infra.retry.time.sleep")
    def test_timeout_result_triggers_retry(self, mock_sleep, mock_config):
        """Timeout result should trigger retry with fresh quote"""
        mock_config.tx.swap_max_retries = 3
        mock_config.tx.retry_delay = 0.1

        call_count = [0]

        def mock_operation(attempt: int) -> TxResult:
            call_count[0] += 1
            if attempt == 0:
                return TxResult.timeout("pending_sig_1")
            return TxResult.success("success_sig")

        result = execute_swap_with_retry(mock_operation, "swap(SOL->USDC)")

        self.assertTrue(result.is_success)
        self.assertEqual(call_count[0], 2)

    @patch("dex_adapter_universal.infra.retry.global_config")
    def test_non_recoverable_error_no_retry(self, mock_config):
        """Non-recoverable error should not trigger retry"""
        mock_config.tx.swap_max_retries = 5
        mock_config.tx.retry_delay = 0.1

        call_count = [0]

        def mock_operation(attempt: int) -> TxResult:
            call_count[0] += 1
            return TxResult.failed("contract reverted", recoverable=False)

        result = execute_swap_with_retry(mock_operation, "swap(SOL->USDC)")

        self.assertFalse(result.is_success)
        self.assertEqual(call_count[0], 1)

    @patch("dex_adapter_universal.infra.retry.global_config")
    @patch("dex_adapter_universal.infra.retry.time.sleep")
    def test_slippage_exception_retry(self, mock_sleep, mock_config):
        """Slippage exceptions should trigger retry with fresh quote"""
        mock_config.tx.swap_max_retries = 3
        mock_config.tx.retry_delay = 0.1

        call_count = [0]

        def mock_operation(attempt: int) -> TxResult:
            call_count[0] += 1
            if attempt == 0:
                raise Exception("Slippage exceeded maximum tolerance")
            return TxResult.success("test_signature")

        result = execute_swap_with_retry(mock_operation, "swap(SOL->USDC)")

        self.assertTrue(result.is_success)
        self.assertEqual(call_count[0], 2)

    @patch("dex_adapter_universal.infra.retry.global_config")
    @patch("dex_adapter_universal.infra.retry.time.sleep")
    def test_max_retries_returns_timeout_if_signature_exists(self, mock_sleep, mock_config):
        """If max retries exceeded with a signature, return timeout result"""
        mock_config.tx.swap_max_retries = 2
        mock_config.tx.retry_delay = 0.1

        def mock_operation(attempt: int) -> TxResult:
            return TxResult.timeout(f"sig_{attempt}")

        result = execute_swap_with_retry(mock_operation, "swap(SOL->USDC)")

        # Should return timeout with last signature
        self.assertTrue(result.is_timeout)
        self.assertIn("sig_", result.signature)

    @patch("dex_adapter_universal.infra.retry.global_config")
    def test_attempt_number_passed_to_operation(self, mock_config):
        """Verify attempt number is correctly passed to the operation"""
        mock_config.tx.swap_max_retries = 3
        mock_config.tx.retry_delay = 0.1

        attempts_received = []

        def mock_operation(attempt: int) -> TxResult:
            attempts_received.append(attempt)
            if attempt < 2:
                return TxResult.failed("error", recoverable=True)
            return TxResult.success("test_signature")

        with patch("dex_adapter_universal.infra.retry.time.sleep"):
            result = execute_swap_with_retry(mock_operation, "swap(SOL->USDC)")

        self.assertEqual(attempts_received, [0, 1, 2])
        self.assertTrue(result.is_success)


class TestExecuteWithRetrySwapConfig(unittest.TestCase):
    """Tests for execute_with_retry with swap config flag"""

    @patch("dex_adapter_universal.infra.retry.global_config")
    def test_uses_lp_retries_by_default(self, mock_config):
        """Default should use LP max retries"""
        mock_config.tx.lp_max_retries = 3
        mock_config.tx.swap_max_retries = 10
        mock_config.tx.retry_delay = 0.1

        mock_operation = MagicMock(return_value=TxResult.failed("error", recoverable=True))

        with patch("dex_adapter_universal.infra.retry.time.sleep"):
            execute_with_retry(mock_operation, "test_operation")

        # Should use lp_max_retries (3)
        self.assertEqual(mock_operation.call_count, 3)

    @patch("dex_adapter_universal.infra.retry.global_config")
    def test_uses_swap_retries_with_flag(self, mock_config):
        """Should use swap max retries when flag is set"""
        mock_config.tx.lp_max_retries = 3
        mock_config.tx.swap_max_retries = 5
        mock_config.tx.retry_delay = 0.1

        mock_operation = MagicMock(return_value=TxResult.failed("error", recoverable=True))

        with patch("dex_adapter_universal.infra.retry.time.sleep"):
            execute_with_retry(mock_operation, "test_operation", use_swap_config=True)

        # Should use swap_max_retries (5)
        self.assertEqual(mock_operation.call_count, 5)


if __name__ == "__main__":
    unittest.main()
