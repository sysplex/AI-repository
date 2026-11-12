"""T09 负向验证临时文件：故意违反分层契约（core 不得依赖 api）。"""

from app.api import health as _health  # noqa: F401
