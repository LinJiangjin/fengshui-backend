# -*- coding: utf-8 -*-
"""风水装修 App · 后端服务（FastAPI）

启动：
    pip install -r requirements.txt
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app.db import Base, engine, ping
from app.models import House  # noqa: F401  导入即注册表，供建表使用
from app.routers import bazi_router, diagnose_router, house_router, library_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动自检数据库连通性并自动建表。

    建表失败不阻断启动——计算类接口（诊断 / 排盘）本就不依赖数据库，
    只有房屋档案落库会受影响，届时接口会返回明确错误。
    """
    db_ok, db_info = ping()
    print(f"[startup] database: {'connected' if db_ok else 'UNAVAILABLE'} -> {db_info}")
    if db_ok:
        try:
            Base.metadata.create_all(bind=engine)
            print("[startup] tables ready: houses")
        except SQLAlchemyError as exc:
            print(f"[startup] create tables failed: {exc}")
    yield


app = FastAPI(
    title="风水装修 App API",
    version="0.2.0",
    description="定坐向 -> 出报告；生辰 -> 排八字。数值由确定性规则引擎计算，不经过大模型。",
    lifespan=lifespan,
)

# 开发阶段允许 Flutter 调试端直连
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(diagnose_router)
app.include_router(bazi_router)
app.include_router(library_router)
app.include_router(house_router)


@app.get("/health")
def health():
    db_ok, db_info = ping()
    return {
        "code": 0,
        # 计算类接口不依赖数据库，库挂了服务仍可用，因此只降级标记、不影响探活
        "status": "ok" if db_ok else "degraded",
        "data": {
            "service": "fengshui-api",
            "database": {"connected": db_ok, "info": db_info},
        },
    }
