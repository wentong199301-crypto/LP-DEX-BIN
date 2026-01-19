# DEX LP 操作费用分析报告

## 用户反馈费用 vs 程序理论费用

| DEX | 用户反馈 | 程序计算 | 差异分析 |
|-----|---------|---------|---------|
| Raydium (Solana) | ~$0.03 | ~$0.005 | 可能包含账户租金押金 |
| PancakeSwap (BSC) | ~$0.03 | ~$0.023 | 较接近 |
| Uniswap (ETH) | ~$0.8 | ~$0.84 | 非常接近 |
| Meteora (Solana) | 未测试 | ~$0.003 | - |

## 关键发现

### 1. Raydium 多步骤关仓问题 ⚠️

**程序实现** (`dex_adapter_universal/modules/liquidity.py`):

```python
if position.pool.dex == "raydium" and hasattr(adapter, "generate_close_position_steps"):
    return self._execute_multi_step_close(position, adapter)
```

关仓分为3笔独立交易：
- Step 1: Remove all liquidity
- Step 2: Claim fees/rewards  
- Step 3: Close position (burn NFT)

**每笔交易都有独立的base fee (5000 lamports)**

| 操作 | 交易数 | 费用 |
|------|-------|-----|
| 开仓 | 1笔 | ~$0.0013 |
| 关仓(程序) | 3笔 | ~$0.004 |
| 关仓(UI预计) | 1笔 | ~$0.0013 |

### 2. 账户租金押金 (SOL) - 不是费用

Raydium开仓时需要创建：
- NFT mint账户: ~0.00289 SOL (~$0.75)
- Position PDA: ~0.00203 SOL (~$0.53)
- ATA账户: ~0.00203 SOL (如果不存在)

**总押金: ~0.01 SOL (~$2.6)**

这些押金在**关仓时会退回**，不应计入费用。

但是如果用户的统计方式不同，可能会将这部分计入"费用"。

### 3. EVM Approve 交易

程序首次交互时会执行approve交易：
- 每个代币: ~46,000 gas
- 两个代币: ~92,000 gas

如果UI使用Permit2签名，则无需额外交易。

## 费用配置参数

### Solana (config.py)

```python
# LP操作 compute budget
lp_compute_units: 600,000  # CU限制
lp_compute_unit_price: 1,000  # microlamports/CU (priority fee)
```

Priority fee计算:
- 600,000 CU × 1,000 μlamports/CU = 600 lamports = $0.000156

### EVM (config.py)

```python
# PancakeSwap
gas_limit_multiplier: 1.2  # 额外20%缓冲
priority_fee_gwei: 0.1  # 最低priority fee

# Uniswap  
gas_limit_multiplier: 1.2
priority_fee_gwei: 0.1
```

## 建议优化

### 1. Raydium 关仓合并 (高优先级)

修改 `generate_close_position_steps` 将3笔交易合并为1笔：

```python
# 当前: 3笔独立交易
def generate_close_position_steps():
    yield remove_liquidity_ix, "remove", False
    yield claim_fees_ix, "claim", False
    yield close_position_ix, "close", True

# 建议: 1笔交易包含所有指令
def build_close_position():
    return [remove_liquidity_ix, claim_fees_ix, close_position_ix]
```

### 2. 明确费用统计口径

- gas/compute费用: 实际消耗
- 账户租金: 单独列出 (会退回)
- approve费用: 首次才需要

### 3. 动态 priority fee

当前使用固定priority fee，可考虑:
- Solana: 使用getPriorityFee API获取建议值
- EVM: 根据网络拥堵动态调整

## 测试池地址

- Raydium: `AQAGYQsdU853WAKhXM79CgNdoyhrRwXvYHX6qrDyC1FS`
- PancakeSwap: `0x4a3218606AF9B4728a9F187E1c1a8c07fBC172a9`
- Uniswap: `0x4e68Ccd3E89f51C3074ca5072bbAC773960dFa36`
- Meteora: `HTvjzsfX3yU6BUodCjZ5vZkUrAxMDTrBs3CJaq43ashR`

