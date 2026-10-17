# -*- coding: utf-8 -*-
"""风水装修 App · 后端服务（FastAPI）

启动：
    pip install -r requirements.txt
    uvicorn main:app --reload --host 0.0.0.0 --port 8000

首次部署先创建管理员账号：
    python scripts/init_admin.py --username admin --password 你的密码
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.config import APP_ENV, CORS_ALLOW_ORIGIN_REGEX, CORS_ALLOW_ORIGINS
from app.db import Base, SessionLocal, engine, ping
from app.models import (  # noqa: F401  导入即注册表
    Admin,
    BaziProfile,
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


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """把 HTTPException 包装成统一响应格式。

    同时保留 `detail` 字段，兼容已有的 Flutter 客户端解析逻辑。
    """
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
