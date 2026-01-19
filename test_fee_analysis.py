"""
DEX 开撤仓费用分析测试脚本

测试各个DEX的开仓和撤仓操作，记录实际费用消耗。
费用定义：付出后不会退回的钱（如gas费），不包括押金。

测试池子：
- Raydium: AQAGYQsdU853WAKhXM79CgNdoyhrRwXvYHX6qrDyC1FS
- PancakeSwap: 0x4a3218606AF9B4728a9F187E1c1a8c07fBC172a9
- Uniswap: 0x4e68Ccd3E89f51C3074ca5072bbAC773960dFa36
- Meteora: HTvjzsfX3yU6BUodCjZ5vZkUrAxMDTrBs3CJaq43ashR
"""

import os
import sys
import time
from decimal import Decimal
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Load .env file
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass


@dataclass
class FeeRecord:
    """费用记录"""
    dex: str
    pool: str
    operation: str  # "open" or "close"
    
    # 余额变化
    native_before: Decimal
    native_after: Decimal
    token0_before: Decimal
    token0_after: Decimal
    token1_before: Decimal
    token1_after: Decimal
    
    # 交易信息
    tx_hash: Optional[str] = None
    success: bool = False
    error: Optional[str] = None
    
    # 预估gas费 (用于EVM链)
    gas_used: Optional[int] = None
    gas_price: Optional[int] = None
    
    @property
    def native_fee(self) -> Decimal:
        """原生代币费用消耗"""
        return self.native_before - self.native_after
    
    @property
    def token0_change(self) -> Decimal:
        """Token0 变化"""
        return self.token0_after - self.token0_before
    
    @property
    def token1_change(self) -> Decimal:
        """Token1 变化"""
        return self.token1_after - self.token1_before


class FeeAnalyzer:
    """费用分析器"""
    
    def __init__(self):
        self.records: list[FeeRecord] = []
    
    def add_record(self, record: FeeRecord):
        self.records.append(record)
        self._print_record(record)
    
    def _print_record(self, record: FeeRecord):
        """打印单条记录"""
        print(f"\n{'='*60}")
        print(f"DEX: {record.dex} | 操作: {record.operation}")
        print(f"池子: {record.pool[:20]}...")
        print(f"状态: {'成功' if record.success else '失败'}")
        if record.error:
            print(f"错误: {record.error}")
        if record.tx_hash:
            print(f"TX: {record.tx_hash}")
        print(f"-"*40)
        print(f"原生代币费用: {record.native_fee:.8f}")
        print(f"  开始: {record.native_before:.8f}")
        print(f"  结束: {record.native_after:.8f}")
        print(f"Token0 变化: {record.token0_change:.8f}")
        print(f"Token1 变化: {record.token1_change:.8f}")
        if record.gas_used:
            print(f"Gas使用: {record.gas_used}")
    
    def print_summary(self):
        """打印汇总"""
        print("\n" + "="*70)
        print("费用分析汇总")
        print("="*70)
        
        # 按DEX分组
        by_dex: Dict[str, list[FeeRecord]] = {}
        for r in self.records:
            if r.dex not in by_dex:
                by_dex[r.dex] = []
            by_dex[r.dex].append(r)
        
        for dex, records in by_dex.items():
            print(f"\n{dex}:")
            print("-"*50)
            
            open_records = [r for r in records if r.operation == "open" and r.success]
            close_records = [r for r in records if r.operation == "close" and r.success]
            
            if open_records:
                avg_open_fee = sum(r.native_fee for r in open_records) / len(open_records)
                print(f"  开仓费用: {avg_open_fee:.8f} (平均)")
                for i, r in enumerate(open_records):
                    print(f"    #{i+1}: {r.native_fee:.8f}")
            
            if close_records:
                avg_close_fee = sum(r.native_fee for r in close_records) / len(close_records)
                print(f"  撤仓费用: {avg_close_fee:.8f} (平均)")
                for i, r in enumerate(close_records):
                    print(f"    #{i+1}: {r.native_fee:.8f}")
            
            total_fee = sum(r.native_fee for r in records if r.success)
            print(f"  总费用: {total_fee:.8f}")


