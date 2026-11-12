# Changelog

格式遵循 Keep a Changelog；按模块分类。

> **维护归属（M0）**：本文件归协调者维护。M0 阶段 T01–T10 一律不改本文件，各任务把条目草稿放进 PR「遗留问题」段；由 T11 一次性汇总写入。见 `AGENTS.md §7` 与 `docs/tasks/M0/README.md` 所有权矩阵。

## [Unreleased]

### Added
- docs: 设计文档集（01–09）
- docs: M0 任务拆分与接口契约
- M0 地基 T01：项目骨架与工具链（Python 3.12 + `uv --frozen`、ruff / `mypy --strict` / import-linter / pytest、Makefile）
- M0 地基 T02–T03：配置校验与结构化日志、请求上下文、统一错误体系
- M0 地基 T04–T06：异步数据层与 Alembic 迁移/审计表、进程内事件总线、NYSE 日历（2024–2026）与可替换时钟
- M0 地基 T07–T08：Redis 客户端、健康探针、Prometheus 指标与生命周期；Docker Compose 全栈、Nginx 代理、非 root 镜像
- M0 地基 T09：GitHub Actions 7 个门禁 job、Dependabot、CODEOWNERS，以及私有仓库无分支保护的替代做法（`docs/ci.md §6.2`）
- M0 地基 T10：共享测试基座、覆盖率门槛 80 与测试指南
- M0 地基 T11：集成验收记录 `docs/acceptance/M0.md`、全链路冒烟与性能基线
- M1 阶段 0：任务总览、接口契约与 T01–T07 任务卡（`docs/tasks/M1/`），M1 Identity 里程碑与 #36–#42 Issue
- M1-T01（#36）：`argon2-cffi` / `PyJWT` / `email-validator` 依赖与 `uv.lock`、7 个可选认证配置项、identity 四张表的 ORM 模型与端口、`0002_identity` 迁移（含 `audit_log.user_id` 外键）、import-linter 契约修正、`docs/03 §3.1` 与环境变量模板登记

### Changed
- CI：Dependabot 三个 ecosystem 忽略 `semver-major` 升级，避免跨大版本 PR 反复破坏 `uv --frozen` 与固定 SHA 基线（#28/#29 留待 M1 结项后评估）

### Fixed
- M0-F1（#24）：500 响应回写 `X-Request-ID` 与三项安全头，服务端生成的 `request_id` 不再丢失
- M0-F2（#25）：配置层拒绝 `CORS_ORIGINS` 通配符，避免 `allow_credentials=True` 下反射任意来源
- M0-F3（#26）：worker 改用 `load_settings_or_exit()`、关闭 uvicorn 重复访问日志、清理 T02 冗余测试兜底
- T11 接缝：`app/core/logging.py` 不再桥接 `uvicorn.access`，使 `--no-access-log` 真正生效（每次请求仅 1 条带 `request_id` 的 `http.access`）
- T09：`hashFiles()` 不得用于 job 级 `if` 导致 0 job failure，改为 step 级输出 + `needs` 守卫
