"""
Raydium 指定池子开平仓测试

测试池子: 3ucNos4NbumPLZNWztqGHNFFgkHeRMBQAVemeeomsUxv

警告: 此测试执行真实交易，会消耗真实代币！
"""

import sys
import os
from decimal import Decimal
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

# 加载环境变量
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ============================================================
# 配置区域 - 请根据你的实际情况修改
# ============================================================

# 你的池子地址
POOL_ADDRESS = "3ucNos4NbumPLZNWztqGHNFFgkHeRMBQAVemeeomsUxv"

# RPC URL - 使用你自己的 RPC 或公共 RPC
RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")

# 钱包配置 (二选一)
# 方式1: 私钥文件路径 (使用原始字符串或正斜杠)
KEYPAIR_PATH = os.getenv("SOLANA_KEYPAIR_PATH", r"C:\wallets\test.json")
# 方式2: Base58 私钥字符串
PRIVATE_KEY = os.getenv("SOLANA_PRIVATE_KEY", None)

# 开仓参数
AMOUNT_USD = Decimal("2")  # 开仓金额 (USD)
PRICE_RANGE_PERCENT = 0.02  # 价格范围 (+/- 2%)
SLIPPAGE_BPS = 100  # 滑点 (1%)


# ============================================================
# 测试函数
# ============================================================

def create_client():
    """创建 DexClient"""
    from dex_adapter_universal import DexClient
    
    keypair_path = KEYPAIR_PATH
    
    # 处理路径中可能存在的引号和转义字符问题
    if keypair_path:
        keypair_path = keypair_path.strip('"').strip("'")
        # 修复 dotenv 中 \t 被解释为制表符的问题
        keypair_path = keypair_path.replace('\t', '\\t')
        # 规范化路径
        keypair_path = str(Path(keypair_path).resolve())
        print(f"  使用钱包文件: {keypair_path}")
    
    if keypair_path:
        return DexClient(rpc_url=RPC_URL, keypair_path=keypair_path)
    elif PRIVATE_KEY:
        return DexClient(rpc_url=RPC_URL, private_key=PRIVATE_KEY)
    else:
        raise ValueError(
            "请配置钱包！设置环境变量 SOLANA_KEYPAIR_PATH 或 SOLANA_PRIVATE_KEY"
        )


def test_query_pool(client):
    """测试1: 查询池子信息"""
    print("\n" + "="*60)
    print("测试1: 查询池子信息")
    print("="*60)
    
    pool = client.market.pool(POOL_ADDRESS, dex="raydium")
    
    print(f"  池子地址: {pool.address}")
    print(f"  Token0: {pool.token0.symbol} ({pool.token0.mint})")
    print(f"  Token1: {pool.token1.symbol} ({pool.token1.mint})")
    print(f"  当前价格: {pool.price}")
    print(f"  Tick Spacing: {getattr(pool, 'tick_spacing', 'N/A')}")
    
    return pool


def test_query_balance(client, pool):
    """测试2: 查询钱包余额"""
    print("\n" + "="*60)
    print("测试2: 查询钱包余额")
    print("="*60)
    
    print(f"  钱包地址: {client.wallet.address}")
    
    sol_balance = client.wallet.sol_balance()
    print(f"  SOL 余额: {sol_balance}")
    
    # 查询池子代币余额
    token0_balance = client.wallet.balance(pool.token0.mint)
    token1_balance = client.wallet.balance(pool.token1.mint)
    print(f"  {pool.token0.symbol} 余额: {token0_balance}")
    print(f"  {pool.token1.symbol} 余额: {token1_balance}")
    
    return sol_balance, token0_balance, token1_balance


def test_query_positions(client):
    """测试3: 查询现有仓位"""
    print("\n" + "="*60)
    print("测试3: 查询现有 Raydium 仓位")
    print("="*60)
    
    positions = client.lp.positions(dex="raydium")
    
    print(f"  找到 {len(positions)} 个仓位")
    
    for i, pos in enumerate(positions):
        print(f"\n  仓位 {i+1}:")
        print(f"    ID: {pos.id[:20]}...")
        if hasattr(pos, 'pool_address') and pos.pool_address:
            print(f"    Pool: {pos.pool_address[:20]}...")
        if hasattr(pos, 'tick_lower') and pos.tick_lower is not None:
            print(f"    Tick范围: {pos.tick_lower} ~ {pos.tick_upper}")
        if hasattr(pos, 'liquidity'):
            print(f"    流动性: {pos.liquidity}")
    
    return positions


