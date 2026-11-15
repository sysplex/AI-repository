"""导出 FastAPI 生产级 OpenAPI 规范 JSON。

供前端代码生成器（OpenAPI TypeScript CodeGen）消费，确保前后端接口契约 100% 同步无漂移。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# 设置最小化虚拟环境变量以允许构建应用
os.environ.setdefault("APP_ENV", "ci")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres@db.test:5432/app")
os.environ.setdefault("REDIS_URL", "redis://cache.test:6379/0")
os.environ.setdefault("SECRET_KEY", "t" * 40)

# 将 backend 目录加入 sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.main import create_app  # noqa: E402


def export_openapi(output_path: Path | None = None) -> Path:
    if output_path is None:
        output_path = REPO_ROOT / "frontend" / "openapi.json"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    app = create_app()
    spec = app.openapi()

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)

    print(f"OpenAPI spec successfully exported to {output_path}")
    print(f"  - Title: {spec.get('info', {}).get('title')}")
    print(f"  - Version: {spec.get('info', {}).get('version')}")
    print(f"  - Paths: {len(spec.get('paths', {}))}")
    print(f"  - Schemas: {len(spec.get('components', {}).get('schemas', {}))}")
    return output_path


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    export_openapi(target)
