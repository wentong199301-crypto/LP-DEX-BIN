# DEX Adapter Universal

多链 DEX 协议统一接口。提供 Solana、Ethereum、BSC 上的流动性管理和代币交换的原子操作。

## 支持的链和协议

| 链 | 交换聚合器 | LP 协议 |
|---|----------|--------|
| **Solana** | Jupiter | Raydium CLMM, Meteora DLMM |
| **Ethereum** | 1inch | Uniswap V3 |
| **BSC** | 1inch | PancakeSwap V3 |

## 安装

```bash
pip install -e .
```

依赖：
- `solders` - Solana SDK
- `httpx` - HTTP 客户端
- `web3` - EVM SDK（用于 ETH/BSC）
- `python-dotenv` - 环境配置
- `eth-account` - EVM 签名

## 目录

- [快速开始](#快速开始)
- [项目结构](#项目结构)
- [配置参考](#配置参考)
- [费用说明](#费用说明)
- [DexClient 模块](#dexclient-模块)
- [类型定义](#类型定义)
- [错误处理](#错误处理)
- [测试](#测试)
- [最近更新](#最近更新)

---

## 快速开始

### Solana（Jupiter + Raydium/Meteora）

```python
from decimal import Decimal
from dex_adapter_universal import DexClient, PriceRange

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
result = client.lp.open(
    pool=pool,
    price_range=PriceRange.percent(0.02),  # +/- 2%
    amount0=Decimal("0.1"),
    amount1=Decimal("10"),
)
```

### Ethereum / BSC（1inch + Uniswap/PancakeSwap）

```python
from decimal import Decimal
from dex_adapter_universal import SwapModule, EVMSigner

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
from dex_adapter_universal import DexClient, SwapModule, EVMSigner

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

---

## 项目结构

```
dex_adapter_universal/
├── dex_adapter_universal/              # 主包
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
│   │   ├── oneinch/          # 1inch 交换（ETH/BSC）
│   │   ├── uniswap/          # Uniswap V3（ETH）
│   │   └── pancakeswap/      # PancakeSwap V3（BSC）
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

---

## 配置参考

### 基础配置

复制 `.env.example` 到 `.env` 并配置：

```bash
# Solana RPC
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
SOLANA_KEYPAIR_PATH=/path/to/keypair.json
# 或使用私钥
# SOLANA_PRIVATE_KEY=your_base58_private_key

# EVM（ETH/BSC）
ETH_RPC_URL=https://eth.llamarpc.com
BSC_RPC_URL=https://bsc-dataseed.binance.org
EVM_PRIVATE_KEY=your_evm_private_key

# API Keys
ONEINCH_API_KEY=your_1inch_api_key
```

### Solana 交易配置

```bash
# Swap 操作 Compute Budget
TX_COMPUTE_UNITS=200000           # Compute Unit 限制 (默认: 200,000)
TX_COMPUTE_UNIT_PRICE=1000        # Priority Fee (microlamports/CU, 默认: 1,000)

# LP 操作 Compute Budget (需要更高)
TX_LP_COMPUTE_UNITS=600000        # LP Compute Unit 限制 (默认: 600,000)
TX_LP_COMPUTE_UNIT_PRICE=1000     # LP Priority Fee (默认: 1,000)

# 交易确认
TX_CONFIRMATION_TIMEOUT=90.0      # 确认超时秒数 (默认: 90)
TX_MAX_RETRIES=3                  # 最大重试次数 (默认: 3)
TX_RETRY_DELAY=2.0                # 重试间隔秒数 (默认: 2)
TX_SKIP_PREFLIGHT=false           # 跳过预检 (默认: false)
```

### EVM Gas 配置

```bash
# PancakeSwap (BSC)
PANCAKESWAP_GAS_LIMIT_MULTIPLIER=1.2    # Gas 估算缓冲 (默认: 1.2)
PANCAKESWAP_PRIORITY_FEE_GWEI=0.1       # Priority Fee Gwei (默认: 0.1)

# Uniswap (Ethereum)
UNISWAP_GAS_LIMIT_MULTIPLIER=1.2        # Gas 估算缓冲 (默认: 1.2)
UNISWAP_PRIORITY_FEE_GWEI=0.1           # Priority Fee Gwei (默认: 0.1)

# 1inch
ONEINCH_GAS_LIMIT_MULTIPLIER=1.1        # Gas 估算缓冲 (默认: 1.1)
ONEINCH_PRIORITY_FEE_GWEI=0.1           # Priority Fee Gwei (默认: 0.1)
```

---

## 费用说明

### 费用定义

**费用 (Fee)**: 付出后不会退回的钱
- ✅ Gas 费 (EVM 链)
- ✅ Compute Unit 费用 (Solana)
- ✅ 交易签名费 (Solana base fee)

**不计入费用**:
- ❌ 账户租金押金 (Solana, 关仓时退回)
- ❌ Token Approve 的 allowance (不消耗资金)

### UI 反馈费用 vs 程序计算费用

| DEX | UI 反馈 | 程序实测 | 差异分析 |
|-----|---------|---------|---------|
| Raydium (Solana) | ~$0.03 | ~$0.005 | 可能包含账户租金押金 |
| PancakeSwap (BSC) | ~$0.03 | **$0.023** | 实测：开仓$0.017+关仓$0.006 |
| Uniswap (ETH) | ~$0.8 | ~$0.84 | 非常接近 |
| Meteora (Solana) | 未测试 | ~$0.003 | - |

#### PancakeSwap 实测详情 (2026-01-19)

| 操作 | 交易哈希 | Gas Used | Fee (BNB) | Fee (USD) |
|------|----------|----------|-----------|-----------|
| 开仓 | `57ccfff6...` | 484,042 | 0.0000242 | $0.017 |
| 关仓 | `51d831cc...` | 165,762 | 0.0000083 | $0.006 |
| **总计** | - | 649,804 | 0.0000325 | **$0.023** |

*测试池: USD1/WBNB 0.05% (0x4a3218606AF9B4728a9F187E1c1a8c07fBC172a9)*

### 关键发现

#### 1. Raydium 多步骤关仓问题 ⚠️

**程序实现** (`dex_adapter_universal/modules/liquidity.py`):

```python
if position.pool.dex == "raydium" and hasattr(adapter, "generate_close_position_steps"):
    return self._execute_multi_step_close(position, adapter)
```

关仓分为 3 笔独立交易：
- Step 1: Remove all liquidity (移除流动性)
- Step 2: Claim fees/rewards (领取手续费/奖励)
- Step 3: Close position (关闭仓位，销毁 NFT)

**每笔交易都有独立的 base fee (5000 lamports)**

| 操作 | 交易数 | 费用 |
|------|-------|-----|
| 开仓 | 1 笔 | ~$0.0013 |
| 关仓 (程序) | 3 笔 | ~$0.004 |
| 关仓 (UI 预计) | 1 笔 | ~$0.0013 |

#### 2. 账户租金押金 (SOL) - 不是费用

Raydium 开仓时需要创建：
- NFT mint 账户: ~0.00289 SOL (~$0.75)
- Position PDA: ~0.00203 SOL (~$0.53)
- ATA 账户: ~0.00203 SOL (如果不存在)

**总押金: ~0.01 SOL (~$2.6)**

这些押金在**关仓时会退回**，不应计入费用。

但是如果用户的统计方式不同，可能会将这部分计入"费用"。

#### 3. EVM Approve 交易

程序首次交互时会执行 approve 交易：
- 每个代币: ~46,000 gas
- 两个代币: ~92,000 gas

如果 UI 使用 Permit2 签名，则无需额外交易。

### 费用配置参数

#### Solana (config.py)

```python
# LP 操作 compute budget
lp_compute_units: 600,000      # CU 限制
lp_compute_unit_price: 1,000   # microlamports/CU (priority fee)
```

Priority fee 计算:
- 600,000 CU × 1,000 μlamports/CU = 600 lamports = $0.000156

#### EVM (config.py)

```python
# PancakeSwap
gas_limit_multiplier: 1.2   # 额外 20% 缓冲
priority_fee_gwei: 0.1      # 最低 priority fee

# Uniswap  
gas_limit_multiplier: 1.2
priority_fee_gwei: 0.1
```

### Solana 费用结构

```
总费用 = Base Fee + Priority Fee

Base Fee = 5,000 lamports/signature (固定)
Priority Fee = Compute Units × CU Price / 1,000,000

示例 (LP 操作):
= 5,000 + (600,000 × 1,000 / 1,000,000)
= 5,000 + 600 lamports
= 5,600 lamports
≈ 0.0000056 SOL
≈ $0.0015 (按 $260/SOL)
```

**账户租金押金 (关仓时退回)**:

| 账户类型 | 租金 (SOL) | 说明 |
|---------|-----------|------|
| Token Account (ATA) | ~0.00203 | 首次创建代币账户 |
| NFT Mint (Raydium) | ~0.00289 | 仓位 NFT |
| Position PDA | ~0.00203 | 仓位数据账户 |

### EVM 费用结构

**Ethereum (EIP-1559)**:
```
总费用 = Gas Used × (Base Fee + Priority Fee)

- Base Fee: 由网络动态决定
- Priority Fee: 可配置 (默认 0.1 Gwei)
- Max Fee: Base Fee × 2 + Priority Fee (程序设置)
```

**BSC (Legacy)**:
```
总费用 = Gas Used × Gas Price

- Gas Price: 由网络决定 (程序使用 web3.eth.gas_price)
```

### 各 DEX 费用估算

| DEX | 链 | 开仓费用 | 关仓费用 | 备注 |
|-----|---|---------|---------|------|
| Raydium | Solana | ~$0.0013 | ~$0.004 | 程序关仓 3 笔交易 |
| Meteora | Solana | ~$0.0014 | ~$0.0014 | 单笔交易 |
| PancakeSwap | BSC | ~$0.01-0.02 | ~$0.01 | 取决于 Gas Price |
| Uniswap | ETH | ~$0.5-5 | ~$0.3-3 | 取决于 Gas Price |

**注**: 首次交互还需要 Approve 费用 (EVM 链约 46,000 gas/代币)

### 建议优化

#### 1. Raydium 关仓合并 (高优先级)

修改 `generate_close_position_steps` 将 3 笔交易合并为 1 笔：

```python
# 当前: 3 笔独立交易
def generate_close_position_steps():
    yield remove_liquidity_ix, "remove", False
    yield claim_fees_ix, "claim", False
    yield close_position_ix, "close", True

# 建议: 1 笔交易包含所有指令
def build_close_position():
    return [remove_liquidity_ix, claim_fees_ix, close_position_ix]
```

#### 2. 明确费用统计口径

- gas/compute 费用: 实际消耗
- 账户租金: 单独列出 (会退回)
- approve 费用: 首次才需要

#### 3. 动态 priority fee

当前使用固定 priority fee，可考虑:
- Solana: 使用 getPriorityFee API 获取建议值
- EVM: 根据网络拥堵动态调整

---

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

### lp - LP 操作（Solana/EVM）
```python
# 开启仓位
result = client.lp.open(pool, price_range, amount0, amount1)

# 管理仓位
client.lp.add(position, amount0, amount1)
client.lp.remove(position, percent=50)
client.lp.claim(position)
client.lp.close(position)

# 查询仓位
positions = client.lp.positions()
positions = client.lp.positions(pool_address)
```

---

## 类型定义

### PriceRange（价格范围）
```python
from dex_adapter_universal import PriceRange

PriceRange.one_tick()              # 最窄范围
PriceRange.percent(0.02)           # +/- 2%
PriceRange.bps(200)                # +/- 200 基点（2%）
PriceRange.absolute(95.0, 105.0)   # 绝对价格
```

### 核心类型
```python
from dex_adapter_universal import Token, Pool, Position, TxResult, QuoteResult

# TxResult
result.status       # TxStatus.SUCCESS, FAILED, PENDING, TIMEOUT
result.signature    # 交易签名/哈希
result.is_success   # 布尔快捷方式

# QuoteResult
quote.from_amount   # 输入金额（原始值）
quote.to_amount     # 输出金额（原始值）
quote.price_impact_percent
```

---

## 错误处理

```python
from dex_adapter_universal.errors import (
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

---

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

**⚠️ 警告**：集成测试执行真实交易并消耗真实代币！

### 测试池地址

| DEX | 链 | 池地址 | 交易对 |
|-----|---|-------|-------|
| Raydium | Solana | `AQAGYQsdU853WAKhXM79CgNdoyhrRwXvYHX6qrDyC1FS` | SOL/USDC |
| Meteora | Solana | `HTvjzsfX3yU6BUodCjZ5vZkUrAxMDTrBs3CJaq43ashR` | SOL/USDC |
| PancakeSwap | BSC | `0x4a3218606AF9B4728a9F187E1c1a8c07fBC172a9` | WBNB/USDT |
| Uniswap | ETH | `0x4e68Ccd3E89f51C3074ca5072bbAC773960dFa36` | WETH/USDC |

---

## 最近更新

### v1.1.0 - 2026-01-19

#### 修复

**1. web3.py v7 gasPrice 兼容性问题**

在 web3.py v7 版本中，`build_transaction()` 方法会自动添加 EIP-1559 参数，与手动设置的 `gasPrice` 产生冲突。

**受影响文件**:
- `dex_adapter_universal/protocols/pancakeswap/adapter.py`
- `dex_adapter_universal/protocols/uniswap/adapter.py`

**解决方案**: 在 `_add_gas_price()` 方法中明确处理 gas 参数的互斥关系：

```python
def _add_gas_price(self, tx):
    if self._chain_id == 1:  # Ethereum (EIP-1559)
        # 设置 EIP-1559 参数
        tx["maxFeePerGas"] = max_fee
        tx["maxPriorityFeePerGas"] = max_priority_fee
        # 移除冲突的 gasPrice
        if "gasPrice" in tx:
            del tx["gasPrice"]
    else:  # BSC (Legacy)
        # 移除 EIP-1559 参数
        tx.pop("maxFeePerGas", None)
        tx.pop("maxPriorityFeePerGas", None)
        tx["gasPrice"] = self._web3.eth.gas_price
```

**2. PancakeSwap Native BNB 处理问题**

原代码尝试在 WBNB 池子中使用 native BNB 作为 value 发送，但 Position Manager 合约不会自动 wrap BNB。

**症状**: 开仓交易 revert，错误 "Price slippage check"

**受影响文件**: `dex_adapter_universal/protocols/pancakeswap/adapter.py`

**解决方案**: 改为直接使用 WBNB 代币，不使用 native value：

```python
# 修改前：尝试发送 native BNB
if token1_is_native and raw_amount1 > 0:
    native_value += raw_amount1
# 不 approve WBNB

# 修改后：始终使用代币
native_value = 0  # 不发送 native BNB
# Approve 所有代币（包括 WBNB）
if raw_amount1 > 0:
    approval = self._ensure_approval_for_position_manager(token1_addr, raw_amount1)
```

**注意**: 用户需要有 WBNB 代币余额，而不是只有 native BNB。

#### 已知问题

**1. Raydium 多步骤关仓**

程序关仓使用 3 笔独立交易，费用约为 UI 单笔交易的 3 倍。

**影响**: 关仓费用 ~$0.004 vs UI ~$0.0013

**位置**: `dex_adapter_universal/modules/liquidity.py`

**建议优化**: 
- 合并为单笔交易
- 或使用 Jito Bundle 打包

---

## 设计原则

1. **多链支持** - Solana、Ethereum、BSC 统一接口
2. **原子操作** - 每个方法是一个完整的单一操作
3. **协议无关** - 跨不同 DEX 协议的相同 API
4. **错误恢复** - 错误指示是否可以重试
5. **类型安全** - 所有数据结构使用 dataclass
6. **最小费用** - 使用保守的 gas/priority fee 配置

---

## License

MIT
