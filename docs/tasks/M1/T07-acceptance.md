# M1-T07 集成验收、越权复核、演示脚本与结项 tag

> Issue [#42](https://github.com/sysplex/AI-repository/issues/42)｜分支 `chore/m1-t07-acceptance`｜依赖：T01–T06 全部合并｜规模：中
> 权威源：`docs/08-test-plan.md` M1 清单、`docs/07-delivery-standard.md §1.2`（DoD 12 项）、`docs/tasks/M0/T11-integration-acceptance.md`（M0 验收体例）。

## 1. 目标

独立复核 M1 全部验收项、补最小接缝修复、产出可复现的验收记录与演示脚本，把 M1 结项并打 tag。

## 2. 范围

**包含**
- 全新环境复核：`docker compose up -d --build` → 迁移 → `/readyz` → M1 全链路（本机无 Docker 时用一次性 GitHub runner 工作流，探针脚本不进入最终 main）。
- 接缝检查：AST 对照 `CONTRACTS.md` 全部 `def` / `class` 名、OpenAPI 与 `docs/05 §2.1` 端点逐行对照、`lint-imports` 5 契约、迁移 `downgrade base → upgrade head` 后 `/readyz` 仍 200。
- `docs/08-test-plan.md` M1 五项清单逐项勾选；`docs/acceptance/M1.md`（验收记录：五项证据、偏差表、越权矩阵复核、安全自检、性能/不变量说明、遗留问题）。
- `scripts/m1_demo.py`：非作者可运行的演示脚本（httpx 调本地 `/api/v1`，依次演示注册/登录/刷新/登出/me/改密重置），带 `--base-url` 参数与清晰输出；`docs/acceptance/M1.md` 写运行方式。
- `CHANGELOG.md` M1 汇总条目；`docs/README.md` 路线图状态行把 M1 置为 ✅（`M1–M10` 行拆为 `M1` 与 `M2–M10` 两行）。
- tag `m1-identity-v0.2.0`（annotated，指向 T07 合并后的 main）；向 Issue #42、审计锚点 #12 提交结项报告；M1 milestone 关闭。
- 最小接缝修复：只允许改 `app/main.py` 与各 M1 任务文件；发现契约问题先在 Issue 提出，不自行改签名。

**不含**
- 新功能、新端点、新迁移、新依赖；`docs/01/02/04/06/07/09`、`AGENTS.md`、根 `Makefile` 仍不得改。

## 3. 文件所有权

| 文件 | 动作 |
|---|---|
| `docs/acceptance/M1.md`、`scripts/m1_demo.py` | 新增 |
| `docs/08-test-plan.md`（仅 M1 清单勾选）、`CHANGELOG.md`、`docs/README.md`（仅路线图状态行） | 修改 |
| `backend/app/main.py` 与 M1 任务文件 | 仅最小接缝修复（无修复则不改） |

## 4. 接口

不改任何公开签名；验收以 `CONTRACTS.md` 与 `docs/05 §2.1` 为对照基准。

## 5. 验收标准

- [ ] `docs/08-test-plan.md` M1 五项清单全部勾选并附证据：认证全流程 + 登出失效、限流、越权覆盖全部私有端点（含 T06 的两个公开端点不泄露枚举）、登录/改密审计、admin 守卫。
- [ ] 越权矩阵复核：把 T05 矩阵扩展到 T06 之后的实际端点总数，逐行贴结果；任何私有端点缺失即退回。
- [ ] 接缝检查：CONTRACTS 声明名齐全（打印 `present/total` 与 `missing=0`）；OpenAPI 路径与 `docs/05 §2.1` 表一致（含 `/api/v1` 前缀）；`lint-imports` 5 契约全 kept。
- [ ] 迁移 `downgrade base → upgrade head` 后 `/readyz` 200；全新 checkout 按 `deploy/README.md` 从零启动成功。
- [ ] `make check` 等价门禁全绿，覆盖率 ≥ 80；main CI 7/7 job success；安全自检：`pip-audit`、`gitleaks --all` 全历史、镜像非 root、`/metrics` 外部 403、无密钥入库。
- [ ] `scripts/m1_demo.py` 在全新环境可运行（贴真实输出摘录）；`docs/acceptance/M1.md` 含运行命令。
- [ ] `CHANGELOG.md`、`docs/README.md`、tag、结项评论、milestone 关闭均完成；一次性探针文件不进入 main。

## 6. DoD

- [ ] 只改 §3 列出的文件
- [ ] 公开签名与 `CONTRACTS.md` 一致
- [ ] `make check` 等价门禁全绿
- [ ] 文档/CHANGELOG 随 PR
- [ ] PR 四段格式 + 逐条证据

## 7. 假设与偏差（必须登记）

- 本机无 Docker 且测试机 SSH 免密不可用，「从零启动全栈」由一次性 runner 工作流承载（与 M0 T11 一致），探针分支验证后删除。
- Q3（邮件服务商）、Q4（AI 配额）仍待拍板；M1 用端口化与可配置默认值满足验收，遗留项写入 `docs/acceptance/M1.md`。
- 私有仓库免费版无分支保护，继续按 `docs/ci.md §6.2` 团队约定执行。
- 上线前条件（凭据轮换、T08 验证栈清理、Dependabot #28/#29 评估）沿用 #12 记录，不因 M1 结项自动关闭。
