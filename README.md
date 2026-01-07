# DEX Adapter

多链 DEX 协议统一接口。提供 Solana、Ethereum、BSC 上的流动性管理和代币交换的原子操作。

## 支持的链和协议

| 链 | 交换聚合器 | LP 协议 |
|---|----------|--------|
| **Solana** | Jupiter | Raydium CLMM, Meteora DLMM |
| **Ethereum** | 1inch | - |
| **BSC** | 1inch | - |

## 安装

```bash
pip install -e .
```

依赖：
- `solders` - Solana SDK
- `httpx` - HTTP 客户端
- `web3` - EVM SDK（用于 ETH/BSC）
- `python-dotenv` - 环境配置

## 项目结构

```
dex_adapter/
├── dex_adapter/              # 主包
│   ├── __init__.py           # 公共导出
│   ├── client.py             # DexClient 入口
│   ├── config.py             # 配置管理
│   │
│   ├── modules/              # 功能模块
│   │   ├── wallet.py         # 余额查询（Solana）
│   │   ├── market.py         # 池/价格查询（Solana）
│   │   ├── swap.py           # 多链交换
│   │   └── liquidity.py      # LP 操作（Solana）
│   │
│   ├── protocols/            # 协议适配器
│   │   ├── base.py           # ProtocolAdapter 抽象基类
│   │   ├── registry.py       # 协议注册表
│   │   ├── raydium/          # Raydium CLMM
│   │   ├── meteora/          # Meteora DLMM
│   │   ├── jupiter/          # Jupiter 交换
│   │   └── oneinch/          # 1inch 交换（ETH/BSC）
│   │
│   ├── infra/                # 基础设施
│   │   ├── rpc.py            # Solana RPC 客户端
│   │   ├── solana_signer.py  # Solana 签名
│   │   ├── evm_signer.py     # EVM 签名（web3.py）
│   │   └── tx_builder.py     # Solana 交易构建
│   │
│   ├── types/                # 类型定义
│   │   ├── common.py         # Token
│   │   ├── pool.py           # Pool
│   │   ├── position.py       # Position
│   │   ├── price.py          # PriceRange, RangeMode
│   │   ├── result.py         # TxResult, QuoteResult
│   │   ├── solana_tokens.py  # Solana 代币注册表
│   │   └── evm_tokens.py     # ETH/BSC 代币注册表
│   │
│   └── errors/               # 错误定义
│       └── exceptions.py     # 所有异常类
│
└── test/                     # 测试
    ├── unit_test/            # 单元测试
    ├── module_test/          # 集成测试
    └── run_all_tests.py      # 测试运行器
```

## 快速开始

### Solana（Jupiter + Raydium/Meteora）

```python
from decimal import Decimal
from dex_adapter import DexClient, PriceRange

# 使用密钥文件初始化客户端
client = DexClient(
    rpc_url="https://api.mainnet-beta.solana.com",
    keypair_path="/path/to/keypair.json",
)

# 查询余额
print(f"SOL: {client.wallet.sol_balance()}")
print(f"USDC: {client.wallet.balance('USDC')}")

# SOL 兑换 USDC
result = client.swap.swap(
    from_token="SOL",
    to_token="USDC",
    amount=Decimal("0.1"),
    slippage_bps=50,
    chain="solana",
)
print(f"交换: {result.signature}")

# 在 Raydium 开启 LP 仓位
pool = client.market.pool_by_symbol("SOL/USDC", dex="raydium")
result = client.liquidity.open(
    pool=pool,
    price_range=PriceRange.percent(0.02),  # +/- 2%
    amount0=Decimal("0.1"),
    amount1=Decimal("10"),
)
```

### Ethereum / BSC（1inch）

```python
from decimal import Decimal
from dex_adapter import SwapModule, EVMSigner

# 从私钥创建 EVM 签名器
signer = EVMSigner.from_env()  # 使用 EVM_PRIVATE_KEY 环境变量

# 创建交换模块
swap = SwapModule(evm_signer=signer)

# 在 Ethereum 上 ETH 兑换 USDC
result = swap.swap(
    from_token="ETH",
    to_token="USDC",
    amount=Decimal("0.1"),
    slippage_bps=50,
    chain="eth",
)
print(f"TX: {result.signature}")

# 在 BSC 上 BNB 兑换 USDT
result = swap.swap(
    from_token="BNB",
    to_token="USDT",
    amount=Decimal("0.1"),
    slippage_bps=50,
    chain="bsc",
)
```

### 多链交换