# ============================================================================
# Raydium 测试
# ============================================================================

def test_raydium_fees(analyzer: FeeAnalyzer):
    """测试 Raydium 开撤仓费用"""
    print("\n" + "="*70)
    print("测试 Raydium 费用")
    print("="*70)
    
    POOL = "AQAGYQsdU853WAKhXM79CgNdoyhrRwXvYHX6qrDyC1FS"
    
    try:
        from test.module_test.conftest import create_client
        from dex_adapter_universal.types import PriceRange
        
        client = create_client()
        owner = client.wallet.address
        print(f"钱包地址: {owner}")
        
        # 获取池子信息
        pool = client.market.pool(POOL, dex="raydium")
        if not pool:
            print(f"无法获取池子: {POOL}")
            return
        
        print(f"池子: {pool.symbol}")
        print(f"当前价格: {pool.price}")
        
        # 1. 记录开仓前余额
        sol_before = client.wallet.balance("SOL")
        
        # 获取token余额
        token0_before = Decimal("0")
        token1_before = Decimal("0")
        try:
            # 尝试获取代币余额
            if pool.token0.symbol:
                token0_before = client.wallet.balance(pool.token0.symbol)
            if pool.token1.symbol:
                token1_before = client.wallet.balance(pool.token1.symbol)
        except Exception as e:
            print(f"获取代币余额失败: {e}")
        
        print(f"\n开仓前余额:")
        print(f"  SOL: {sol_before}")
        print(f"  {pool.token0.symbol or 'Token0'}: {token0_before}")
        print(f"  {pool.token1.symbol or 'Token1'}: {token1_before}")
        
        # 2. 执行开仓
        print(f"\n执行开仓...")
        open_result = client.lp.open(
            pool=pool,
            price_range=PriceRange.percent(0.02),
            amount_usd=Decimal("2"),
            slippage_bps=100,
        )
        
        time.sleep(2)  # 等待区块确认
        
        # 3. 记录开仓后余额
        sol_after_open = client.wallet.balance("SOL")
        token0_after_open = Decimal("0")
        token1_after_open = Decimal("0")
        try:
            if pool.token0.symbol:
                token0_after_open = client.wallet.balance(pool.token0.symbol)
            if pool.token1.symbol:
                token1_after_open = client.wallet.balance(pool.token1.symbol)
        except:
            pass
        
        open_record = FeeRecord(
            dex="Raydium",
            pool=POOL,
            operation="open",
            native_before=sol_before,
            native_after=sol_after_open,
            token0_before=token0_before,
            token0_after=token0_after_open,
            token1_before=token1_before,
            token1_after=token1_after_open,
            tx_hash=open_result.signature,
            success=open_result.is_success,
            error=open_result.error if not open_result.is_success else None,
        )
        analyzer.add_record(open_record)
        
        if not open_result.is_success:
            print(f"开仓失败: {open_result.error}")
            return
        
        # 4. 获取新开的仓位
        print(f"\n等待仓位创建...")
        time.sleep(3)
        
        positions = client.lp.positions(dex="raydium")
        if not positions:
            print("没有找到仓位")
            return
        
        position = positions[0]
        print(f"仓位ID: {position.id[:20]}...")
        
        # 5. 记录撤仓前余额
        sol_before_close = client.wallet.balance("SOL")
        token0_before_close = Decimal("0")
        token1_before_close = Decimal("0")
        try:
            if pool.token0.symbol:
                token0_before_close = client.wallet.balance(pool.token0.symbol)
            if pool.token1.symbol:
                token1_before_close = client.wallet.balance(pool.token1.symbol)
        except:
            pass
        
        # 6. 执行撤仓
        print(f"\n执行撤仓...")
        close_result = client.lp.close(position)
        
        time.sleep(2)
        
        # 7. 记录撤仓后余额
        sol_after_close = client.wallet.balance("SOL")
        token0_after_close = Decimal("0")
        token1_after_close = Decimal("0")
        try:
            if pool.token0.symbol:
                token0_after_close = client.wallet.balance(pool.token0.symbol)
            if pool.token1.symbol:
                token1_after_close = client.wallet.balance(pool.token1.symbol)
        except:
            pass
        
        close_record = FeeRecord(
            dex="Raydium",
            pool=POOL,
            operation="close",
            native_before=sol_before_close,
            native_after=sol_after_close,
            token0_before=token0_before_close,
            token0_after=token0_after_close,
            token1_before=token1_before_close,
            token1_after=token1_after_close,
            tx_hash=close_result.signature,
            success=close_result.is_success,
            error=close_result.error if not close_result.is_success else None,
        )
        analyzer.add_record(close_record)
        
        # 8. 计算总费用
        print(f"\n=== Raydium 总费用分析 ===")
        total_sol_fee = sol_before - sol_after_close
        print(f"SOL 总消耗: {total_sol_fee:.8f} SOL")
        
        # 考虑代币退回
        token0_net = token0_after_close - token0_before
        token1_net = token1_after_close - token1_before
        print(f"Token0 净变化: {token0_net}")
        print(f"Token1 净变化: {token1_net}")
        
    except Exception as e:
        print(f"Raydium 测试失败: {e}")
        import traceback
        traceback.print_exc()


