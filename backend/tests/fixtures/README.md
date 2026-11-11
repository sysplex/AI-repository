# 录制 fixture 目录规范（M0 / T10）

本目录存放**离线、可重复**的第三方响应录制文件与测试静态数据。业务行情样本由 M2 起按本规范补充；本任务只提供规范、加载器与一个基础设施冒烟样例。

## 目录与命名

```
tests/fixtures/
  README.md              # 本文件
  loader.py              # load_fixture(path)
  <provider>/            # 数据源标识，如 yfinance / alpaca / nyse / m0
    <symbol>/            # 标的或主题，小写；不含斜杠，如 aapl / _smoke
      <endpoint>.json    # 端点或场景名，如 quote / daily / healthz
```

- 一律小写 ASCII 文件名，单词间用 `_` 或 `-`；禁止空格、中文、绝对路径。
- 同一端点不同参数用后缀区分：`daily_1y.json`、`daily_5y.json`。
- 只放 JSON；二进制响应、CSV、图片不放这里。
- 示例：`tests/fixtures/m0/_smoke/healthz.json` 是 T10 冒烟样例，**不是业务 fixture**。

## 加载方式

```python
from tests.fixtures.loader import load_fixture

payload = load_fixture("m0/_smoke/healthz.json")
assert payload["status"] == "ok"
```

`load_fixture` 会拒绝越界路径（`../` 或绝对路径）并对缺失文件抛 `FileNotFoundError`，避免测试静默读到错误数据。

## 脱敏（强制）

录制真实供应商响应后，提交前必须删除或替换：

- `Authorization` / `Cookie` / `api_key` / `token` 等请求与响应头字段；
- 账号 ID、真实用户 UUID、邮箱、手机号、IP；
- 任何可反推凭据的签名、时间戳签名串；
- 只保留业务字段，且把真实用户标识换成固定占位值（如 `00000000-0000-0000-0000-000000000001`）。

仓库已启用 `detect-private-key` 与 `detect-secrets` 两个 pre-commit hook；提交前执行 `pre-commit run --all-files` 自检。**任何密钥都不允许写进 fixture**。

## 重新录制

1. 在**隔离测试环境**（非生产）用真实凭据调用供应商，保存原始响应到临时目录（不要放进仓库）。
2. 运行脱敏脚本/人工核对，删掉上节列出的字段。
3. 按上面的目录规范落盘为 `<provider>/<symbol>/<endpoint>.json`，UTF-8、2 空格缩进。
4. 在 fixture 顶层可选加 `"_recorded_at": "YYYY-MM-DD"` 说明录制日期；**不得**加凭据或环境名。
5. 更新引用该 fixture 的契约测试期望值，并在 PR「验收证据」写明录制来源与脱敏项。
6. 运行 `make check`；`detect-secrets` 通过后才允许合并。

## 约定

- 契约测试（外部适配器）复用同一套录制 fixture，保证不同实现行为一致；
- 涉及「当前时间」的断言必须使用 `frozen_clock` fixture，不得依赖真实时钟；
- fixture 只是输入，测试不得反向修改仓库里的录制文件。
