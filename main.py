# -*- coding: utf-8 -*-
"""风水装修 App · 后端服务（FastAPI）

启动：
    pip install -r requirements.txt
    uvicorn main:app --reload --host 0.0.0.0 --port 8000

首次部署先创建管理员账号：
    python scripts/init_admin.py --username admin --password 你的密码
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import APP_ENV, CORS_ALLOW_ORIGIN_REGEX, CORS_ALLOW_ORIGINS
from app.db import Base, SessionLocal, engine, ping
from app.models import (  # noqa: F401  导入即注册表
    Admin,
    BaziProfile,
    CalcRecord,
    ElementNote,
    House,
    Scheme,
    SmsCode,
    User,
)
from app.routers import (
    admin_router,
    almanac_router,
    auth_router,
    bazi_profile_router,
    bazi_router,
    bazhai_router,
    diagnose_router,
    divination_router,
    marriage_router,
    phone_energy_router,
    house_router,
    legal_router,
    library_router,
    records_router,
    xuankong_router,
    ziwei_router,
)
from app.seed_library import seed_library

# 建表后需要存在的业务表，启动时打印便于确认
_EXPECTED_TABLES = (
    "admins",
    "users",
    "sms_codes",
    "houses",
    "bazi_profiles",
    "calc_records",
    "schemes",
    "element_notes",
)


def _cors_summary() -> str:
    """回显实际生效的跨域策略，避免上线后靠猜。"""
    parts = []
    if CORS_ALLOW_ORIGINS:
        parts.append("origins=" + ",".join(CORS_ALLOW_ORIGINS))
    if CORS_ALLOW_ORIGIN_REGEX:
        parts.append(f"regex={CORS_ALLOW_ORIGIN_REGEX}")
    return " | ".join(parts) if parts else "DISABLED（不允许任何跨域来源）"


def _maybe_seed_admin(db: Session) -> None:
    """仅在配置了 ADMIN_USERNAME/ADMIN_PASSWORD 且库内尚无管理员时创建一个初始账号。

    用途：托管部署的 SQLite 每次重建，靠环境变量保证管理后台始终有可用账号，
    从而能登录查看注册用户。本地开发若未配置这两个变量则完全跳过，不影响已有数据。
    """
    from app.security import hash_password
    from app.utils import new_id

    username = (os.getenv("ADMIN_USERNAME") or "").strip()
    password = (os.getenv("ADMIN_PASSWORD") or "").strip()
    if not username or not password:
        return
    if db.query(Admin).first() is not None:
        return
    db.add(
        Admin(
            id=new_id("adm"),
            username=username,
            password_hash=hash_password(password),
            display_name=(os.getenv("ADMIN_DISPLAY_NAME") or username).strip() or username,
            status="active",
        )
    )
    db.commit()
    print(f"[startup] 已用环境变量创建初始管理员：{username}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动自检数据库连通性并自动建表。

    建表失败不阻断启动——计算类接口（诊断 / 排盘）本就不依赖数据库，
    只有用户体系与房屋档案落库会受影响，届时接口会返回明确错误。
    """
    print(f"[startup] env={APP_ENV} cors: {_cors_summary()}")
    if APP_ENV == "prod" and not CORS_ALLOW_ORIGINS:
        print(
            "[startup] WARNING: APP_ENV=prod 但未配置 CORS_ALLOW_ORIGINS，"
            "所有跨域请求都会被拒绝（App 原生端不走 CORS，不受影响）"
        )
    db_ok, db_info = ping()
    print(f"[startup] database: {'connected' if db_ok else 'UNAVAILABLE'} -> {db_info}")
    if db_ok:
        try:
            Base.metadata.create_all(bind=engine)
            print(f"[startup] tables ready: {', '.join(_EXPECTED_TABLES)}")
        except SQLAlchemyError as exc:
            print(f"[startup] create tables failed: {exc}")
        else:
            # 方案库初始内容：只在表为空时写入，不会覆盖运营改过的数据
            session = SessionLocal()
            try:
                seeded_schemes, seeded_notes = seed_library(session)
                if seeded_schemes or seeded_notes:
                    print(
                        "[startup] 方案库初始化完成："
                        f"{seeded_schemes} 个方案 / {seeded_notes} 条五行解读"
                    )
                _maybe_seed_admin(session)
            except Exception as exc:  # noqa: BLE001  初始化失败不该拦住服务启动
                print(f"[startup] seed library failed: {exc}")
            finally:
                session.close()
    yield


app = FastAPI(
    title="风水装修 App API",
    version="0.3.0",
    description=(
        "定坐向 -> 出报告；生辰 -> 排八字 / 紫微 / 八宅；查日课 -> 黄历择日。"
        "数值由确定性规则引擎计算，不经过大模型。"
        "用户体系：手机号 + 短信验证码；管理后台独立 token。"
    ),
    lifespan=lifespan,
)