# ============================================================================
# Meteora 测试
# ============================================================================

def test_meteora_fees(analyzer: FeeAnalyzer):
    """测试 Meteora 开撤仓费用"""
    print("\n" + "="*70)
    print("测试 Meteora 费用")
    print("="*70)
    
    POOL = "HTvjzsfX3yU6BUodCjZ5vZkUrAxMDTrBs3CJaq43ashR"
    
    try:
        from test.module_test.conftest import create_client
        from dex_adapter_universal.types import PriceRange
        
        client = create_client()
        owner = client.wallet.address
        print(f"钱包地址: {owner}")
        
        # 获取池子信息
        pool = client.market.pool(POOL, dex="meteora")
        if not pool:
            print(f"无法获取池子: {POOL}")
            return
        
        print(f"池子: {pool.symbol}")
        print(f"当前价格: {pool.price}")
        
        # 1. 记录开仓前余额
        sol_before = client.wallet.balance("SOL")
        token0_before = Decimal("0")
        token1_before = Decimal("0")
        try:
            if pool.token0.symbol:
                token0_before = client.wallet.balance(pool.token0.symbol)
            if pool.token1.symbol:
                token1_before = client.wallet.balance(pool.token1.symbol)
        except:
            pass
        
        print(f"\n开仓前余额:")
        print(f"  SOL: {sol_before}")
        print(f"  {pool.token0.symbol or 'Token0'}: {token0_before}")
        print(f"  {pool.token1.symbol or 'Token1'}: {token1_before}")
        
        # 2. 执行开仓
        print(f"\n执行开仓...")
        open_result = client.lp.open(
            pool=pool,
            price_range=PriceRange.percent(0.02),
            amount_usd=Decimal("2"),
            slippage_bps=100,
        )
        
        time.sleep(2)
        
        # 3. 记录开仓后余额
        sol_after_open = client.wallet.balance("SOL")
        token0_after_open = Decimal("0")
        token1_after_open = Decimal("0")
        try:
            if pool.token0.symbol:
                token0_after_open = client.wallet.balance(pool.token0.symbol)
            if pool.token1.symbol:
                token1_after_open = client.wallet.balance(pool.token1.symbol)
        except:
            pass
        
        open_record = FeeRecord(
            dex="Meteora",
            pool=POOL,
            operation="open",
            native_before=sol_before,
            native_after=sol_after_open,
            token0_before=token0_before,
            token0_after=token0_after_open,
            token1_before=token1_before,
            token1_after=token1_after_open,
            tx_hash=open_result.signature,
            success=open_result.is_success,
            error=open_result.error if not open_result.is_success else None,
        )
        analyzer.add_record(open_record)
        
        if not open_result.is_success:
            print(f"开仓失败: {open_result.error}")
            return
        
        # 4. 获取新开的仓位
        print(f"\n等待仓位创建...")
        time.sleep(3)
        
        positions = client.lp.positions(dex="meteora")
        if not positions:
            print("没有找到仓位")
            return
        
        position = positions[0]
        print(f"仓位ID: {position.id[:20]}...")
        
        # 5. 记录撤仓前余额
        sol_before_close = client.wallet.balance("SOL")
        token0_before_close = Decimal("0")
        token1_before_close = Decimal("0")
        try:
            if pool.token0.symbol:
                token0_before_close = client.wallet.balance(pool.token0.symbol)
            if pool.token1.symbol:
                token1_before_close = client.wallet.balance(pool.token1.symbol)
        except:
            pass
        
        # 6. 执行撤仓
        print(f"\n执行撤仓...")
        close_result = client.lp.close(position)
        
        time.sleep(2)
        
        # 7. 记录撤仓后余额
        sol_after_close = client.wallet.balance("SOL")
        token0_after_close = Decimal("0")
        token1_after_close = Decimal("0")
        try:
            if pool.token0.symbol:
                token0_after_close = client.wallet.balance(pool.token0.symbol)
            if pool.token1.symbol:
                token1_after_close = client.wallet.balance(pool.token1.symbol)
        except:
            pass
        
        close_record = FeeRecord(
            dex="Meteora",
            pool=POOL,
            operation="close",
            native_before=sol_before_close,
            native_after=sol_after_close,
            token0_before=token0_before_close,
            token0_after=token0_after_close,
            token1_before=token1_before_close,
            token1_after=token1_after_close,
            tx_hash=close_result.signature,
            success=close_result.is_success,
            error=close_result.error if not close_result.is_success else None,
        )
        analyzer.add_record(close_record)
        
        # 8. 计算总费用
        print(f"\n=== Meteora 总费用分析 ===")
        total_sol_fee = sol_before - sol_after_close
        print(f"SOL 总消耗: {total_sol_fee:.8f} SOL")
        
    except Exception as e:
        print(f"Meteora 测试失败: {e}")
        import traceback
        traceback.print_exc()


