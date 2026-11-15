# M9-T08 前端端到端验收（E2E）、Docker 容器化构建与 M9 结项报告

| 项 | 内容 |
|---|---|
| 波次 | Wave 5 |
| 依赖 | T01–T07 全部完成 |
| 阻塞 | M9 结项发布 |
| 分支 | `feat/m9-t08-frontend-e2e-closeout` |
| Issue | #172 |
| 建议规模 | 中（0.5 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
执行前端关键链路端到端验收（E2E-01 主链路、E2E-02 筛选到决策、E2E-03 异常降级），优化前端多阶段 Dockerfile 构建与 Nginx 生产反向代理，撰写结项报告 `docs/acceptance/M9.md`，打上 Git 语义化版本标签 `v0.9.0` 并发布。

---

## 2. 交付范围
1. **端到端 E2E 验收测试**：
   - E2E-01：注册登录 $\to$ 模拟盘创建 $\to$ 添加自选 AAPL $\to$ K 线技术信号 $\to$ AI 研究 $\to$ 买入建议 $\to$ 下限价单 $\to$ 交易日志全链路；
   - E2E-02：策略筛选标的 $\to$ 送入对比 $\to$ 长期持有评估；
   - E2E-03：数据过期 Warning 展示、AI 配额耗尽拦截提示。
2. **生产构建与容器化**：
   - 前端多阶段 Dockerfile（Node.js build $\to$ Nginx alpine 静态分发）；
   - Nginx 反向代理配置（`/api/` 转发后端，SPA 路由回退 `index.html`）。
3. **文档与版本发布**：
   - 结项报告 `docs/acceptance/M9.md`；
   - 更新 `docs/README.md` 与 `CHANGELOG.md`；
   - 发布 Git 标签 `v0.9.0` 与 GitHub Release。
