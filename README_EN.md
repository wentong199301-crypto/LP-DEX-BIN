# DEX Adapter

Unified interface for multi-chain DEX protocols. Provides atomic operations for liquidity management and token swaps across Solana, Ethereum, and BSC.

## Supported Chains & Protocols

| Chain | Swap Aggregator | LP Protocols |
|-------|-----------------|--------------|
| **Solana** | Jupiter | Raydium CLMM, Meteora DLMM |
| **Ethereum** | 1inch | - |
| **BSC** | 1inch | - |

## Installation

```bash
pip install -e .
```

Dependencies:
- `solders` - Solana SDK
- `httpx` - HTTP client
- `web3` - EVM SDK (for ETH/BSC)
- `python-dotenv` - Environment configuration

## Project Structure

```
dex_adapter/
├── dex_adapter/              # Main package
│   ├── __init__.py           # Public exports
│   ├── client.py             # DexClient entry point
│   ├── config.py             # Configuration management
│   │
│   ├── modules/              # Functional modules
│   │   ├── wallet.py         # Balance queries (Solana)
│   │   ├── market.py         # Pool/price queries (Solana)
│   │   ├── swap.py           # Multi-chain swaps
│   │   └── liquidity.py      # LP operations (Solana)
│   │
│   ├── protocols/            # Protocol adapters
│   │   ├── base.py           # ProtocolAdapter ABC
│   │   ├── registry.py       # Protocol registry
│   │   ├── raydium/          # Raydium CLMM
│   │   ├── meteora/          # Meteora DLMM
│   │   ├── jupiter/          # Jupiter swap
│   │   └── oneinch/          # 1inch swap (ETH/BSC)
│   │
│   ├── infra/                # Infrastructure
│   │   ├── rpc.py            # Solana RPC client
│   │   ├── solana_signer.py  # Solana signing
│   │   ├── evm_signer.py     # EVM signing (web3.py)
│   │   └── tx_builder.py     # Solana tx construction
│   │
│   ├── types/                # Type definitions
│   │   ├── common.py         # Token
│   │   ├── pool.py           # Pool
│   │   ├── position.py       # Position
│   │   ├── price.py          # PriceRange, RangeMode
│   │   ├── result.py         # TxResult, QuoteResult
│   │   ├── solana_tokens.py  # Solana token registry
│   │   └── evm_tokens.py     # ETH/BSC token registry
│   │
│   └── errors/               # Error definitions
│       └── exceptions.py     # All exception classes
│
└── test/                     # Tests
    ├── unit_test/            # Unit tests
    ├── module_test/          # Integration tests
    └── run_all_tests.py      # Test runner
```

## Quick Start

### Solana (Jupiter + Raydium/Meteora)

```python
from decimal import Decimal
from dex_adapter import DexClient, PriceRange

# Initialize client with keypair file
client = DexClient(
    rpc_url="https://api.mainnet-beta.solana.com",
    keypair_path="/path/to/keypair.json",
)

# Check balances
print(f"SOL: {client.wallet.sol_balance()}")
print(f"USDC: {client.wallet.balance('USDC')}")

# Swap SOL to USDC
result = client.swap.swap(
    from_token="SOL",
    to_token="USDC",
    amount=Decimal("0.1"),
    slippage_bps=50,
    chain="solana",
)
print(f"Swap: {result.signature}")

# Open LP position on Raydium
pool = client.market.pool_by_symbol("SOL/USDC", dex="raydium")
result = client.liquidity.open_position(
    pool=pool,
    price_range=PriceRange.percent(0.02),  # +/- 2%
    amount0=Decimal("0.1"),
    amount1=Decimal("10"),
)
```

### Ethereum / BSC (1inch)

```python
from decimal import Decimal
from dex_adapter import SwapModule, EVMSigner

# Create EVM signer from private key
signer = EVMSigner.from_env()  # Uses EVM_PRIVATE_KEY env var

# Create swap module
swap = SwapModule(evm_signer=signer)

# Swap ETH to USDC on Ethereum
result = swap.swap(
    from_token="ETH",
    to_token="USDC",
    amount=Decimal("0.1"),
    slippage_bps=50,
    chain="eth",
)
print(f"TX: {result.signature}")

# Swap BNB to USDT on BSC
result = swap.swap(
    from_token="BNB",
    to_token="USDT",
    amount=Decimal("0.1"),
    slippage_bps=50,
    chain="bsc",
)
```

