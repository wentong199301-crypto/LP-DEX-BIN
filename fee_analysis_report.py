# -*- coding: utf-8 -*-
"""
Fee Analysis Report Script

Analyzes and compares theoretical gas costs for LP operations across DEXs
without actually executing transactions.
"""

import os
import sys
os.environ['BSC_RPC_URL'] = 'https://bsc-dataseed.binance.org'
os.environ['ETH_RPC_URL'] = 'https://eth.llamarpc.com'

# 设置输出编码
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from web3 import Web3
from decimal import Decimal

# 价格数据 (可以从CoinGecko获取)
PRICES_USD = {
    "SOL": 260.0,   # Solana
    "BNB": 700.0,   # BSC
    "ETH": 3400.0,  # Ethereum
}

# Gas估算数据 (基于实际测试)
GAS_ESTIMATES = {
    "pancakeswap_v3": {
        "mint_position": 380000,    # 开仓
        "collect": 150000,          # 收取费用
        "decrease_liquidity": 180000,  # 移除流动性
        "burn": 50000,              # 销毁NFT
        "approve": 46000,           # ERC20 approve (每个代币)
    },
    "uniswap_v3": {
        "mint_position": 450000,    # Ethereum更高
        "collect": 180000,
        "decrease_liquidity": 200000,
        "burn": 60000,
        "approve": 46000,
    }
}

# Solana compute单位估算
SOLANA_CU_ESTIMATES = {
    "raydium_clmm": {
        "open_position": 200000,    # 开仓
        "close_position": 150000,   # 关仓
        "increase_liquidity": 150000,
        "decrease_liquidity": 150000,
    },
    "meteora_dlmm": {
        "add_liquidity": 400000,    # Meteora需要更多CU
        "remove_liquidity": 300000,
        "claim_fee": 100000,
    }
}

# Solana base fee per signature
SOLANA_BASE_FEE_LAMPORTS = 5000  # 5000 lamports = 0.000005 SOL

def get_bsc_gas_price():
    """获取BSC当前gas价格"""
    try:
        web3 = Web3(Web3.HTTPProvider('https://bsc-dataseed.binance.org'))
        gas_price = web3.eth.gas_price
        gas_price_gwei = web3.from_wei(gas_price, 'gwei')
        return float(gas_price_gwei)
    except Exception as e:
        print(f"获取BSC gas价格失败: {e}")
        return 3.0  # 默认值

def get_eth_gas_price():
    """获取Ethereum当前gas价格 (包括priority fee)"""
    try:
        web3 = Web3(Web3.HTTPProvider('https://eth.llamarpc.com'))
        latest_block = web3.eth.get_block('latest')
        base_fee = latest_block.get('baseFeePerGas', 0)
        
        # Priority fee (配置默认0.1 gwei)
        priority_fee = web3.to_wei(0.1, 'gwei')
        max_fee = int(base_fee * 1.5) + priority_fee  # 使用1.5x base fee + priority
        
        total_gwei = web3.from_wei(max_fee, 'gwei')
        return float(total_gwei)
    except Exception as e:
        print(f"获取ETH gas价格失败: {e}")
        return 30.0  # 默认值

def get_solana_priority_fee():
    """获取Solana priority fee配置"""
    # 从config获取默认值
    from dex_adapter_universal.config import config
    cu_price = config.tx.lp_compute_unit_price  # microlamports per CU
    return cu_price

def calculate_evm_fee(gas_used: int, gas_price_gwei: float, native_price_usd: float) -> tuple:
    """计算EVM链费用"""
    gas_price_wei = gas_price_gwei * 1e9
    fee_wei = gas_used * gas_price_wei
    fee_native = fee_wei / 1e18
    fee_usd = fee_native * native_price_usd
    return fee_native, fee_usd

def calculate_solana_fee(compute_units: int, cu_price_microlamports: int, num_signatures: int = 1) -> tuple:
    """计算Solana费用
    
    Args:
        compute_units: 计算单位
        cu_price_microlamports: 每CU的优先费 (microlamports)
        num_signatures: 签名数量 (每个交易至少1个)
    """
    # Base fee: 5000 lamports per signature
    base_fee_lamports = SOLANA_BASE_FEE_LAMPORTS * num_signatures
    
    # Priority fee
    priority_fee_lamports = (compute_units * cu_price_microlamports) / 1_000_000
    
    total_lamports = base_fee_lamports + priority_fee_lamports
    total_sol = total_lamports / 1e9
    total_usd = total_sol * PRICES_USD["SOL"]
    
    return total_sol, total_usd

