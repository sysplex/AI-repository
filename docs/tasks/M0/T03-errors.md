# M0-T03 统一错误体系

| 项 | 内容 |
|---|---|
| 波次 | Wave 1 |
| 依赖 | **T01、T02 已合并**（`request_id_var` 由 T02 导出，见下） |
| 阻塞 | T07 |
| 分支 | `feat/m0-t03-errors` |
| 建议规模 | 小–中 |
| 负责 Agent | _未分配_ |

## 目标
实现 `ErrorCode`、`AppError` 及全部子类、统一异常处理器，错误响应格式严格按 `CONTRACTS.md §4` 与 `docs/05-api-spec.md §1.1–1.2`。

## 对 T02 的依赖（顺序执行下为硬依赖）
响应体含 `request_id`，来自 `app.core.logging.request_id_var`。该变量由 **T02** 在 `core/logging.py` 中导出，T01 的空壳**不导出**（见 `CONTRACTS.md §1` 补充）。因此本任务必须等 T02 合并后开工；执行序列为 T02 → T03，原「软依赖」表述已取消。

## 范围
**包含**
1. `ErrorCode`（StrEnum）与 `AppError` 体系；每个子类的默认 `code`/`http_status`/默认中文 `message` 与 05 文档一致。
2. `register_exception_handlers(app)`：处理 `AppError`、`RequestValidationError`、`StarletteHTTPException`、`Exception`（见契约）。
3. 校验错误精简：`details.errors = [{"field": "body.qty", "message": "...", "type": "..."}]`；**不回显输入值**（避免泄露敏感信息）。
4. 500 处理：对外固定文案"服务器内部错误"，日志用 `get_logger` 记录完整异常（`exc_info`）与 request_id。
5. `RateLimited` 的 `Retry-After` 头。

**不包含**：具体业务错误的抛出（M1+）；日志实现（T02）。

## 文件所有权
- **拥有（可整体重写）**：`backend/app/core/errors.py`
- **新增测试**：`backend/tests/unit/core/test_errors.py`
- **不得修改**：其他文件

## 验收标准
- [ ] 每个 `ErrorCode` 与 05 文档 §1.2 一一对应（测试：枚举值集合 == 文档集合 + `INTERNAL_ERROR`）
- [ ] 每个子类的 `http_status` 与 05 文档一致（参数化测试）
- [ ] 在测试 app 中抛出各类 `AppError` → 状态码、响应体结构、`request_id` 字段正确
- [ ] 请求体校验失败 → 400 `VALIDATION_ERROR`，`details.errors` 精简且不含输入值（测试：提交含"secret-value"的非法 body，断言响应不含该字符串）
- [ ] 404（未知路由）、405 → 统一错误格式
- [ ] 未捕获异常 → 500，响应不含堆栈/异常文本，日志含完整堆栈（测试）
- [ ] `RateLimited(details={"retry_after": 30})` → 响应头 `Retry-After: 30`
- [ ] `make check` 全绿；覆盖率 ≥ 90%
