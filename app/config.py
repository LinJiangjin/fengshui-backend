# -*- coding: utf-8 -*-
"""应用配置：环境变量优先，其次读取项目根目录 .env（不覆盖已有环境变量）。"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # server/


def _load_dotenv(path: Path) -> None:
    """极简 .env 解析：支持 KEY=VALUE、# 注释、引号包裹；已存在的环境变量优先。"""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_dotenv(BASE_DIR / ".env")


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


POSTGRES_HOST = _env("POSTGRES_HOST", "127.0.0.1")
POSTGRES_PORT = int(_env("POSTGRES_PORT", "5432"))
POSTGRES_DB = _env("POSTGRES_DB", "fengshui")
POSTGRES_USER = _env("POSTGRES_USER", "fengshui_app")
POSTGRES_PASSWORD = _env("POSTGRES_PASSWORD", "Fengshui_app_2026")

POSTGRES_URL = "postgresql+psycopg://{user}:{password}@{host}:{port}/{db}".format(
    user=POSTGRES_USER,
    password=POSTGRES_PASSWORD,
    host=POSTGRES_HOST,
    port=POSTGRES_PORT,
    db=POSTGRES_DB,
)

# 未显式配置 DATABASE_URL 时用 SQLite 文件库（server/fengshui.db）：
# 零外部依赖，本地开发与单机部署开箱即用，房屋档案照样落库。
# 换 PostgreSQL 只需在 .env 里写一行，例如：
#     DATABASE_URL=postgresql+psycopg://fengshui_app:pwd@127.0.0.1:5432/fengshui
DATABASE_URL = _env("DATABASE_URL", "") or "sqlite:///" + str(
    BASE_DIR / "fengshui.db"
).replace("\\", "/")
