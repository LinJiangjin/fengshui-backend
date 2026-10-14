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


# ------------------------------------------------------------------ 鉴权
# 生产环境必须在 .env 里覆盖 JWT_SECRET，否则任何人拿到源码即可伪造 token。
JWT_SECRET = _env("JWT_SECRET", "dev-only-secret-change-me-in-production")
JWT_ALGORITHM = _env("JWT_ALGORITHM", "HS256")
# 后台 token 有效期长一些，避免运营频繁掉线
JWT_EXPIRE_MINUTES = int(_env("JWT_EXPIRE_MINUTES", str(60 * 24 * 7)))

# 业务时区偏移（小时）。时间统一按 UTC 存储，但「今日新增」这类统计
# 要按运营所在时区切分，默认东八区。
APP_TIMEZONE_OFFSET_HOURS = float(_env("APP_TIMEZONE_OFFSET_HOURS", "8"))


# ------------------------------------------------------------------ 运行环境 / CORS
# dev  = 本地开发：放行本机任意端口的跨域请求。Flutter Web 的调试端口是
#        随机分配的，逐个列举不现实，因此用正则兜住 localhost。
# prod = 线上：只认 CORS_ALLOW_ORIGINS 里显式写出的域名，没配就拒绝一切跨域。
#
# 注意：App 原生端（Android / iOS）走的是原生 HTTP 栈，不受 CORS 约束；
# 这里的配置只影响 Flutter Web 端与管理后台。
APP_ENV = _env("APP_ENV", "dev")

# 逗号分隔的完整 Origin，例如：
#     CORS_ALLOW_ORIGINS=https://app.example.com,https://admin.example.com
CORS_ALLOW_ORIGINS = [
    item.strip() for item in _env("CORS_ALLOW_ORIGINS", "").split(",") if item.strip()
]

# 允许的 Origin 正则：默认仅在 dev 下放行本机任意端口；prod 下默认关闭，
# 如确需放宽可在 .env 里显式指定。置为空字符串即彻底关闭。
CORS_ALLOW_ORIGIN_REGEX = _env(
    "CORS_ALLOW_ORIGIN_REGEX",
    "" if APP_ENV == "prod" else r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
)


# ------------------------------------------------------------------ 短信
# provider: console = 验证码只写日志不发短信（开发用）；aliyun = 阿里云短信
SMS_PROVIDER = _env("SMS_PROVIDER", "console")
# console 模式下的固定验证码，方便本地联调不用翻日志
SMS_DEV_CODE = _env("SMS_DEV_CODE", "888888")
SMS_CODE_TTL_SECONDS = int(_env("SMS_CODE_TTL_SECONDS", "300"))
# 同一手机号发送间隔（秒），防刷
SMS_SEND_INTERVAL_SECONDS = int(_env("SMS_SEND_INTERVAL_SECONDS", "60"))
# 单个验证码最多校验失败次数，超过后作废
SMS_MAX_VERIFY_ATTEMPTS = int(_env("SMS_MAX_VERIFY_ATTEMPTS", "5"))

# 阿里云短信所需配置（provider=aliyun 时才读）
ALIYUN_SMS_ACCESS_KEY_ID = _env("ALIYUN_SMS_ACCESS_KEY_ID", "")
ALIYUN_SMS_ACCESS_KEY_SECRET = _env("ALIYUN_SMS_ACCESS_KEY_SECRET", "")
ALIYUN_SMS_SIGN_NAME = _env("ALIYUN_SMS_SIGN_NAME", "")
ALIYUN_SMS_TEMPLATE_CODE = _env("ALIYUN_SMS_TEMPLATE_CODE", "")
