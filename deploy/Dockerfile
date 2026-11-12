# M0-T08 多阶段构建：builder 用 uv 装依赖，runtime 只带 venv 与源码，非 root 运行。
# 同一镜像供 api / worker / migrate 三种角色复用，通过 compose 的 command 区分。
# 说明：不声明 `# syntax=docker/dockerfile:1.x`，本文件只用经典指令，
# 走 Docker 内置前端即可，避免 CI/内网环境额外拉取 dockerfile 前端镜像。

ARG PYTHON_VERSION=3.12.15

# uv 二进制来源 stage。tag 必须写死：`COPY --from=` 不支持变量展开，
# 用独立 stage 而不是 `--from=ghcr.io/astral-sh/uv:${UV_VERSION}`。
FROM ghcr.io/astral-sh/uv:0.13.7 AS uv-bin

# ---------- builder ----------
FROM python:${PYTHON_VERSION}-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

COPY --from=uv-bin /uv /usr/local/bin/uv

WORKDIR /src

# 先只拷依赖清单，让依赖层可缓存：源码变更不触发重新解析依赖。
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 再拷源码并安装项目自身（package = false，因此只是把 app 放进 venv 可导入位置）。
COPY backend/ ./
RUN uv sync --frozen --no-dev

# ---------- runtime ----------
FROM python:${PYTHON_VERSION}-slim AS runtime

ARG PYTHON_VERSION

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONHASHSEED=random \
    PATH="/opt/venv/bin:$PATH" \
    APP_HOME=/app

# 非 root：固定 uid/gid，便于宿主侧卷权限与审计。
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin app

WORKDIR ${APP_HOME}

COPY --from=builder --chown=app:app /opt/venv /opt/venv
COPY --chown=app:app backend/ ${APP_HOME}/

# 迁移脚本以只读方式随镜像发布；运行期不写代码目录。
USER app

EXPOSE 8000

# 只用标准库探活，镜像里不装 curl/wget。
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status == 200 else 1)"]

# 应用自身在 RequestContextMiddleware 输出带 request_id 的 `http.access` 日志；
# 关掉 uvicorn.access，避免每个请求重复两行（M0-F3 / Issue #26）。
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-access-log"]
