# M2-T03 YFinance 数据源适配器、离线 Fixture 与契约测试

| 项 | 内容 |
|---|---|
| 波次 | Wave 2 |
| 依赖 | T01 已合并 |
| 阻塞 | T04、T05、T07 |
| 分支 | `feat/m2-t03-yfinance-adapter` |
| 建议规模 | 中–大（1天） |
| 负责 Agent | _待认领_ |

## 目标
实现实现首个数据源适配器 `YFinanceAdapter`（遵循 `DataProvider` 契约），引入 `yfinance` 依赖，提供离线 Fixture 录制/回放机制与完整的契约测试套件，确保无需外网即可稳定运行。

## 范围
**包含**
1. 依赖配置更新（`backend/pyproject.toml`）：
   - 将 `yfinance` 引入 `dependencies`。
   - 在 `[tool.ruff.lint.per-file-ignores]` 中为 `app/modules/*/adapters/**` 放行 `TID251`，确保仅能在适配器中导入 `yfinance`。
   - 更新并提交 `uv.lock`。
2. `backend/app/modules/marketdata/adapters/yfinance.py`：
   - 实现 `DataProvider` 协议中规定的全部方法。
   - 所有 `yfinance` 阻塞方法通过 `asyncio.to_thread` 执行。
   - 数据转换逻辑：将 yfinance 的 DataFrame/dict 转换为强类型的 `Bar`、`Quote`、`Fundamentals` 等领域模型，金额转换为 `Decimal`。
   - 支持通过构造参数 `fixture_dir` 传入离线录制数据目录，优先回放。
3. 离线 Fixtures 数据录制与基线：
   - 放置于 `backend/tests/fixtures/m2/`，包含 AAPL, MSFT, NVDA 的历史 K 线、分红/拆股、报价及财务数据样例。
4. 契约测试 `backend/tests/contract/modules/marketdata/test_yfinance_contract.py`：
   - 针对 `DataProvider` 协议断言返回数据结构与字段类型。
   - 验证 NVDA 2024-06 拆股（10:1）在 `get_corporate_actions` 与复权价格 `adj_close` 中的正确性。

## 文件所有权
- **修改**：`backend/pyproject.toml`、`backend/uv.lock`
- **创建并拥有**：
  - `backend/app/modules/marketdata/adapters/__init__.py`
  - `backend/app/modules/marketdata/adapters/yfinance.py`
  - `backend/tests/fixtures/m2/**`
  - `backend/tests/contract/modules/marketdata/test_yfinance_contract.py`
  - `backend/tests/contract/modules/__init__.py`

## 验收标准
- [ ] `YFinanceAdapter` 完整实现 `DataProvider` 协议全部 11 个方法
- [ ] 所有外部 SDK 调用均在 `asyncio.to_thread` 内执行
- [ ] 契约测试使用本地 fixture 回放通过，在断网/离线环境下执行 `pytest tests/contract` 100% 成功
- [ ] NVDA 2024-06 拆股样例契约测试通过
- [ ] 架构规则守卫：业务层无 `import yfinance`，`make lint-imports` 与 `make check` 全部通过