```python
from dex_adapter import DexClient, SwapModule, EVMSigner

# 初始化所有链
client = DexClient(
    rpc_url="https://api.mainnet-beta.solana.com",
    keypair_path="/path/to/keypair.json",
)
evm_signer = EVMSigner.from_env()
client.swap.set_evm_signer(evm_signer)

# 在任意链上交换
client.swap.swap("SOL", "USDC", Decimal("1"), chain="solana")  # Jupiter
client.swap.swap("ETH", "USDC", Decimal("0.1"), chain="eth")   # 1inch
client.swap.swap("BNB", "USDT", Decimal("1"), chain="bsc")     # 1inch
```

## 配置

复制 `.env.example` 到 `.env` 并配置：

```bash
# Solana
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
SOLANA_KEYPAIR_PATH=/path/to/keypair.json

# EVM（ETH/BSC）
ONEINCH_API_KEY=your_1inch_api_key
EVM_PRIVATE_KEY=your_evm_private_key
```

## DexClient 模块

### wallet - 余额操作（Solana）
```python
client.wallet.sol_balance()          # SOL 余额
client.wallet.balance("USDC")        # 代币余额
client.wallet.balances()             # 所有余额
client.wallet.token_accounts()       # 列出代币账户
```

### market - 池/价格查询（Solana）
```python
client.market.pool(address)                    # 通过地址获取池
client.market.pool_by_symbol("SOL/USDC", dex)  # 通过交易对获取
client.market.price("SOL/USDC")                # 当前价格
```

### swap - 多链代币交换
```python
# 获取报价
quote = client.swap.quote("SOL", "USDC", amount, chain="solana")
quote = client.swap.quote("ETH", "USDC", amount, chain="eth")

# 执行交换
result = client.swap.swap("SOL", "USDC", amount, chain="solana")
result = client.swap.swap("ETH", "USDC", amount, chain="eth")
result = client.swap.swap("BNB", "USDT", amount, chain="bsc")
```

### liquidity - LP 操作（Solana）
```python
# 开启仓位
result = client.liquidity.open(pool, price_range, amount0, amount1)

# 管理仓位
client.liquidity.add(position, amount0, amount1)
client.liquidity.remove(position, percent=50)
client.liquidity.claim(position)
client.liquidity.close(position)

# 查询仓位
positions = client.liquidity.positions()
positions = client.liquidity.positions(pool_address)
```

## 类型定义

### PriceRange（价格范围）
```python
from dex_adapter import PriceRange

PriceRange.one_tick()              # 最窄范围
PriceRange.percent(0.02)           # +/- 2%
PriceRange.bps(200)                # +/- 200 基点（2%）
PriceRange.absolute(95.0, 105.0)   # 绝对价格
```

### 核心类型
```python
from dex_adapter import Token, Pool, Position, TxResult, QuoteResult

# TxResult
result.status       # TxStatus.SUCCESS, FAILED, PENDING, TIMEOUT
result.signature    # 交易签名/哈希
result.is_success   # 布尔快捷方式

# QuoteResult
quote.from_amount   # 输入金额（原始值）
quote.to_amount     # 输出金额（原始值）
quote.price_impact_percent
```

## 错误处理

```python
from dex_adapter.errors import (
    DexAdapterError,    # 基础异常
    RpcError,           # RPC 问题
    SlippageExceeded,   # 滑点过高
    PoolUnavailable,    # 池不存在
    InsufficientFunds,  # 余额不足
    PositionNotFound,   # 仓位不存在
)

try:
    result = client.swap.swap("SOL", "USDC", amount)
except SlippageExceeded as e:
    print(f"滑点超出: {e}")
except InsufficientFunds as e:
    print(f"需要 {e.required}，拥有 {e.available}")
except DexAdapterError as e:
    if e.recoverable:
        # 可以重试
        pass
```

## 测试

```bash
# 运行单元测试
python test/run_all_tests.py --unit

# 运行集成测试（需要配置）
python test/run_all_tests.py --module

# 运行所有测试
python test/run_all_tests.py --all

# 快速导入测试
python test/run_all_tests.py --quick
```

**警告**：集成测试执行真实交易并消耗真实代币！

## 设计原则

1. **多链支持** - Solana、Ethereum、BSC 统一接口
2. **原子操作** - 每个方法是一个完整的单一操作
3. **协议无关** - 跨不同 DEX 协议的相同 API
4. **错误恢复** - 错误指示是否可以重试
5. **类型安全** - 所有数据结构使用 dataclass
