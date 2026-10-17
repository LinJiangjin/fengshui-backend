# -*- coding: utf-8 -*-
"""八字排盘路由：出生时刻 -> 四柱 / 五行 / 用神喜忌 / 大运 / 流年。"""

from fastapi import APIRouter, HTTPException

from ..schemas import BaziRequest, BaziResponse
from ..engine import build_bazi, build_bazi_fortune, enhance_bazi, true_solar_time

router = APIRouter(prefix="/api/v1", tags=["bazi"])


def ok(data):
    return {"code": 0, "status": "ok", "data": data}


@router.post("/bazi")
def bazi(payload: BaziRequest):
    try:
        # 真太阳时在这里单独算一次：排盘与大运起运必须用**同一个**时刻，
        # 否则交节前后出生的人会排出两套结果。它同时是排盘的内部输入，
        # 这里显式取出来只为传给大运，不是第二次计算口径。
        true_dt, _offset = true_solar_time(
            payload.year, payload.month, payload.day,
            payload.hour, payload.minute, payload.longitude,
        )
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
        profile.update(build_bazi_fortune(profile, true_dt, birth_year=payload.year))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        # 缺 lunar-python、或找不到交节时刻
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # L2 大模型文案增强钩子（未配置时原样返回）
    profile = enhance_bazi(profile, {"birth": profile["birth"]})

    # 用 pydantic 模型做一次出参校验，保证与 BaziResponse 契约一致
    return ok(BaziResponse(**profile))
