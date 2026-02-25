# LP-DEX-BIN 日志增强修改

## 修改目的
支持 LP-BOT-BIN 记录完整的结构化日志，提供必要的交易执行数据

## 修改内容

### 1. types/result.py
- 新增 `SwapResult` 数据类，包含：
  - tx_result: 交易结果
  - from_token/to_token: 交易对
  - amount_in/amount_out: 交易金额
  - execution_price/expected_price: 执行/预期价格
  - slippage_bps/price_impact_bps: 滑点和价格影响

### 2. types/__init__.py
- 导出新增类型：OpenPositionResult, ClosePositionResult, SwapResult

### 3. modules/swap.py
- 修改 `swap()` 方法返回类型从 `TxResult` 改为 `SwapResult`
- 添加 quote 查询获取预期价格
- 计算执行价格、滑点等指标

### 4. modules/liquidity.py
- 修改导入，添加 datetime 和新增类型
- (待完成) 修改 `open()` 和 `close()` 返回完整结果

## 待完成
- [ ] liquidity.py 中 open() 返回 OpenPositionResult
- [ ] liquidity.py 中 close() 返回 ClosePositionResult

## 影响范围
- 不修改业务逻辑
- 只扩展返回字段
- 向后兼容（新增字段）

## 测试验证
- [ ] swap() 返回 SwapResult 正确
- [ ] SwapResult 包含 slippage_bps 字段
