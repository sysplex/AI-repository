# M5-T04 输出 Schema 校验器、JSON 清洗与单次自动重试包装

| 项 | 内容 |
|---|---|
| 波次 | Wave 3（AI 防御机制） |
| 依赖 | T01, T02, T03 |
| 阻塞 | T07 |
| 分支 | `feat/m5-t04-schema-validation-retry` |
| Issue | #104 |
| 建议规模 | 中（0.5–1 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
构建严密的输出 Schema 校验引擎（`validator.py`）与单次自动反馈重试包装器（`retry.py`），对 LLM 响应进行鲁棒的 JSON 清洗提取、Pydantic 校验与失败修正反馈，杜绝破损半成品输出。

---

## 2. 范围
**包含**
1. `backend/app/modules/ai/validator.py`：
   - 健壮的 JSON 提取器：剥离 markdown ```json 围栏、控制字符、尾随逗号；
   - Pydantic 模型动态/静态校验器：字段存在性、类型强约束、枚举合规性、数值区间检查；
   - 结构化错误提取：将 `ValidationError` 转换为 LLM 易懂的纠错提示。
2. `backend/app/modules/ai/retry.py`：
   - 执行包装器：初次调用 LLM $\to$ JSON 提取与 Schema 校验；
   - 若校验失败，构建携带具体字段缺失或枚举非法的纠错消息，自动向 LLM 发起 1 次重试修正；
   - 重试仍失败则抛出 `SchemaValidationError`，将报告标记为 `failed`，不输出破损半成品。
3. `backend/tests/unit/modules/ai/test_schema_validator.py`：
   - 缺字段拦截、枚举越界拦截、格式畸形修正重试成功与重试耗尽失败全分支测试。

---

## 3. 文件所有权
- **创建并拥有**：
  - `backend/app/modules/ai/validator.py`
  - `backend/app/modules/ai/retry.py`
  - `backend/tests/unit/modules/ai/test_schema_validator.py`

---

## 4. 验收标准
- [ ] 缺字段、枚举越界 100% 拦截并触发反馈重试
- [ ] 重试成功返回规范化模型，重试失败抛出统一异常并标记状态
- [ ] 单元测试覆盖率 $\ge 90\%$，`make check` 全绿