def test_open_position(client, pool, auto_confirm=False):
    """测试4: 开仓 (真实交易!)"""
    print("\n" + "="*60)
    print("测试4: 开仓 (真实交易!)")
    print("="*60)
    
    from dex_adapter_universal.types import PriceRange
    
    print(f"  池子: {pool.address[:20]}...")
    print(f"  金额: ${AMOUNT_USD} USD")
    print(f"  价格范围: +/- {PRICE_RANGE_PERCENT*100}%")
    print(f"  滑点: {SLIPPAGE_BPS/100}%")
    
    if not auto_confirm:
        confirm = input("\n  确认开仓? (输入 'yes' 继续): ")
        if confirm.lower() != 'yes':
            print("  已取消开仓")
            return None
    else:
        print("\n  自动确认开仓 (--yes 参数)")
    
    print("\n  正在开仓...")
    result = client.lp.open(
        pool=pool,
        price_range=PriceRange.percent(PRICE_RANGE_PERCENT),
        amount_usd=AMOUNT_USD,
        slippage_bps=SLIPPAGE_BPS,
    )
    
    print(f"  状态: {result.status}")
    print(f"  交易签名: {result.signature}")
    
    if result.is_success:
        print("  [OK] 开仓成功!")
    else:
        print(f"  [FAILED] 开仓失败: {result.error}")
    
    return result


def test_close_position(client, position, auto_confirm=False):
    """测试5: 平仓 (真实交易!)"""
    print("\n" + "="*60)
    print("测试5: 平仓 (真实交易!)")
    print("="*60)
    
    print(f"  仓位ID: {position.id[:20]}...")
    
    if not auto_confirm:
        confirm = input("\n  确认平仓? (输入 'yes' 继续): ")
        if confirm.lower() != 'yes':
            print("  已取消平仓")
            return None
    else:
        print("\n  自动确认平仓 (--yes 参数)")
    
    print("\n  正在平仓...")
    result = client.lp.close(position)
    
    print(f"  状态: {result.status}")
    print(f"  交易签名: {result.signature}")
    
    if result.is_success:
        print("  [OK] 平仓成功!")
    else:
        print(f"  [FAILED] 平仓失败: {result.error}")
    
    return result


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Raydium 指定池子开平仓测试")
    parser.add_argument("--mode", "-m", type=str, choices=["1", "2", "3", "4", "query", "open", "close", "full"],
                       help="测试模式: 1/query=只查询, 2/open=开仓, 3/close=平仓, 4/full=完整流程")
    parser.add_argument("--yes", "-y", action="store_true", help="跳过确认提示")
    parser.add_argument("--position", "-p", type=int, default=1, help="平仓时选择的仓位序号 (默认1)")
    args = parser.parse_args()
    
    print("="*60)
    print("Raydium 指定池子开平仓测试")
    print("="*60)
    print(f"池子地址: {POOL_ADDRESS}")
    print(f"RPC: {RPC_URL[:50]}...")
    
    # 获取模式
    mode = args.mode
    if not mode:
        print("\n选择测试模式:")
        print("  1. 只查询 (不执行交易)")
        print("  2. 开仓测试 (真实交易)")
        print("  3. 平仓测试 (真实交易)")
        print("  4. 完整流程 (开仓 -> 查询 -> 平仓)")
        mode = input("\n请输入选项 (1/2/3/4): ").strip()
    
    # 标准化模式
    mode_map = {"query": "1", "open": "2", "close": "3", "full": "4"}
    mode = mode_map.get(mode, mode)
    
    # 创建客户端
    print("\n创建客户端...")
    try:
        client = create_client()
        print(f"  [OK] 客户端创建成功")
        print(f"  钱包: {client.wallet.address}")
    except Exception as e:
        print(f"  [FAILED] 客户端创建失败: {e}")
        return False
    
    auto_confirm = args.yes
    position_idx = args.position - 1  # 转为0索引
    
    try:
        if mode == "1":
            # 只查询
            pool = test_query_pool(client)
            test_query_balance(client, pool)
            test_query_positions(client)
            
        elif mode == "2":
            # 开仓
            pool = test_query_pool(client)
            test_query_balance(client, pool)
            test_open_position(client, pool, auto_confirm)
            
        elif mode == "3":
            # 平仓
            positions = test_query_positions(client)
            if positions:
                if auto_confirm:
                    # 使用命令行指定的序号
                    idx = position_idx
                else:
                    # 让用户选择要平的仓位
                    print("\n选择要平仓的仓位序号 (从1开始):")
                    idx = int(input("  序号: ")) - 1
                    
                if 0 <= idx < len(positions):
                    test_close_position(client, positions[idx], auto_confirm)
                else:
                    print(f"  无效的序号 (有效范围: 1-{len(positions)})")
            else:
                print("  没有找到可平仓的仓位")
                
        elif mode == "4":
            # 完整流程
            pool = test_query_pool(client)
            test_query_balance(client, pool)
            positions_before = test_query_positions(client)
            
            result = test_open_position(client, pool, auto_confirm)
            if result and result.is_success:
                import time
                print("\n  等待5秒让交易确认...")
                time.sleep(5)
                
                positions_after = test_query_positions(client)
                if positions_after:
                    # 平最新的仓位
                    test_close_position(client, positions_after[0], auto_confirm)
                    
        else:
            print("无效的选项")
            return False
            
    except Exception as e:
        print(f"\n[ERROR] 测试出错: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n" + "="*60)
    print("测试完成!")
    print("="*60)
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

