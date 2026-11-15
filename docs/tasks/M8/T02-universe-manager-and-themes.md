# M8-T02 股票池服务（UniverseManager）与主题股票池库（F9 核心定义与预设配置）

| 项 | 内容 |
|---|---|
| 波次 | Wave 2 |
| 依赖 | T01 |
| 阻塞 | T04, T05 |
| 分支 | `feat/m8-t02-universe-manager-themes` |
| Issue | #150 |
| 建议规模 | 中（0.5 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
在 `backend/app/modules/screener/` 下实现 `UniverseManager`，管理内置经典全市场基准股票池（标普 500、纳指 100、道琼斯 30），以及 F9 核心热门主题成分股库（AI 芯片、GLP-1 减肥药、高股息现金流、网络安全等），支持动态解析标的列表与主题详情。

---

## 2. 范围
**包含**
1. `backend/app/modules/screener/universe.py`：
   - 实现 `UniverseManager` 类，符合 `UniverseManagerProtocol`；
   - 内置股票池注册表：`sp500`, `nasdaq100`, `dow30`, `custom`；
   - 包含成分股票代码映射列表与大样本标的集；
   - 内置热门主题（F9）库定义：
     - `ai_chips`：英伟达、AMD、博通、台积电等；
     - `glp1_weightloss`：礼来、诺和诺德等；
     - `high_dividend`：可口可乐、强生、宝洁、雪佛龙等；
     - `cyber_security`：CrowdStrike、Palo Alto、Fortinet 等；
     - `cloud_saas`：微软、亚马逊、谷歌、赛富时等；
   - 主题元数据：中文名称、导语、新手向商业逻辑分析、成分标的画像。
2. 单元测试 `backend/tests/unit/modules/screener/test_universe_manager.py`：
   - 验证股票池列表读取、标的列表获取、不存在股票池/主题异常处理；
   - 验证所有预设主题的数据完整性（股票列表非空、代码大写规范）。

---

## 3. 验收标准
- [ ] 完整支持标普500、纳指100、道指30和自定义股票池获取
- [ ] 预设主题（$\ge 5$ 个）完整，覆盖 AI、减肥药、高分红等高频关注主题
- [ ] 单元测试覆盖率 $\ge 90\%$，`mypy --strict` 0 错误
