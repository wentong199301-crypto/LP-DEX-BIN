# DEX Adapter 费用配置与开撤仓说明文档

## 目录

1. [本次修改摘要](#1-本次修改摘要)
2. [费用结构概述](#2-费用结构概述)
3. [Solana 链费用配置](#3-solana-链费用配置)
4. [EVM 链费用配置](#4-evm-链费用配置)
5. [各 DEX 开撤仓流程与费用](#5-各-dex-开撤仓流程与费用)
6. [环境变量配置参考](#6-环境变量配置参考)
7. [费用计算公式](#7-费用计算公式)
8. [已知问题与优化建议](#8-已知问题与优化建议)

---

## 1. 本次修改摘要

### 1.1 修复: web3.py v7 gasPrice 兼容性问题

**问题描述**: 在 web3.py v7 版本中，`build_transaction()` 方法会自动添加 EIP-1559 参数（`maxFeePerGas`, `maxPriorityFeePerGas`），与手动设置的 `gasPrice` 产生冲突，导致 `Unknown kwargs: ['gasPrice']` 错误。

**修复位置**:
- `dex_adapter_universal/protocols/pancakeswap/adapter.py`
- `dex_adapter_universal/protocols/uniswap/adapter.py`

**修复内容**: 在 `_add_gas_price()` 方法中，明确处理 gas 参数的互斥关系：

```python
def _add_gas_price(self, tx: Dict[str, Any]):
    """Add gas price to transaction with minimum priority fee from config"""
    if self._chain_id == 1:  # Ethereum (EIP-1559)
        latest_block = self._web3.eth.get_block("latest")
        base_fee = latest_block.get("baseFeePerGas", 0)
        priority_fee_gwei = global_config.pancakeswap.priority_fee_gwei
        max_priority_fee = self._web3.to_wei(priority_fee_gwei, "gwei")
        max_fee = int(base_fee * 2) + max_priority_fee
        tx["maxFeePerGas"] = max_fee
        tx["maxPriorityFeePerGas"] = max_priority_fee
        # 移除冲突的 gasPrice 字段
        if "gasPrice" in tx:
            del tx["gasPrice"]
    else:  # BSC 等使用 legacy gas price
        # 移除 EIP-1559 字段
        tx.pop("maxFeePerGas", None)
        tx.pop("maxPriorityFeePerGas", None)
        tx["gasPrice"] = self._web3.eth.gas_price
```

### 1.2 发现: Raydium 多步骤关仓问题

**问题描述**: 程序在关闭 Raydium 仓位时使用 3 笔独立交易，而 UI 可能使用单笔交易完成。

**影响**: 关仓费用约为 UI 的 3 倍。

**代码位置**: `dex_adapter_universal/modules/liquidity.py`

```python
# 程序使用多步骤关仓
if position.pool.dex == "raydium" and hasattr(adapter, "generate_close_position_steps"):
    return self._execute_multi_step_close(position, adapter)
```

**关仓步骤**:
1. Step 1: Remove all liquidity (移除流动性)
2. Step 2: Claim fees/rewards (领取手续费/奖励)
3. Step 3: Close position (关闭仓位，销毁 NFT)

---

## 2. 费用结构概述

### 2.1 费用定义

**费用 (Fee)**: 付出后不会退回的钱，包括:
- Gas 费 (EVM 链)
- Compute Unit 费用 (Solana)
- 交易签名费 (Solana base fee)

**不计入费用**:
- 账户租金押金 (Solana, 关仓时退回)
- Token Approve 的 allowance (不消耗资金)

### 2.2 各链费用类型

| 链 | 费用组成 | 说明 |
|----|---------|------|
| Solana | Base Fee + Priority Fee | Base Fee 固定, Priority Fee 可配置 |
| Ethereum | (Base Fee + Priority Fee) × Gas Used | EIP-1559 模型 |
| BSC | Gas Price × Gas Used | Legacy 模型 |

---

## 3. Solana 链费用配置

### 3.1 费用组成

Solana 交易费用由两部分组成:

```
总费用 = Base Fee + Priority Fee
```

- **Base Fee**: 5000 lamports/signature (固定)
- **Priority Fee**: Compute Units × Compute Unit Price

### 3.2 配置参数

配置文件: `dex_adapter_universal/config.py`

```python
@dataclass
class TxConfig:
    # Swap 操作 Compute Budget
    compute_units: int = 200_000          # 环境变量: TX_COMPUTE_UNITS
    compute_unit_price: int = 1_000       # 环境变量: TX_COMPUTE_UNIT_PRICE (microlamports/CU)
    
    # LP 操作 Compute Budget (更高)
    lp_compute_units: int = 600_000       # 环境变量: TX_LP_COMPUTE_UNITS
    lp_compute_unit_price: int = 1_000    # 环境变量: TX_LP_COMPUTE_UNIT_PRICE (microlamports/CU)
```

### 3.3 费用计算示例

```
LP 操作 Priority Fee:
= 600,000 CU × 1,000 microlamports/CU
= 600,000,000 microlamports
= 600 lamports
= 0.0000006 SOL

总费用 (含 Base Fee):
= 5,000 + 600 lamports
= 5,600 lamports
= 0.0000056 SOL
≈ $0.0015 (按 $260/SOL 计算)
```

### 3.4 代码实现

交易构建时设置 Compute Budget (`dex_adapter_universal/infra/tx_builder.py`):

```python
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price

def build_and_send(self, instructions, compute_units=None, compute_unit_price=None):
    cu_limit = compute_units or self._config.compute_units
    cu_price = compute_unit_price or self._config.compute_unit_price
    
    all_instructions = []
    if set_compute_unit_limit:
        all_instructions.append(set_compute_unit_limit(cu_limit))
    if set_compute_unit_price and cu_price:
        all_instructions.append(set_compute_unit_price(cu_price))
    all_instructions.extend(instructions)
```

### 3.5 账户租金押金 (不计入费用)

| 账户类型 | 租金 (SOL) | 说明 |
|---------|-----------|------|
| Token Account (ATA) | ~0.00203 | 首次创建代币账户 |
| NFT Mint (Raydium) | ~0.00289 | 仓位 NFT |
| Position PDA | ~0.00203 | 仓位数据账户 |

**注意**: 这些租金在关仓时会退回到用户钱包。

---

## 4. EVM 链费用配置

### 4.1 Ethereum (EIP-1559 模型)

```
总费用 = Gas Used × (Base Fee + Priority Fee)
```

- **Base Fee**: 由网络动态决定
- **Priority Fee (Tip)**: 可配置，默认 0.1 gwei

### 4.2 BSC (Legacy 模型)

```
总费用 = Gas Used × Gas Price
```

- **Gas Price**: 由网络决定，程序使用 `web3.eth.gas_price`

### 4.3 配置参数

```python
@dataclass
class PancakeSwapConfig:
    gas_limit_multiplier: float = 1.2     # 环境变量: PANCAKESWAP_GAS_LIMIT_MULTIPLIER
    priority_fee_gwei: float = 0.1        # 环境变量: PANCAKESWAP_PRIORITY_FEE_GWEI

@dataclass
class UniswapConfig:
    gas_limit_multiplier: float = 1.2     # 环境变量: UNISWAP_GAS_LIMIT_MULTIPLIER
    priority_fee_gwei: float = 0.1        # 环境变量: UNISWAP_PRIORITY_FEE_GWEI

@dataclass
class OneInchConfig:
    gas_limit_multiplier: float = 1.1     # 环境变量: ONEINCH_GAS_LIMIT_MULTIPLIER
    priority_fee_gwei: float = 0.1        # 环境变量: ONEINCH_PRIORITY_FEE_GWEI
```

### 4.4 Gas 价格计算逻辑

**Ethereum (EIP-1559)**:

```python
def _add_gas_price(self, tx):
    latest_block = self._web3.eth.get_block("latest")
    base_fee = latest_block.get("baseFeePerGas", 0)
    priority_fee_gwei = global_config.uniswap.priority_fee_gwei  # 默认 0.1
    max_priority_fee = self._web3.to_wei(priority_fee_gwei, "gwei")
    max_fee = int(base_fee * 2) + max_priority_fee  # 2x base fee 作为缓冲
    
    tx["maxFeePerGas"] = max_fee
    tx["maxPriorityFeePerGas"] = max_priority_fee
```

**BSC (Legacy)**:

```python
def _add_gas_price(self, tx):
    tx["gasPrice"] = self._web3.eth.gas_price  # 使用网络当前 gas price
```

### 4.5 Gas Limit 设置

程序使用估算值乘以缓冲系数:

```python
estimated_gas = self._web3.eth.estimate_gas(tx)
gas_limit = int(estimated_gas * gas_limit_multiplier)  # 默认 1.2x
```

### 4.6 Approve 交易费用

首次与合约交互时需要 Approve:

| 操作 | Gas 消耗 | 说明 |
|-----|---------|------|
| ERC20 Approve | ~46,000 | 每个代币一次 |
| Position Manager Approve | ~46,000 | LP 操作需要 |

**代码位置**: `_ensure_approval_for_position_manager()`

```python
def _ensure_approval_for_position_manager(self, token_address, amount):
    # 检查现有 allowance
    allowance = token_contract.functions.allowance(owner, pm_address).call()
    if allowance >= amount:
        return None  # 已授权
    
    # 执行 approve (无限授权)
    approve_tx = token_contract.functions.approve(pm_address, 2**256 - 1)
```

---

## 5. 各 DEX 开撤仓流程与费用

### 5.1 Raydium CLMM (Solana)

#### 开仓流程

1. 创建 ATA 账户 (如果不存在)
2. 创建 NFT Mint 账户
3. 创建 Position PDA
4. Mint NFT 并添加流动性

**交易数**: 1 笔

#### 关仓流程 (程序实现)

```python
# dex_adapter_universal/protocols/raydium/adapter.py
def generate_close_position_steps(self, position, owner):
    # Step 1: 移除所有流动性
    yield remove_liquidity_instructions, "remove_liquidity", False
    
    # Step 2: 领取剩余费用/奖励
    yield claim_fees_instructions, "claim_fees", False
    
    # Step 3: 关闭仓位 (销毁 NFT)
    yield close_position_instructions, "close_position", True
```

**交易数**: 3 笔

#### 费用估算

| 操作 | 交易数 | 费用 (SOL) | 费用 (USD) |
|-----|-------|-----------|-----------|
| 开仓 | 1 | ~0.000005 | ~$0.0013 |
| 关仓 (程序) | 3 | ~0.000015 | ~$0.0040 |
| 关仓 (UI) | 1 | ~0.000005 | ~$0.0013 |

### 5.2 Meteora DLMM (Solana)

#### 开仓流程

1. 创建 Position 账户
2. 添加流动性到指定 Bins

**交易数**: 1 笔

#### 关仓流程

1. 移除所有流动性
2. 关闭 Position 账户

**交易数**: 1 笔

#### 费用估算

| 操作 | 交易数 | 费用 (SOL) | 费用 (USD) |
|-----|-------|-----------|-----------|
| 开仓 | 1 | ~0.000005 | ~$0.0014 |
| 关仓 | 1 | ~0.000005 | ~$0.0014 |

### 5.3 PancakeSwap V3 (BSC)

#### 开仓流程

1. Approve Token0 (如需)
2. Approve Token1 (如需)
3. Mint Position (创建仓位 NFT)

**交易数**: 1-3 笔

#### 关仓流程

使用 Multicall 合并:
1. Decrease Liquidity
2. Collect Fees
3. Burn NFT

**交易数**: 1 笔

#### 费用估算 (Gas Price = 3 Gwei)

| 操作 | Gas | 费用 (BNB) | 费用 (USD) |
|-----|-----|-----------|-----------|
| Mint Position | ~380,000 | ~0.00114 | ~$0.80 |
| Approve (每个) | ~46,000 | ~0.00014 | ~$0.10 |
| Close (Multicall) | ~280,000 | ~0.00084 | ~$0.59 |

**注**: BSC Gas Price 通常为 1-5 Gwei，费用会相应变化。当前网络 Gas Price 约 0.05 Gwei，实际费用更低。

### 5.4 Uniswap V3 (Ethereum)

#### 开仓流程

1. Approve Token0 (如需)
2. Approve Token1 (如需)
3. Mint Position

**交易数**: 1-3 笔

#### 关仓流程

使用 Multicall 合并:
1. Decrease Liquidity
2. Collect Fees
3. Burn NFT

**交易数**: 1 笔

#### 费用估算 (Gas Price = 30 Gwei)

| 操作 | Gas | 费用 (ETH) | 费用 (USD) |
|-----|-----|-----------|-----------|
| Mint Position | ~450,000 | ~0.0135 | ~$46 |
| Approve (每个) | ~46,000 | ~0.0014 | ~$4.7 |
| Close (Multicall) | ~320,000 | ~0.0096 | ~$33 |

**注**: Ethereum Gas Price 波动较大，实际费用差异显著。

---

## 6. 环境变量配置参考

### 6.1 Solana Compute Budget

```bash
# Swap 操作
TX_COMPUTE_UNITS=200000           # Compute Unit 限制
TX_COMPUTE_UNIT_PRICE=1000        # Priority Fee (microlamports/CU)

# LP 操作 (需要更高)
TX_LP_COMPUTE_UNITS=600000        # LP Compute Unit 限制
TX_LP_COMPUTE_UNIT_PRICE=1000     # LP Priority Fee (microlamports/CU)
```

### 6.2 EVM Gas 设置

```bash
# PancakeSwap
PANCAKESWAP_GAS_LIMIT_MULTIPLIER=1.2    # Gas 估算缓冲
PANCAKESWAP_PRIORITY_FEE_GWEI=0.1       # Priority Fee (Gwei)

# Uniswap
UNISWAP_GAS_LIMIT_MULTIPLIER=1.2
UNISWAP_PRIORITY_FEE_GWEI=0.1

# 1inch
ONEINCH_GAS_LIMIT_MULTIPLIER=1.1
ONEINCH_PRIORITY_FEE_GWEI=0.1
```

### 6.3 交易确认

```bash
TX_CONFIRMATION_TIMEOUT=90.0      # 确认超时 (秒)
TX_MAX_RETRIES=3                  # 最大重试次数
TX_RETRY_DELAY=2.0                # 重试间隔 (秒)
TX_SKIP_PREFLIGHT=false           # 跳过预检
TX_PREFLIGHT_COMMITMENT=confirmed # 预检确认级别
```

---

## 7. 费用计算公式

### 7.1 Solana

```
单笔交易费用 = Base Fee + (Compute Units × CU Price / 1,000,000)

其中:
- Base Fee = 5,000 lamports (固定)
- Compute Units = 使用的计算单位
- CU Price = microlamports/CU (配置)

转换:
- 1 SOL = 1,000,000,000 lamports
- 1 lamport = 1,000,000 microlamports
```

### 7.2 Ethereum (EIP-1559)

```
交易费用 = Gas Used × Effective Gas Price

其中:
- Effective Gas Price = min(Base Fee + Priority Fee, Max Fee Per Gas)
- Base Fee = 区块基础费用 (动态)
- Priority Fee = 矿工小费 (配置, 默认 0.1 Gwei)
- Max Fee Per Gas = Base Fee × 2 + Priority Fee (程序设置)

转换:
- 1 ETH = 1,000,000,000 Gwei
- 1 Gwei = 1,000,000,000 Wei
```

### 7.3 BSC (Legacy)

```
交易费用 = Gas Used × Gas Price

其中:
- Gas Price = 网络当前价格 (由 web3.eth.gas_price 获取)

转换:
- 1 BNB = 1,000,000,000 Gwei
```

---

## 8. 已知问题与优化建议

### 8.1 Raydium 多步骤关仓

**问题**: 关仓使用 3 笔交易，费用是单笔交易的 3 倍。

**建议优化**:

1. **合并交易**: 将 3 步合并为单笔交易

```python
def build_close_position(self, position, owner):
    instructions = []
    instructions.extend(self._build_remove_liquidity(position))
    instructions.extend(self._build_claim_fees(position))
    instructions.extend(self._build_close_position(position))
    return instructions  # 单笔交易
```

2. **使用 Jito Bundle**: 将多笔交易打包

### 8.2 EVM Approve 额外费用

**问题**: 首次交互需要单独的 Approve 交易。

**建议优化**:

1. **使用 Permit2**: 避免单独 Approve

```python
# Permit2 签名替代 Approve 交易
permit_signature = sign_permit(token, amount, deadline)
```

2. **无限授权**: 首次授权 `2**256-1`，后续无需再授权

### 8.3 动态 Priority Fee

**问题**: 使用固定 Priority Fee 可能导致交易延迟或多付。

**建议优化**:

1. **Solana**: 使用 `getPriorityFee` API

```python
# 获取建议的 priority fee
response = rpc.get_recent_prioritization_fees(addresses)
suggested_fee = calculate_median(response)
```

2. **Ethereum**: 使用 `eth_maxPriorityFeePerGas`

```python
suggested_priority = web3.eth.max_priority_fee
```

### 8.4 Gas 估算优化

**问题**: 使用 1.2x 缓冲可能多预留 gas。

**建议**: 
- 精确估算后使用 1.05-1.1x 缓冲
- 未使用的 gas 会退回，不影响实际费用

---

## 附录: 测试池地址

| DEX | 链 | 池地址 | 交易对 |
|-----|---|-------|-------|
| Raydium | Solana | `AQAGYQsdU853WAKhXM79CgNdoyhrRwXvYHX6qrDyC1FS` | SOL/USDC |
| Meteora | Solana | `HTvjzsfX3yU6BUodCjZ5vZkUrAxMDTrBs3CJaq43ashR` | SOL/USDC |
| PancakeSwap | BSC | `0x4a3218606AF9B4728a9F187E1c1a8c07fBC172a9` | WBNB/USDT |
| Uniswap | Ethereum | `0x4e68Ccd3E89f51C3074ca5072bbAC773960dFa36` | WETH/USDC |

---

*文档生成时间: 2026-01-19*
*版本: 1.0*

