#!/usr/bin/env python3
"""M1 身份模块演示脚本（`docs/tasks/M1/T07-acceptance.md`）。

非作者也能跑：只依赖 `httpx`（已在 `backend/pyproject.toml` 中）与标准库，按顺序演示
注册 → 登录 → 资料 → 设置 → 用量 → 刷新 → 登出 → 密码重置，每步打印期望/实际状态码。

用法（服务端已启动，且 `APP_ENV=local` 让邮件走 `LoggingMailSender`）::

    python scripts/m1_demo.py --base-url http://127.0.0.1:8000

密码重置需要从服务端日志里取一次性令牌。若日志不在默认位置，用
``--reset-log`` 指定；确实拿不到时加 ``--skip-reset`` 跳过最后两步。

退出码：全部符合预期为 0；有失败为 1；只有跳过为 0。
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import uuid
from typing import Any

try:
    import httpx
except ImportError:  # pragma: no cover - 依赖缺失时给出可操作提示
    print("需要 httpx：在 backend 目录执行 `uv run python ../scripts/m1_demo.py`")
    raise SystemExit(2) from None

_API = "/api/v1"
_TOKEN_IN_LOG = re.compile(r"([A-Za-z0-9_-]{43})")
_MAIL_EVENT = "mail.send"
_OK = "✔"
_BAD = "✘"
_SKIP = "−"


class Demo:
    """按步骤执行并把结果累积成摘要。"""

    def __init__(self, client: httpx.Client) -> None:
        self._client = client
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self._total = 0

    def step(self, label: str, expected: int, response: httpx.Response) -> httpx.Response:
        self._total += 1
        ok = response.status_code == expected
        mark = _OK if ok else _BAD
        print(f"[{self._total:>2}] {label:<34} {response.status_code} (期望 {expected}) {mark}")
        if ok:
            self.passed += 1
        else:
            self.failed += 1
            print(f"     响应：{response.text[:300]}")
        return response

    def skip(self, label: str, reason: str) -> None:
        self._total += 1
        self.skipped += 1
        print(f"[{self._total:>2}] {label:<34} {_SKIP} 跳过（{reason}）")

    def info(self, text: str) -> None:
        print(f"     {text}")

    def summary(self) -> int:
        print("-" * 72)
        print(f"结果：{self.passed} 通过 / {self.failed} 失败 / {self.skipped} 跳过")
        return 0 if self.failed == 0 else 1


def _read_reset_token(path: str, *, timeout: float) -> str | None:
    """从服务端日志里取最后一次 `mail.send` 的正文令牌（本地日志投递专用）。

    日志可能由 `docker compose logs -f` 之类的跟随进程写入，落盘比响应稍晚，
    所以在 `timeout` 秒内轮询，避免偶发竞态。
    """
    deadline = time.monotonic() + timeout
    while True:
        token = _scan_reset_token(path)
        if token is not None or time.monotonic() >= deadline:
            return token
        time.sleep(0.2)


def _scan_reset_token(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()
    except OSError:
        return None
    for line in reversed(lines):
        if _MAIL_EVENT not in line:
            continue
        match = _TOKEN_IN_LOG.search(line)
        if match is not None:
            return match.group(1)
    return None


def _json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {}


def run(args: argparse.Namespace) -> int:
    base = args.base_url.rstrip("/") + _API
    email = args.email or f"demo-{uuid.uuid4().hex[:8]}@example.com"
    old_password = args.password
    new_password = args.new_password

    print(f"目标：{base}")
    print(f"账号：{email}")
    print("-" * 72)

    with httpx.Client(timeout=args.timeout, follow_redirects=False) as client:
        demo = Demo(client)

        registered = demo.step(
            "POST /auth/register",
            201,
            client.post(f"{base}/auth/register", json={"email": email, "password": old_password}),
        )
        user_id = _json(registered).get("id")
        demo.info(f"user_id={user_id}")

        logged_in = demo.step(
            "POST /auth/login",
            200,
            client.post(f"{base}/auth/login", json={"email": email, "password": old_password}),
        )
        pair = _json(logged_in)
        access = str(pair.get("access_token", ""))
        refresh = str(pair.get("refresh_token", ""))
        demo.info(f"expires_in={pair.get('expires_in')} refresh 长度={len(refresh)}")
        headers = {"Authorization": f"Bearer {access}"}

        profile = demo.step("GET /me", 200, client.get(f"{base}/me", headers=headers))
        demo.info(f"role={_json(profile).get('role')} status={_json(profile).get('status')}")

        updated = demo.step(
            "PATCH /me",
            200,
            client.patch(
                f"{base}/me",
                headers=headers,
                json={"settings": {"risk_profile": "aggressive", "language": "zh-CN"}},
            ),
        )
        demo.info(f"settings={_json(updated).get('settings')}")

        usage = demo.step("GET /me/usage", 200, client.get(f"{base}/me/usage", headers=headers))
        body = _json(usage)
        demo.info(
            f"calls={body.get('calls')} quota={body.get('quota')} cost_usd={body.get('cost_usd')}"
        )

        rotated = demo.step(
            "POST /auth/refresh",
            200,
            client.post(f"{base}/auth/refresh", json={"refresh_token": refresh}),
        )
        rotated_pair = _json(rotated)
        new_access = str(rotated_pair.get("access_token", ""))
        new_refresh = str(rotated_pair.get("refresh_token", ""))

        demo.step(
            "POST /auth/refresh（旧的，应失效）",
            401,
            client.post(f"{base}/auth/refresh", json={"refresh_token": refresh}),
        )

        demo.step(
            "POST /auth/logout",
            204,
            client.post(
                f"{base}/auth/logout",
                headers={"Authorization": f"Bearer {new_access}"},
                json={"refresh_token": new_refresh},
            ),
        )
        demo.step(
            "POST /auth/refresh（登出后）",
            401,
            client.post(f"{base}/auth/refresh", json={"refresh_token": new_refresh}),
        )

        requested = demo.step(
            "POST /auth/password/reset-request",
            202,
            client.post(f"{base}/auth/password/reset-request", json={"email": email}),
        )
        demo.info(f"响应体={_json(requested)}")
        demo.step(
            "POST /auth/password/reset-request（不存在）",
            202,
            client.post(f"{base}/auth/password/reset-request", json={"email": "ghost@example.com"}),
        )

        if args.skip_reset:
            demo.skip("POST /auth/password/reset-confirm", "--skip-reset")
            demo.skip("POST /auth/login（新口令）", "--skip-reset")
            return demo.summary()

        token = _read_reset_token(args.reset_log, timeout=args.reset_wait)
        if token is None:
            demo.skip(
                "POST /auth/password/reset-confirm", f"{args.reset_log} 里没有 mail.send 令牌"
            )
            demo.skip("POST /auth/login（新口令）", "缺少重置令牌")
            demo.info("提示：重置令牌由 LoggingMailSender 写入服务端日志，可用")
            demo.info("      `docker compose logs api | grep mail.send` 查看后重跑。")
            return demo.summary()

        demo.info(f"从日志取得重置令牌（前 6 位）：{token[:6]}…")
        demo.step(
            "POST /auth/password/reset-confirm",
            204,
            client.post(
                f"{base}/auth/password/reset-confirm",
                json={"token": token, "new_password": new_password},
            ),
        )
        demo.step(
            "POST /auth/password/reset-confirm（重放）",
            401,
            client.post(
                f"{base}/auth/password/reset-confirm",
                json={"token": token, "new_password": new_password},
            ),
        )
        demo.step(
            "POST /auth/login（旧口令，应失败）",
            401,
            client.post(f"{base}/auth/login", json={"email": email, "password": old_password}),
        )
        demo.step(
            "POST /auth/login（新口令）",
            200,
            client.post(f"{base}/auth/login", json={"email": email, "password": new_password}),
        )
        return demo.summary()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M1 身份模块演示（注册→登录→刷新→登出→改密）")
    parser.add_argument(
        "--base-url", default="http://127.0.0.1:8000", help="服务地址（不含 /api/v1）"
    )
    parser.add_argument("--email", default="", help="账号邮箱；缺省随机生成，避免重复注册")
    parser.add_argument(
        "--password", default="Str0ngPassw0rd!", help="初始口令（≥12 位含大小写与数字）"
    )
    parser.add_argument("--new-password", default="N3wStr0ngPassw0rd!", help="重置后的新口令")
    parser.add_argument(
        "--reset-log",
        default="api.log",
        help="服务端日志文件，用于取重置令牌（APP_ENV=local 时由 LoggingMailSender 写入）",
    )
    parser.add_argument("--skip-reset", action="store_true", help="跳过密码重置两步")
    parser.add_argument("--timeout", type=float, default=10.0, help="单请求超时秒数")
    parser.add_argument(
        "--reset-wait",
        type=float,
        default=5.0,
        help="等待日志出现重置令牌的秒数（日志跟随写入时有竞态）",
    )
    args = parser.parse_args(argv)
    try:
        return run(args)
    except httpx.HTTPError as exc:
        print(f"网络错误：{exc}")
        print("检查服务是否已启动，以及 --base-url 是否正确。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