# 跨域来源按环境收敛，不再无脑放行 "*"（那等于对所有站点开放）。
# 白名单见 .env 的 CORS_ALLOW_ORIGINS；dev 环境额外放行本机任意端口，
# 因为 Flutter Web 的调试端口是随机分配的。
# 注意：App 原生端（Android / iOS）不走 CORS，此处配置只影响 Web 端与后台。
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_origin_regex=CORS_ALLOW_ORIGIN_REGEX or None,
    allow_methods=["*"],
    allow_headers=["*"],
)


_WEB_DIR = Path(__file__).resolve().parent / "web"
_WEB_INDEX = _WEB_DIR / "index.html"

# 这些前缀的 404 保持 JSON 错误，不做 SPA 回退（API 打错路径要返回明确错误而非首页）
_SPA_EXEMPT_PREFIXES = ("/api/", "/api", "/admin", "/health", "/_diag")


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """把 HTTPException 包装成统一响应格式。

    同时保留 `detail` 字段，兼容已有的 Flutter 客户端解析逻辑。
    另外承担 SPA 深链接回退：/login 等前端路由在静态目录里没有对应文件，
    StaticFiles 抛 404，这里拦截后返回 index.html，交给前端路由接管
    （API / 后台路径除外，它们的 404 必须保持原样）。
    """
    if (
        exc.status_code == 404
        and request.method in ("GET", "HEAD")
        and not request.url.path.startswith(_SPA_EXEMPT_PREFIXES)
        and _WEB_INDEX.is_file()
    ):
        return FileResponse(_WEB_INDEX, media_type="text/html")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.status_code,
            "status": "error",
            "message": str(exc.detail),
            "detail": exc.detail,
            "data": None,
        },
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """参数校验失败也走统一格式，避免前端拿到两种错误结构。"""
    errors = exc.errors()
    first = errors[0] if errors else {}
    loc = ".".join(str(part) for part in first.get("loc", []) if part != "body")
    message = first.get("msg", "参数校验失败")
    # 新版 starlette 把 HTTP_422_UNPROCESSABLE_ENTITY 改名了，这里兼容两种
    unprocessable = getattr(
        status, "HTTP_422_UNPROCESSABLE_CONTENT", status.HTTP_422_UNPROCESSABLE_ENTITY
    )
    return JSONResponse(
        status_code=unprocessable,
        content={
            "code": 422,
            "status": "error",
            "message": f"{loc}: {message}" if loc else message,
            "detail": errors,
            "data": None,
        },
    )


app.include_router(diagnose_router)
app.include_router(bazi_router)
app.include_router(bazi_profile_router)
app.include_router(ziwei_router)
app.include_router(bazhai_router)
app.include_router(almanac_router)
app.include_router(xuankong_router)
app.include_router(divination_router)
app.include_router(marriage_router)
app.include_router(phone_energy_router)
app.include_router(library_router)
app.include_router(house_router)
app.include_router(auth_router)
app.include_router(legal_router)
app.include_router(admin_router)
app.include_router(records_router)


@app.get("/health")
def health():
    db_ok, db_info = ping()
    return {
        "code": 0,
        # 计算类接口不依赖数据库，库挂了服务仍可用，因此只降级标记、不影响探活
        "status": "ok" if db_ok else "degraded",
        "data": {
            "service": "fengshui-api",
            "version": app.version,
            "database": {"connected": db_ok, "info": db_info},
        },
    }


@app.get("/_diag")
def diag(request: Request):
    """临时诊断：核对服务端实际收到的 token 与生效的密钥。

    用于排查「刚登录就被判过期」——若 auth_prefix 与客户端发出的 token 不一致，
    说明反向代理改写了 Authorization 头，改用 X-Auth-Token 通道即可绕过。
    排查完应删除本接口，避免对外暴露配置指纹。
    """
    import hashlib

    from app.security import JWT_SECRET

    return {
        "code": 0,
        "data": {
            "auth_prefix": request.headers.get("authorization", "")[:28],
            "xauth_len": len(request.headers.get("x-auth-token") or ""),
            "secret_sha12": hashlib.sha256(JWT_SECRET.encode()).hexdigest()[:12],
            "env_file_exists": (Path(__file__).resolve().parent / ".env").is_file(),
        },
    }


# ------------------------------------------------------------------ 静态托管（同域部署）
# 把 Flutter Web 构建产物放到 server/web/ 后，本服务单端口同时提供页面与 API：
# /api/v1/*、/health 等动态路由优先匹配，其余路径回退到 index.html（SPA 路由）。
# 目录不存在时（纯 API 部署）跳过挂载，行为与原来完全一致。
_ADMIN_WEB_DIR = Path(__file__).resolve().parent / "admin_web"

if _ADMIN_WEB_DIR.is_dir():
    from fastapi.staticfiles import StaticFiles

    # 管理后台挂在 /admin 子路径；必须在根挂载之前注册，否则会被 / 的 SPA 回退吞掉。
    app.mount("/admin", StaticFiles(directory=_ADMIN_WEB_DIR, html=True), name="admin_web")

if _WEB_DIR.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=_WEB_DIR, html=True), name="web")
