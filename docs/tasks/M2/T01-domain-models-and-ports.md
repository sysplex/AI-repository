# M2-T01 领域数据模型、类型与 DataProvider 端口契约

| 项 | 内容 |
|---|---|
| 波次 | Wave 1（M2 首置任务） |
| 依赖 | M0 已结项 |
| 阻塞 | T02、T03、T04、T05、T06、T07 |
| 分支 | `feat/m2-t01-models-ports` |
| 建议规模 | 小–中（半天） |
| 负责 Agent | _待认领_ |

## 目标
建立 M2 数据模块核心领域类型模型（`models.py`）以及抽象数据提供者接口契约（`ports.py`），为数据库表、适配器、缓存及上层业务提供完备的类型定义与输入输出协议。

## 范围
**包含**
1. `backend/app/modules/marketdata/models.py`：
   - 严格按 `CONTRACTS.md §1` 实现不可变领域模型：
     `Bar`、`Quote`、`CompanyProfile`、`Fundamentals`、`FinancialStatements`、`EarningsEvent`、`EarningsHistory`、`NewsItem`、`AnalystRatings`、`CorporateAction`、`FactsSnapshot`。
   - 所有模型均使用 `ConfigDict(frozen=True)`。
   - 价格/金额使用 `Decimal`，时间使用带时区 UTC `datetime`，美东交易日使用 `date`。
2. `backend/app/modules/marketdata/ports.py`：
   - 严格按 `CONTRACTS.md §2` 实现 `DataProvider(Protocol)` 协议。
   - 包含完整的异步方法签名：`get_bars`、`get_quote`、`get_quotes`、`get_fundamentals`、`get_financial_statements`、`get_earnings`、`get_news`、`get_analyst_ratings`、`get_corporate_actions`、`get_profile`、`get_universe`。
3. 单元测试 `backend/tests/unit/modules/marketdata/test_models.py`：
   - 验证各模型不可变性（修改抛出 ValidationError）。
   - 验证各模型序列化与反序列化。
   - 验证 `Decimal` 精度与缺失字段收集逻辑。

**不包含**
- 数据库表定义与 Alembic（归 T02）。
- 任何具体数据源适配器实现（归 T03）。
- 外部依赖与网络调用。

## 文件所有权
- **创建并拥有**：
  - `backend/app/modules/marketdata/models.py`
  - `backend/app/modules/marketdata/ports.py`
  - `backend/tests/unit/modules/marketdata/test_models.py`
  - `backend/tests/unit/modules/marketdata/__init__.py`
  - `backend/tests/unit/modules/__init__.py`
- **不得修改**：
  - `backend/pyproject.toml`
  - `app/core/**`
  - `docs/**`

## 验收标准
- [ ] `models.py` 与 `ports.py` 完全符合 `CONTRACTS.md §1` 与 `§2` 签名
- [ ] 单元测试全部通过：验证字段类型、Decimal 精度、时区感知、frozen 不可变性
- [ ] `make check`（ruff + mypy --strict + import-linter + pytest）全部通过，无类型错误
