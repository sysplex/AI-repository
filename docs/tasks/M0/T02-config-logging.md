# M0-T02 配置、日志与请求上下文

| 项 | 内容 |
|---|---|
| 波次 | Wave 1 |
| 依赖 | T01 已合并 |
| 阻塞 | T04、T07、T10 |
| 分支 | `feat/m0-t02-config-logging` |
| 建议规模 | 中 |
| 负责 Agent | _未分配_ |

## 目标
实现 `Settings`、结构化日志、请求上下文中间件（request_id）、CORS 与安全响应头，严格按 `CONTRACTS.md §2、§3`。

## 范围
**包含**
1. `core/config.py`：完整 `Settings`、`get_settings()`；校验规则：`database_url` 必须以 `postgresql+asyncpg://` 开头，`redis_url` 以 `redis://` 或 `rediss://` 开头，`secret_key` ≥ 32 字符；`cors_origins` 同时支持 JSON 数组与逗号分隔字符串；`.env` 仅在 `app_env=local` 时读取。
2. 启动失败友好提示：缺失/非法变量**一次性全部列出**（变量名 + 原因），不暴露任何值；退出码 ≠ 0。提供一个小函数 `load_settings_or_exit()` 供 `main`/`worker` 使用（`create_app()` 内部仍调 `get_settings()`；`get_settings()` 抛出的异常应是可读的）。
3. `core/logging.py`：structlog + 标准库桥接（uvicorn/sqlalchemy/arq 的日志也进入同一格式）；`request_id_var/user_id_var/task_id_var` 自动并入每条日志。
4. `core/middleware.py`：`RequestContextMiddleware`（X-Request-ID 处理、访问日志）、`SecurityHeadersMiddleware`、CORS；`install_middlewares` 内用注释标明「指标中间件插入点」（**T02 只留注释，不得自行调用** `install_metrics`；T07 在该处替换为唯一一行调用 `install_metrics(app, settings)`，见 `CONTRACTS.md §3/§8`。T07 对本文件的修改权限仅限这一行）。
5. 敏感信息保护：日志与 `repr(Settings)` 不得泄露 `secret_key`、`database_url` 中的密码（以 `***` 代替）；访问日志不记录 `Authorization`、`Cookie`、请求体。

**阶段切换点**：T01 空壳 `Settings` 不校验三必填变量且 `uvicorn` 可空壳启动；**本任务合并后**启用「缺失/非法即启动失败并一次性列出」，见 `CONTRACTS.md §2`。两条行为分属不同阶段，评审按阶段判定。

**不包含**：错误处理器（T03）、指标（T07）。

## 文件所有权
- **拥有（可整体重写）**：`backend/app/core/config.py`、`core/logging.py`、`core/middleware.py`
- **新增测试**：`backend/tests/unit/core/test_config.py`、`test_logging.py`、`test_middleware.py`
- **不得修改**：`main.py` 及其他任务文件

## 验收标准
- [ ] 缺失全部必填变量启动 → 一次列出 `DATABASE_URL, REDIS_URL, SECRET_KEY`（测试断言）
- [ ] `SECRET_KEY` 过短、`DATABASE_URL` 前缀错误 → 失败且信息可读
- [ ] `repr(settings)`、日志、异常信息中均不出现密钥与数据库密码（测试断言）
- [ ] 请求带合法 `X-Request-ID` → 响应头原样回写；不带/非法 → 生成新 UUID4（测试）
- [ ] JSON 日志每行含 `timestamp/level/event/request_id`；设置 `user_id_var` 后日志含 `user_id`（测试）
- [ ] 访问日志含方法/路径/状态码/耗时，不含 `Authorization`（测试：带该头的请求，断言日志文本不含其值）
- [ ] 安全响应头三项存在（测试）
- [ ] CORS：配置白名单后预检请求允许；未配置不安装（测试）
- [ ] `cors_origins` 两种格式解析正确（测试）
- [ ] `make check` 全绿；本任务相关模块覆盖率 ≥ 90%

## 交接说明
合并后通知协调者；T04（DB URL 来自 Settings）、T07 依赖本任务。
