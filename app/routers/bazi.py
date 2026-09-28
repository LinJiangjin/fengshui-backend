# -*- coding: utf-8 -*-
"""八字排盘路由：出生时刻 -> 四柱 / 五行 / 用神喜忌。"""

from fastapi import APIRouter, HTTPException

from ..schemas import BaziRequest, BaziResponse
from ..engine import build_bazi, enhance_bazi

router = APIRouter(prefix="/api/v1", tags=["bazi"])


def ok(data):
    return {"code": 0, "status": "ok", "data": data}


@router.post("/bazi")
def bazi(payload: BaziRequest):
    try:
        profile = build_bazi(
            year=payload.year,
            month=payload.month,
            day=payload.day,
            hour=payload.hour,
            minute=payload.minute,
            gender=payload.gender,
            longitude=payload.longitude,
            name=payload.name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # L2 大模型文案增强钩子（未配置时原样返回）
    profile = enhance_bazi(profile, {"birth": profile["birth"]})

    # 用 pydantic 模型做一次出参校验，保证与 BaziResponse 契约一致
    return ok(BaziResponse(**profile))