### Multi-Chain Swaps

```python
from dex_adapter import DexClient, SwapModule, EVMSigner

# Initialize for all chains
client = DexClient(
    rpc_url="https://api.mainnet-beta.solana.com",
    keypair_path="/path/to/keypair.json",
)
evm_signer = EVMSigner.from_env()
client.swap.set_evm_signer(evm_signer)

# Swap on any chain
client.swap.swap("SOL", "USDC", Decimal("1"), chain="solana")  # Jupiter
client.swap.swap("ETH", "USDC", Decimal("0.1"), chain="eth")   # 1inch
client.swap.swap("BNB", "USDT", Decimal("1"), chain="bsc")     # 1inch
```

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
# Solana
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
SOLANA_KEYPAIR_PATH=/path/to/keypair.json

# EVM (ETH/BSC)
ONEINCH_API_KEY=your_1inch_api_key
EVM_PRIVATE_KEY=your_evm_private_key
```

## DexClient Modules

### wallet - Balance Operations (Solana)
```python
client.wallet.sol_balance()          # SOL balance
client.wallet.balance("USDC")        # Token balance
client.wallet.balances()             # All balances
client.wallet.token_accounts()       # List token accounts
```

### market - Pool/Price Queries (Solana)
```python
client.market.pool(address)                    # Get pool by address
client.market.pool_by_symbol("SOL/USDC", dex)  # Get by symbol
client.market.price("SOL/USDC")                # Current price
```

### swap - Multi-Chain Token Swaps
```python
# Get quote
quote = client.swap.quote("SOL", "USDC", amount, chain="solana")
quote = client.swap.quote("ETH", "USDC", amount, chain="eth")

# Execute swap
result = client.swap.swap("SOL", "USDC", amount, chain="solana")
result = client.swap.swap("ETH", "USDC", amount, chain="eth")
result = client.swap.swap("BNB", "USDT", amount, chain="bsc")
```

### liquidity - LP Operations (Solana)
```python
# Open position
result = client.liquidity.open_position(pool, price_range, amount0, amount1)

# Manage position
client.liquidity.add_liquidity(position, amount0, amount1)
client.liquidity.remove_liquidity(position, percent=50)
client.liquidity.claim_fees(position)
client.liquidity.close_position(position)

# Query positions
positions = client.liquidity.positions()
positions = client.liquidity.positions(pool_address)
```

## Type Definitions

### PriceRange
```python
from dex_adapter import PriceRange

PriceRange.one_tick()              # Narrowest range
PriceRange.percent(0.02)           # +/- 2%
PriceRange.bps(200)                # +/- 200 bps (2%)
PriceRange.absolute(95.0, 105.0)   # Absolute prices
```

### Core Types
```python
from dex_adapter import Token, Pool, Position, TxResult, QuoteResult

# TxResult
result.status       # TxStatus.SUCCESS, FAILED, PENDING, TIMEOUT
result.signature    # Transaction signature/hash
result.is_success   # Boolean shortcut

# QuoteResult
quote.from_amount   # Input amount (raw)
quote.to_amount     # Output amount (raw)
quote.price_impact_percent
```

## Error Handling

```python
from dex_adapter.errors import (
    DexAdapterError,    # Base exception
    RpcError,           # RPC issues
    SlippageExceeded,   # Slippage too high
    PoolUnavailable,    # Pool not found
    InsufficientFunds,  # Not enough balance
    PositionNotFound,   # Position not found
)

try:
    result = client.swap.swap("SOL", "USDC", amount)
except SlippageExceeded as e:
    print(f"Slippage exceeded: {e}")
except InsufficientFunds as e:
    print(f"Need {e.required}, have {e.available}")
except DexAdapterError as e:
    if e.recoverable:
        # Can retry
        pass
```

## Testing

```bash
# Run unit tests
python test/run_all_tests.py --unit

# Run integration tests (requires config)
python test/run_all_tests.py --module

# Run all tests
python test/run_all_tests.py --all

# Quick import test
python test/run_all_tests.py --quick
```

**Warning**: Integration tests execute REAL transactions and spend REAL tokens!

## Design Principles

1. **Multi-Chain** - Unified interface for Solana, Ethereum, BSC
2. **Atomic Operations** - Each method is a single, complete operation
3. **Protocol Agnostic** - Same API across different DEX protocols
4. **Error Recovery** - Errors indicate whether retry is possible
5. **Type Safety** - Dataclasses for all data structures
