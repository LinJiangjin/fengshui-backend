# -*- coding: utf-8 -*-
"""风水装修 App · 后端服务（FastAPI）

启动：
    pip install -r requirements.txt
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import bazi_router, diagnose_router

app = FastAPI(
    title="风水装修 App API",
    version="0.2.0",
    description="定坐向 -> 出报告；生辰 -> 排八字。数值由确定性规则引擎计算，不经过大模型。",
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


@app.get("/health")
def health():
    return {"code": 0, "status": "ok", "data": {"service": "fengshui-api"}}
