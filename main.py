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

from app.db import Base, engine, ping
from app.models import Admin, BaziProfile, House, SmsCode, User  # noqa: F401  导入即注册表
from app.routers import (
    admin_router,
    auth_router,
    bazi_profile_router,
    bazi_router,
    diagnose_router,
    house_router,
    library_router,
    ziwei_router,
)

# 建表后需要存在的业务表，启动时打印便于确认
_EXPECTED_TABLES = ("admins", "users", "sms_codes", "houses", "bazi_profiles")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动自检数据库连通性并自动建表。

    建表失败不阻断启动——计算类接口（诊断 / 排盘）本就不依赖数据库，
    只有用户体系与房屋档案落库会受影响，届时接口会返回明确错误。
    """
    db_ok, db_info = ping()
    print(f"[startup] database: {'connected' if db_ok else 'UNAVAILABLE'} -> {db_info}")
    if db_ok:
        try:
            Base.metadata.create_all(bind=engine)
            print(f"[startup] tables ready: {', '.join(_EXPECTED_TABLES)}")
        except SQLAlchemyError as exc:
            print(f"[startup] create tables failed: {exc}")
    yield


app = FastAPI(
    title="风水装修 App API",
    version="0.3.0",
    description=(
        "定坐向 -> 出报告；生辰 -> 排八字。"
        "数值由确定性规则引擎计算，不经过大模型。"
        "用户体系：手机号 + 短信验证码；管理后台独立 token。"
    ),
    lifespan=lifespan,
)

# 开发阶段允许 Flutter 调试端与本地管理后台直连。
# 上线前务必收敛为具体域名，否则等于对所有站点开放。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
app.include_router(library_router)
app.include_router(house_router)
app.include_router(auth_router)
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
