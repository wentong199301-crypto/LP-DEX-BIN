"""
运行所有开仓和撤仓测试，并汇总费用记录

WARNING: 这些测试会执行真实的交易并消耗真实的代币！
"""

import sys
from pathlib import Path
from datetime import datetime
import json

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 导入测试函数
from test.simple_test.raydium_test import main as test_raydium
from test.simple_test.meteora_test import main as test_meteora
from test.simple_test.uniswap_test import main as test_uniswap
from test.simple_test.pancakeswap_test import main as test_pancakeswap


def run_test_with_capture(test_name, test_func):
    """运行测试并捕获输出"""
    print(f"\n{'='*70}")
    print(f"运行测试: {test_name}")
    print(f"{'='*70}\n")
    
    import io
    from contextlib import redirect_stdout, redirect_stderr
    
    output = io.StringIO()
    error_output = io.StringIO()
    
    try:
        with redirect_stdout(output), redirect_stderr(error_output):
            success = test_func()
        output_text = output.getvalue()
        error_text = error_output.getvalue()
        
        # 打印输出
        print(output_text)
        if error_text:
            print("错误输出:", error_text)
        
        return {
            "name": test_name,
            "success": success,
            "output": output_text,
            "error": error_text,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        error_msg = f"测试执行异常: {e}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        return {
            "name": test_name,
            "success": False,
            "output": output_text if 'output_text' in locals() else "",
            "error": error_msg + "\n" + traceback.format_exc(),
            "timestamp": datetime.now().isoformat()
        }


def extract_costs_from_output(output_text):
    """从测试输出中提取费用信息"""
    costs = {}
    
    # 查找费用摘要部分
    if "COST SUMMARY" in output_text:
        lines = output_text.split("\n")
        in_cost_section = False
        
        for line in lines:
            if "COST SUMMARY" in line:
                in_cost_section = True
                continue
            
            if in_cost_section:
                if "Open fee:" in line:
                    # 提取开仓费用
                    try:
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if part == "lamports":
                                costs["open_lamports"] = int(parts[i-1].replace(",", ""))
                            elif part == "SOL)":
                                costs["open_sol"] = float(parts[i-1].replace("(", ""))
                    except:
                        pass
                
                elif "Close fee:" in line:
                    # 提取撤仓费用
                    try:
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if part == "lamports":
                                costs["close_lamports"] = int(parts[i-1].replace(",", ""))
                            elif part == "SOL)":
                                costs["close_sol"] = float(parts[i-1].replace("(", ""))
                    except:
                        pass
                
                elif "TOTAL FEES:" in line:
                    # 提取总费用
                    try:
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if part == "lamports":
                                costs["total_lamports"] = int(parts[i-1].replace(",", ""))
                            elif part == "SOL)":
                                costs["total_sol"] = float(parts[i-1].replace("(", ""))
                    except:
                        pass
                
                elif "=" * 50 in line or "=" * 60 in line:
                    # 费用摘要结束
                    break
    
    return costs


def main():
    """运行所有开仓和撤仓测试"""
    print("=" * 70)
    print("运行所有开仓和撤仓测试")
    print("=" * 70)
    print()
    print("WARNING: 这些测试会执行真实的交易并消耗真实的代币！")
    print()
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # 定义所有测试
    tests = [
        ("Raydium CLMM (Solana)", test_raydium),
        ("Meteora DLMM (Solana)", test_meteora),
        ("Uniswap V3 (Ethereum)", test_uniswap),
        ("PancakeSwap V3 (BSC)", test_pancakeswap),
    ]
    
    results = []
    passed = 0
    failed = 0
    skipped = 0
    
    # 运行每个测试
    for test_name, test_func in tests:
        result = run_test_with_capture(test_name, test_func)
        results.append(result)
        
        if result["success"]:
            passed += 1
            print(f"\n✓ {test_name}: 通过")
        else:
            if "SKIPPED" in result["output"] or "SKIPPED" in result["error"]:
                skipped += 1
                print(f"\n⊘ {test_name}: 跳过")
            else:
                failed += 1
                print(f"\n✗ {test_name}: 失败")
        
        # 提取费用信息
        costs = extract_costs_from_output(result["output"])
        if costs:
            result["costs"] = costs
            print(f"  费用信息: {costs}")
    
    # 打印汇总
    print("\n" + "=" * 70)
    print("测试汇总")
    print("=" * 70)
    print(f"  通过: {passed}")
    print(f"  失败: {failed}")
    print(f"  跳过: {skipped}")
    print(f"  总计: {len(tests)}")
    print()
    
    # 费用汇总
    print("=" * 70)
    print("费用汇总")
    print("=" * 70)
    
    solana_total = 0
    evm_costs = {}
    
    for result in results:
        if "costs" in result:
            costs = result["costs"]
            if "total_sol" in costs:
                solana_total += costs["total_sol"]
                print(f"\n{result['name']}:")
                print(f"  总费用: {costs.get('total_sol', 0):.9f} SOL")
                print(f"  (开仓: {costs.get('open_sol', 0):.9f} SOL, "
                      f"撤仓: {costs.get('close_sol', 0):.9f} SOL)")
    
    if solana_total > 0:
        print(f"\nSolana 链总费用: {solana_total:.9f} SOL")
    
    # 保存结果到文件
    results_file = project_root / "test" / "simple_test" / "test_results.json"
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "total": len(tests)
            },
            "results": results
        }, f, indent=2, ensure_ascii=False)
    
    print(f"\n测试结果已保存到: {results_file}")
    print("=" * 70)
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)