def print_report():
    """打印费用分析报告"""
    print("=" * 80)
    print("                    DEX LP操作费用分析报告")
    print("=" * 80)
    
    # 获取当前价格
    bsc_gas_price = get_bsc_gas_price()
    eth_gas_price = get_eth_gas_price()
    sol_cu_price = get_solana_priority_fee()
    
    print(f"\n[数据] 当前链上数据:")
    print(f"  - BSC Gas Price: {bsc_gas_price:.2f} Gwei")
    print(f"  - ETH Gas Price: {eth_gas_price:.2f} Gwei (含priority fee)")
    print(f"  - Solana CU Price: {sol_cu_price} microlamports/CU")
    print(f"  - Solana Base Fee: {SOLANA_BASE_FEE_LAMPORTS} lamports/signature")
    print(f"  - SOL Price: ${PRICES_USD['SOL']}")
    print(f"  - BNB Price: ${PRICES_USD['BNB']}")
    print(f"  - ETH Price: ${PRICES_USD['ETH']}")
    
    # ========== Raydium (Solana) ==========
    print("\n" + "=" * 80)
    print("[RAY] Raydium CLMM (Solana)")
    print("  !! 重要: 程序使用多步骤关仓 (3笔交易)")
    print("=" * 80)
    
    ray = SOLANA_CU_ESTIMATES["raydium_clmm"]
    
    # 开仓 - 单笔交易
    open_sol, open_usd = calculate_solana_fee(ray["open_position"], sol_cu_price, num_signatures=1)
    
    print(f"\n[开仓] 开仓费用 (单笔交易):")
    print(f"  - Compute Units: {ray['open_position']:,}")
    print(f"  - Base Fee: {SOLANA_BASE_FEE_LAMPORTS} lamports = {SOLANA_BASE_FEE_LAMPORTS/1e9:.9f} SOL")
    print(f"  - Priority Fee: {ray['open_position'] * sol_cu_price / 1e6:.2f} lamports")
    print(f"  - 总费用: {open_sol:.9f} SOL (${open_usd:.6f})")
    print(f"  - 账户租金押金: ~0.00289 SOL (关仓时退回, 不计入费用)")
    
    # 关仓 - 程序使用3步
    # Step 1: Remove liquidity
    # Step 2: Claim fees/rewards  
    # Step 3: Close position
    close_step1_sol, close_step1_usd = calculate_solana_fee(ray["decrease_liquidity"], sol_cu_price, num_signatures=1)
    close_step2_sol, close_step2_usd = calculate_solana_fee(ray["decrease_liquidity"], sol_cu_price, num_signatures=1)
    close_step3_sol, close_step3_usd = calculate_solana_fee(ray["close_position"], sol_cu_price, num_signatures=1)
    
    total_close_sol = close_step1_sol + close_step2_sol + close_step3_sol
    total_close_usd = close_step1_usd + close_step2_usd + close_step3_usd
    
    print(f"\n[关仓] 关仓费用 (程序: 3笔交易):")
    print(f"  Step 1 - Remove Liquidity:")
    print(f"     - 费用: {close_step1_sol:.9f} SOL (${close_step1_usd:.6f})")
    print(f"  Step 2 - Claim Fees/Rewards:")
    print(f"     - 费用: {close_step2_sol:.9f} SOL (${close_step2_usd:.6f})")
    print(f"  Step 3 - Close Position:")
    print(f"     - 费用: {close_step3_sol:.9f} SOL (${close_step3_usd:.6f})")
    print(f"  [程序] 关仓总费用: {total_close_sol:.9f} SOL (${total_close_usd:.6f})")
    
    # UI可能使用单笔交易
    close_single_sol, close_single_usd = calculate_solana_fee(ray["close_position"], sol_cu_price, num_signatures=1)
    print(f"  [UI] 关仓费用 (单笔): {close_single_sol:.9f} SOL (${close_single_usd:.6f})")
    
    program_total = open_usd + total_close_usd
    ui_total = open_usd + close_single_usd
    
    print(f"\n[总计] Raydium 完整开撤仓费用:")
    print(f"  [程序] ${program_total:.6f} (开仓1笔 + 关仓3笔 = 4笔交易)")
    print(f"  [UI估计] ${ui_total:.6f} (开仓1笔 + 关仓1笔 = 2笔交易)")
    print(f"  [差异] 程序比UI多花: ${program_total - ui_total:.6f}")
    
    # ========== Meteora (Solana) ==========
    print("\n" + "=" * 80)
    print("[MET] Meteora DLMM (Solana)")
    print("=" * 80)
    
    met = SOLANA_CU_ESTIMATES["meteora_dlmm"]
    
    # 开仓 (add_liquidity)
    open_sol, open_usd = calculate_solana_fee(met["add_liquidity"], sol_cu_price, num_signatures=1)
    
    print(f"\n[开仓] 开仓费用:")
    print(f"  - Compute Units: {met['add_liquidity']:,}")
    print(f"  - 费用: {open_sol:.9f} SOL (${open_usd:.6f})")
    print(f"  - 账户租金押金: ~0.01 SOL (关仓时退回, 不计入费用)")
    
    # 关仓 (remove_liquidity)
    close_sol, close_usd = calculate_solana_fee(met["remove_liquidity"], sol_cu_price, num_signatures=1)
    
    print(f"\n[关仓] 关仓费用:")
    print(f"  - Compute Units: {met['remove_liquidity']:,}")
    print(f"  - 费用: {close_sol:.9f} SOL (${close_usd:.6f})")
    
    print(f"\n[总计] Meteora 完整开撤仓费用预估: ${open_usd + close_usd:.6f}")
    
    # ========== PancakeSwap (BSC) ==========
    print("\n" + "=" * 80)
    print("[PCS] PancakeSwap V3 (BSC)")
    print("=" * 80)
    
    pcs = GAS_ESTIMATES["pancakeswap_v3"]
    
    # 开仓费用 (可能需要2次approve + mint)
    open_gas = pcs["mint_position"]
    approve_gas = pcs["approve"] * 2  # 两个代币
    
    open_native, open_usd = calculate_evm_fee(open_gas, bsc_gas_price, PRICES_USD["BNB"])
    approve_native, approve_usd = calculate_evm_fee(approve_gas, bsc_gas_price, PRICES_USD["BNB"])
    
    print(f"\n[开仓] 开仓费用:")
    print(f"  1. Mint Position交易:")
    print(f"     - Gas: {open_gas:,}")
    print(f"     - 费用: {open_native:.6f} BNB (${open_usd:.4f})")
    print(f"  2. Approve交易 (首次需要, 两个代币):")
    print(f"     - Gas: {approve_gas:,}")
    print(f"     - 费用: {approve_native:.6f} BNB (${approve_usd:.4f})")
    print(f"  [OK] 开仓总费用 (无approve): ${open_usd:.4f}")
    print(f"  [OK] 开仓总费用 (含approve): ${open_usd + approve_usd:.4f}")
    
    # 关仓费用 (decrease + collect + burn)
    close_gas = pcs["decrease_liquidity"] + pcs["collect"] + pcs["burn"]
    close_native, close_usd = calculate_evm_fee(close_gas, bsc_gas_price, PRICES_USD["BNB"])
    
    # 或者只用单笔交易 (multicall)
    close_single_gas = pcs["decrease_liquidity"] + 100000  # multicall overhead
    close_single_native, close_single_usd = calculate_evm_fee(close_single_gas, bsc_gas_price, PRICES_USD["BNB"])
    
    print(f"\n[关仓] 关仓费用:")
    print(f"  分开交易 (decrease + collect + burn):")
    print(f"     - Gas: {close_gas:,}")
    print(f"     - 费用: {close_native:.6f} BNB (${close_usd:.4f})")
    print(f"  单笔交易 (multicall):")
    print(f"     - Gas: ~{close_single_gas:,}")
    print(f"     - 费用: {close_single_native:.6f} BNB (${close_single_usd:.4f})")
    
    print(f"\n[总计] PancakeSwap 完整开撤仓费用预估: ${open_usd + close_single_usd:.4f}")
    
    # ========== Uniswap (Ethereum) ==========
    print("\n" + "=" * 80)
    print("[UNI] Uniswap V3 (Ethereum)")
    print("=" * 80)
    
    uni = GAS_ESTIMATES["uniswap_v3"]
    
    # 开仓
    open_gas = uni["mint_position"]
    approve_gas = uni["approve"] * 2
    
    open_native, open_usd = calculate_evm_fee(open_gas, eth_gas_price, PRICES_USD["ETH"])
    approve_native, approve_usd = calculate_evm_fee(approve_gas, eth_gas_price, PRICES_USD["ETH"])
    
    print(f"\n[开仓] 开仓费用:")
    print(f"  1. Mint Position交易:")
    print(f"     - Gas: {open_gas:,}")
    print(f"     - 费用: {open_native:.6f} ETH (${open_usd:.4f})")
    print(f"  2. Approve交易 (首次需要):")
    print(f"     - Gas: {approve_gas:,}")
    print(f"     - 费用: {approve_native:.6f} ETH (${approve_usd:.4f})")
    print(f"  [OK] 开仓总费用 (无approve): ${open_usd:.4f}")
    print(f"  [OK] 开仓总费用 (含approve): ${open_usd + approve_usd:.4f}")
    
    # 关仓
    close_gas = uni["decrease_liquidity"] + uni["collect"] + uni["burn"]
    close_native, close_usd = calculate_evm_fee(close_gas, eth_gas_price, PRICES_USD["ETH"])
    
    close_single_gas = uni["decrease_liquidity"] + 120000
    close_single_native, close_single_usd = calculate_evm_fee(close_single_gas, eth_gas_price, PRICES_USD["ETH"])
    
    print(f"\n[关仓] 关仓费用:")
    print(f"  单笔交易 (multicall):")
    print(f"     - Gas: ~{close_single_gas:,}")
    print(f"     - 费用: {close_single_native:.6f} ETH (${close_single_usd:.4f})")
    
    print(f"\n[总计] Uniswap 完整开撤仓费用预估: ${open_usd + close_single_usd:.4f}")
    
    # ========== 汇总比较 ==========
    print("\n" + "=" * 80)
    print("                        [汇总] 费用汇总比较")
    print("=" * 80)
    
    # 计算各DEX费用 (使用程序的实际行为)
    ray_program = calculate_solana_fee(ray["open_position"], sol_cu_price, 1)[1] + \
                  calculate_solana_fee(ray["decrease_liquidity"], sol_cu_price, 1)[1] + \
                  calculate_solana_fee(ray["decrease_liquidity"], sol_cu_price, 1)[1] + \
                  calculate_solana_fee(ray["close_position"], sol_cu_price, 1)[1]
    
    ray_ui = calculate_solana_fee(ray["open_position"], sol_cu_price, 1)[1] + \
             calculate_solana_fee(ray["close_position"], sol_cu_price, 1)[1]
    
    met_total = calculate_solana_fee(met["add_liquidity"] + met["remove_liquidity"], sol_cu_price, 2)[1]
    pcs_total = calculate_evm_fee(pcs["mint_position"] + 280000, bsc_gas_price, PRICES_USD["BNB"])[1]
    uni_total = calculate_evm_fee(uni["mint_position"] + 320000, eth_gas_price, PRICES_USD["ETH"])[1]
    
    print(f"\n{'DEX':<20} {'程序费用':<12} {'UI估计':<12} {'差异':<10} {'备注'}")
    print("-" * 75)
    print(f"{'Raydium (Solana)':<20} {'$'+f'{ray_program:.4f}':<12} {'$'+f'{ray_ui:.4f}':<12} {'$'+f'{ray_program-ray_ui:.4f}':<10} 程序关仓3笔交易")
    print(f"{'Meteora (Solana)':<20} {'$'+f'{met_total:.4f}':<12} {'$'+f'{met_total:.4f}':<12} {'$0.0000':<10} 单笔交易")
    print(f"{'PancakeSwap (BSC)':<20} {'$'+f'{pcs_total:.4f}':<12} {'$'+f'{pcs_total:.4f}':<12} {'$0.0000':<10} 单笔交易")
    print(f"{'Uniswap (ETH)':<20} {'$'+f'{uni_total:.4f}':<12} {'$'+f'{uni_total:.4f}':<12} {'$0.0000':<10} 单笔交易")
    
    # ========== 费用差异可能原因 ==========
    print("\n" + "=" * 80)
    print("                    [分析] 程序与UI费用差异原因")
    print("=" * 80)
    
    print("""
## 主要发现

### 1. Raydium关仓使用多步骤交易 [重要!]
   
   程序实现 (liquidity.py):
   - Step 1: Remove all liquidity
   - Step 2: Claim fees/rewards  
   - Step 3: Close position (burn NFT)
   
   每步都是独立交易，各有Base Fee!
   
   UI可能实现:
   - 单笔交易完成所有操作

### 2. Approve交易 (EVM链)
   - 程序: 对每个代币单独执行approve交易 (首次交互时)
   - UI: 可能使用Permit2/Permit签名，无需额外交易
   - 差异: 每个代币约46,000 gas

### 3. 账户租金押金 (Solana) [不是费用]
   - Raydium: ~0.00289 SOL (关仓时退回)
   - Meteora: ~0.01 SOL (关仓时退回)
   - 如果被错误计入"费用"会造成误解

### 4. Gas/Compute设置差异
   - 程序使用保守估算，有缓冲
   - 实际消耗可能更低
""")

    print("\n" + "=" * 80)
    print("                    [建议] 优化方案")
    print("=" * 80)
    print("""
1. [Raydium] 考虑将关仓合并为单笔交易
   - 修改 generate_close_position_steps 逻辑
   - 或使用 Jito Bundle 打包多笔交易
   
2. [EVM] 使用Permit2减少approve交易
   - PancakeSwap和Uniswap都支持Permit2
   
3. 确保"费用"定义明确
   - 账户租金押金不应计入费用
   - 只统计gas/compute费用
""")

if __name__ == "__main__":
    print_report()
