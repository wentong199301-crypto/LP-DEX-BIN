"""
Result type definitions for transactions and quotes
"""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Optional, List


class TxStatus(Enum):
    """Transaction status"""
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    PENDING = "pending"
    SKIPPED = "skipped"  # No action needed (e.g., nothing to claim)


@dataclass
class TxResult:
    """
    Transaction execution result

    Attributes:
        status: Transaction status
        signature: Transaction signature (base58)
        error: Error message if failed
        recoverable: Whether the error is recoverable (can retry)
        error_code: Error code for programmatic handling
        fee_lamports: Transaction fee in lamports
        slot: Slot number when confirmed
        block_time: Block timestamp
        logs: Transaction logs
    """
    status: TxStatus
    signature: Optional[str] = None
    error: Optional[str] = None
    recoverable: bool = False
    error_code: Optional[str] = None
    fee_lamports: Optional[int] = None
    slot: Optional[int] = None
    block_time: Optional[int] = None
    logs: List[str] = field(default_factory=list)

    @property
    def is_success(self) -> bool:
        return self.status == TxStatus.SUCCESS

    @property
    def is_failed(self) -> bool:
        return self.status == TxStatus.FAILED

    @property
    def is_timeout(self) -> bool:
        return self.status == TxStatus.TIMEOUT

    @property
    def is_skipped(self) -> bool:
        return self.status == TxStatus.SKIPPED

    @property
    def fee_sol(self) -> Optional[float]:
        """Fee in SOL"""
        if self.fee_lamports is None:
            return None
        return self.fee_lamports / 1e9

    @classmethod
    def success(cls, signature: str, fee_lamports: int = 0, **kwargs) -> "TxResult":
        """Create successful result"""
        return cls(
            status=TxStatus.SUCCESS,
            signature=signature,
            fee_lamports=fee_lamports,
            **kwargs
        )

    @classmethod
    def failed(cls, error: str, signature: str = None, **kwargs) -> "TxResult":
        """Create failed result"""
        return cls(
            status=TxStatus.FAILED,
            signature=signature,
            error=error,
            **kwargs
        )

    @classmethod
    def timeout(cls, signature: str = None, **kwargs) -> "TxResult":
        """Create timeout result (recoverable - can check on-chain status)"""
        return cls(
            status=TxStatus.TIMEOUT,
            signature=signature,
            error="Transaction confirmation timeout",
            recoverable=True,
            error_code="2003",
            **kwargs
        )

    @classmethod
    def skipped(cls, reason: str = "No action needed", **kwargs) -> "TxResult":
        """Create skipped result (no transaction was needed)"""
        return cls(
            status=TxStatus.SKIPPED,
            signature=None,
            error=reason,
            **kwargs
        )

    def __str__(self) -> str:
        if self.is_success:
            sig_display = f"{self.signature[:16]}..." if self.signature else "no signature"
            return f"TxResult(SUCCESS, {sig_display})"
        return f"TxResult({self.status.value}, error={self.error})"


@dataclass
class QuoteResult:
    """
    Swap quote result

    Attributes:
        from_token: Input token mint
        to_token: Output token mint
        from_amount: Input amount (raw)
        to_amount: Output amount (raw)
        price_impact: Price impact as decimal (0.01 = 1%)
        fee_amount: Fee amount in input token
        route: Swap route (list of pool addresses or DEX names)
        min_to_amount: Minimum output after slippage
        slippage_bps: Applied slippage in basis points
        raw_response: Raw API response data (for swap transaction building)
    """
    from_token: str
    to_token: str
    from_amount: int
    to_amount: int
    price_impact: Decimal = Decimal(0)
    fee_amount: int = 0
    route: List[str] = field(default_factory=list)
    min_to_amount: Optional[int] = None
    slippage_bps: int = 50
    raw_response: Optional[dict] = None

    @property
    def exchange_rate(self) -> Decimal:
        """Output per input"""
        if self.from_amount == 0:
            return Decimal(0)
        return Decimal(self.to_amount) / Decimal(self.from_amount)

    @property
    def price_impact_percent(self) -> float:
        """Price impact as percentage"""
        return float(self.price_impact * 100)

    def __str__(self) -> str:
        return f"Quote({self.from_amount} -> {self.to_amount}, impact={self.price_impact_percent:.2f}%)"


@dataclass
class OpenPositionResult:
    """
    Result of opening an LP position

    Attributes:
        tx_result: Transaction result
        position_id: New position ID
        nft_mint: NFT mint (Raydium)
        position_address: Position address (Meteora)
        amount0_deposited: Actual token0 amount deposited
        amount1_deposited: Actual token1 amount deposited
    """
    tx_result: TxResult
    position_id: str
    nft_mint: Optional[str] = None
    position_address: Optional[str] = None
    amount0_deposited: Optional[Decimal] = None
    amount1_deposited: Optional[Decimal] = None

    @property
    def is_success(self) -> bool:
        return self.tx_result.is_success


@dataclass
class ClosePositionResult:
    """
    Result of closing an LP position

    Attributes:
        tx_result: Transaction result
        amount0_received: Token0 amount received
        amount1_received: Token1 amount received
        fees_collected: Fees collected by token mint
        rewards_collected: Rewards collected by token mint
    """
    tx_result: TxResult
    amount0_received: Decimal = Decimal(0)
    amount1_received: Decimal = Decimal(0)
    fees_collected: dict = field(default_factory=dict)
    rewards_collected: dict = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        return self.tx_result.is_success