# ============================================================================
# PancakeSwap 测试
# ============================================================================

def test_pancakeswap_fees(analyzer: FeeAnalyzer):
    """测试 PancakeSwap 开撤仓费用"""
    print("\n" + "="*70)
    print("测试 PancakeSwap 费用")
    print("="*70)
    
    POOL = "0x4a3218606AF9B4728a9F187E1c1a8c07fBC172a9"
    
    try:
        from dex_adapter_universal.protocols.pancakeswap import PancakeSwapAdapter
        from dex_adapter_universal.infra.evm_signer import EVMSigner
        from dex_adapter_universal.types import PriceRange
        
        if not os.getenv("EVM_PRIVATE_KEY"):
            print("未设置 EVM_PRIVATE_KEY，跳过 PancakeSwap 测试")
            return
        
        signer = EVMSigner.from_env()
        adapter = PancakeSwapAdapter(chain_id=56, signer=signer)
        
        print(f"钱包地址: {adapter.address}")
        
        # 获取池子信息
        pool = adapter.get_pool_by_address(POOL)
        if not pool:
            print(f"无法获取池子: {POOL}")
            return
        
        print(f"池子: {pool.symbol}")
        print(f"当前价格: {pool.price}")
        
        # 1. 记录开仓前余额
        bnb_before = adapter.get_native_balance()
        token0_before = Decimal("0")
        token1_before = Decimal("0")
        try:
            token0_before = adapter.get_balance(pool.token0.mint)
            token1_before = adapter.get_balance(pool.token1.mint)
        except:
            pass
        
        print(f"\n开仓前余额:")
        print(f"  BNB: {bnb_before}")
        print(f"  {pool.token0.symbol}: {token0_before}")
        print(f"  {pool.token1.symbol}: {token1_before}")
        
        # 2. 执行开仓
        print(f"\n执行开仓...")
        open_result = adapter.open_position(
            pool=pool,
            price_range=PriceRange.percent(0.05),
            amount0=Decimal("0.005"),
            slippage_bps=100,
        )
        
        time.sleep(5)  # BSC确认时间
        
        # 3. 记录开仓后余额
        bnb_after_open = adapter.get_native_balance()
        token0_after_open = Decimal("0")
        token1_after_open = Decimal("0")
        try:
            token0_after_open = adapter.get_balance(pool.token0.mint)
            token1_after_open = adapter.get_balance(pool.token1.mint)
        except:
            pass
        
        open_record = FeeRecord(
            dex="PancakeSwap",
            pool=POOL,
            operation="open",
            native_before=bnb_before,
            native_after=bnb_after_open,
            token0_before=token0_before,
            token0_after=token0_after_open,
            token1_before=token1_before,
            token1_after=token1_after_open,
            tx_hash=open_result.signature,
            success=open_result.is_success,
            error=open_result.error if not open_result.is_success else None,
        )
        analyzer.add_record(open_record)
        
        if not open_result.is_success:
            print(f"开仓失败: {open_result.error}")
            return
        
        # 4. 获取新开的仓位
        print(f"\n等待仓位创建...")
        time.sleep(3)
        
        positions = adapter.get_positions()
        if not positions:
            print("没有找到仓位")
            return
        
        position = positions[0]
        print(f"仓位ID: {position.id}")
        
        # 5. 记录撤仓前余额
        bnb_before_close = adapter.get_native_balance()
        token0_before_close = Decimal("0")
        token1_before_close = Decimal("0")
        try:
            token0_before_close = adapter.get_balance(pool.token0.mint)
            token1_before_close = adapter.get_balance(pool.token1.mint)
        except:
            pass
        
        # 6. 执行撤仓
        print(f"\n执行撤仓...")
        close_result = adapter.close_position(position)
        
        time.sleep(5)
        
        # 7. 记录撤仓后余额
        bnb_after_close = adapter.get_native_balance()
        token0_after_close = Decimal("0")
        token1_after_close = Decimal("0")
        try:
            token0_after_close = adapter.get_balance(pool.token0.mint)
            token1_after_close = adapter.get_balance(pool.token1.mint)
        except:
            pass
        
        close_record = FeeRecord(
            dex="PancakeSwap",
            pool=POOL,
            operation="close",
            native_before=bnb_before_close,
            native_after=bnb_after_close,
            token0_before=token0_before_close,
            token0_after=token0_after_close,
            token1_before=token1_before_close,
            token1_after=token1_after_close,
            tx_hash=close_result.signature,
            success=close_result.is_success,
            error=close_result.error if not close_result.is_success else None,
        )
        analyzer.add_record(close_record)
        
        # 8. 计算总费用
        print(f"\n=== PancakeSwap 总费用分析 ===")
        total_bnb_fee = bnb_before - bnb_after_close
        print(f"BNB 总消耗: {total_bnb_fee:.8f} BNB")
        
    except Exception as e:
        print(f"PancakeSwap 测试失败: {e}")
        import traceback
        traceback.print_exc()


