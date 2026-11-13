# M5-T02 LLMClient 适配器抽象、Mock 实现与高精 Token 计费器

| 项 | 内容 |
|---|---|
| 波次 | Wave 2（AI 基础设施） |
| 依赖 | T01 |
| 阻塞 | T04, T07 |
| 分支 | `feat/m5-t02-llm-client-pricing` |
| Issue | #102 |
| 建议规模 | 中（0.5–1 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
实现六边形架构下的 `LLMClient` 适配器（含全功能 `MockLLMClient` 与通用客户端框架）、各主流模型 Token 定价与高精 Decimal 计费计算器（`pricing.py`），严格遵循 `TID251` 外部 SDK 隔离规则。

---

## 2. 范围
**包含**
1. `backend/app/modules/ai/pricing.py`：
   - 模型价格注册表：支持 Claude 3.5 Sonnet, GPT-4o, DeepSeek-V3/R1, Gemini 1.5 Flash/Pro 等；
   - 高精 Decimal 计算：`calculate_cost(model, input_tokens, output_tokens) -> Decimal`（六位小数精度）。
2. `backend/app/modules/ai/adapters/mock.py`：
   - `MockLLMClient`：实现 `ports.LLMClient` 协议；
   - 支持设置预设返回（固定 JSON、原始文本、自定义 token 数与延迟）；
   - 支持注入异常模式：超时、网络断开、故意缺字段、越界枚举、编造数字、注入攻击文本。
3. `backend/app/modules/ai/adapters/base.py`：
   - 商业 LLM 客户端基础抽象与通用 HTTP/SDK 封装（如结构化 JSON 提示词注入与解析）。
4. `backend/tests/unit/modules/ai/test_pricing_and_mock.py`：
   - 计费计算单元测试、MockClient 各种异常与响应注入测试。

---

## 3. 文件所有权
- **创建并拥有**：
  - `backend/app/modules/ai/pricing.py`
  - `backend/app/modules/ai/adapters/__init__.py`
  - `backend/app/modules/ai/adapters/mock.py`
  - `backend/app/modules/ai/adapters/base.py`
  - `backend/tests/unit/modules/ai/test_pricing_and_mock.py`

---

## 4. 验收标准
- [x] `pricing.py` 严格使用 Decimal 运算，杜绝浮点精度丢失
- [x] `MockLLMClient` 满足各种单测场景与故障注入要求
- [x] 外部 SDK 导入严格限制在 `adapters/` 内部（通过 `ruff check` 与 `TID251`）
- [x] 单元测试覆盖率 $\ge 90\%$，`make check` 全绿
