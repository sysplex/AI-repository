# M6-T05 新手可读性校验与强制合规包装器（Novice Readability & Compliance Guardrail）

| 项 | 内容 |
|---|---|
| 波次 | Wave 4 |
| 依赖 | T01, T04 |
| 阻塞 | T06, T07, T08 |
| 分支 | `feat/m6-t05-novice-compliance` |
| Issue | #121 |
| 建议规模 | 中（0.5 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
构建新手可读性校验与合规保障模块（`compliance.py`）：
1. 术语通俗度检查与白话翻译辅助，确保生僻专业指标配有易懂解释与新手总结；
2. 强制投资研究免责声明注入；
3. 财报指引等缺失数据强制标准化标注为“数据缺失”。

---

## 2. 范围
**包含**
1. `backend/app/modules/research/compliance.py`：
   - `ensure_compliance_disclaimer(report_dict) -> dict`：保证免责声明始终存在；
   - `check_novice_readability(payload) -> bool`：术语覆盖率检查与警告；
   - `normalize_missing_earnings_fields(payload, missing_fields) -> dict`：财报缺失项强制标记为“数据缺失”。
2. 将合规包装机制集成至 `ResearchService` 结果返回管道。
3. `backend/tests/unit/modules/research/test_compliance.py`：
   - 验证免责声明存在性、缺失字段转换与新手术语检查。

---

## 3. 文件所有权
- **创建并拥有**：
  - `backend/app/modules/research/compliance.py`
  - `backend/tests/unit/modules/research/test_compliance.py`
- **协同修改**：
  - `backend/app/modules/research/service.py`

---

## 4. 验收标准
- [x] 无论 LLM 输出为何，最终返回的信封必含标准免责声明
- [x] 缺失数据项明确替换为“数据缺失”，不产生空指针或无根据幻觉
- [x] 单测覆盖率 $\ge 90\%$