# ============================================================================
# Uniswap 测试
# ============================================================================

def test_uniswap_fees(analyzer: FeeAnalyzer):
    """测试 Uniswap 开撤仓费用"""
    print("\n" + "="*70)
    print("测试 Uniswap 费用")
    print("="*70)
    
    POOL = "0x4e68Ccd3E89f51C3074ca5072bbAC773960dFa36"
    
    try:
        from dex_adapter_universal.protocols.uniswap import UniswapAdapter
        from dex_adapter_universal.infra.evm_signer import EVMSigner
        from dex_adapter_universal.types import PriceRange
        
        if not os.getenv("EVM_PRIVATE_KEY"):
            print("未设置 EVM_PRIVATE_KEY，跳过 Uniswap 测试")
            return
        
        signer = EVMSigner.from_env()
        adapter = UniswapAdapter(chain_id=1, signer=signer)
        
        print(f"钱包地址: {adapter.address}")
        
        # 获取池子信息
        pool = adapter.get_pool_by_address(POOL)
        if not pool:
            print(f"无法获取池子: {POOL}")
            return
        
        print(f"池子: {pool.symbol}")
        print(f"当前价格: {pool.price}")
        
        # 1. 记录开仓前余额
        eth_before = adapter.get_native_balance()
        token0_before = Decimal("0")
        token1_before = Decimal("0")
        try:
            token0_before = adapter.get_balance(pool.token0.mint)
            token1_before = adapter.get_balance(pool.token1.mint)
        except:
            pass
        
        print(f"\n开仓前余额:")
        print(f"  ETH: {eth_before}")
        print(f"  {pool.token0.symbol}: {token0_before}")
        print(f"  {pool.token1.symbol}: {token1_before}")
        
        # 2. 执行开仓
        print(f"\n执行开仓...")
        open_result = adapter.open_position(
            pool=pool,
            price_range=PriceRange.percent(0.05),
            amount0=Decimal("0.005"),  # 0.005 WETH
            slippage_bps=100,
        )
        
        time.sleep(15)  # ETH确认时间较长
        
        # 3. 记录开仓后余额
        eth_after_open = adapter.get_native_balance()
        token0_after_open = Decimal("0")
        token1_after_open = Decimal("0")
        try:
            token0_after_open = adapter.get_balance(pool.token0.mint)
            token1_after_open = adapter.get_balance(pool.token1.mint)
        except:
            pass
        
        open_record = FeeRecord(
            dex="Uniswap",
            pool=POOL,
            operation="open",
            native_before=eth_before,
            native_after=eth_after_open,
            token0_before=token0_before,
            token0_after=token0_after_open,
            token1_before=token1_before,
            token1_after=token1_after_open,
            tx_hash=open_result.signature,
            success=open_result.is_success,
            error=open_result.error if not open_result.is_success else None,
        )
        analyzer.add_record(open_record)
        
        if not open_result.is_success:
            print(f"开仓失败: {open_result.error}")
            return
        
        # 4. 获取新开的仓位
        print(f"\n等待仓位创建...")
        time.sleep(5)
        
        positions = adapter.get_positions(version="v3")
        if not positions:
            print("没有找到仓位")
            return
        
        position = positions[0]
        print(f"仓位ID: {position.id}")
        
        # 5. 记录撤仓前余额
        eth_before_close = adapter.get_native_balance()
        token0_before_close = Decimal("0")
        token1_before_close = Decimal("0")
        try:
            token0_before_close = adapter.get_balance(pool.token0.mint)
            token1_before_close = adapter.get_balance(pool.token1.mint)
        except:
            pass
        
        # 6. 执行撤仓
        print(f"\n执行撤仓...")
        close_result = adapter.close_position(position)
        
        time.sleep(15)
        
        # 7. 记录撤仓后余额
        eth_after_close = adapter.get_native_balance()
        token0_after_close = Decimal("0")
        token1_after_close = Decimal("0")
        try:
            token0_after_close = adapter.get_balance(pool.token0.mint)
            token1_after_close = adapter.get_balance(pool.token1.mint)
        except:
            pass
        
        close_record = FeeRecord(
            dex="Uniswap",
            pool=POOL,
            operation="close",
            native_before=eth_before_close,
            native_after=eth_after_close,
            token0_before=token0_before_close,
            token0_after=token0_after_close,
            token1_before=token1_before_close,
            token1_after=token1_after_close,
            tx_hash=close_result.signature,
            success=close_result.is_success,
            error=close_result.error if not close_result.is_success else None,
        )
        analyzer.add_record(close_record)
        
        # 8. 计算总费用
        print(f"\n=== Uniswap 总费用分析 ===")
        total_eth_fee = eth_before - eth_after_close
        print(f"ETH 总消耗: {total_eth_fee:.8f} ETH")
        
    except Exception as e:
        print(f"Uniswap 测试失败: {e}")
        import traceback
        traceback.print_exc()


# ============================================================================
# 主函数
# ============================================================================

def main():
    """主函数"""
    print("="*70)
    print("DEX 开撤仓费用分析")
    print("="*70)
    print()
    print("警告：此脚本会执行真实交易并消耗代币！")
    print()
    
    analyzer = FeeAnalyzer()
    
    # 测试各个DEX
    test_raydium_fees(analyzer)
    test_meteora_fees(analyzer)
    test_pancakeswap_fees(analyzer)
    test_uniswap_fees(analyzer)
    
    # 打印汇总
    analyzer.print_summary()


if __name__ == "__main__":
    main()

