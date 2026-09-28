# -*- coding: utf-8 -*-
"""诊断路由：定坐向 -> 出报告（MVP 主链路）。"""

from fastapi import APIRouter

from ..schemas import DiagnoseRequest
from ..engine import (
    orient,
    build_palaces,
    pick_extremes,
    score_of,
    build_metrics,
    build_advice,
    enhance,
)

router = APIRouter(prefix="/api/v1", tags=["diagnose"])


def ok(data):
    return {"code": 0, "status": "ok", "data": data}


@router.post("/diagnose")
def diagnose(payload: DiagnoseRequest):
    # L1 确定性计算
    orientation = orient(payload.degree, payload.declination)
    palaces = build_palaces(payload.year)
    extremes = pick_extremes(palaces)
    score = score_of(palaces)
    metrics = build_metrics(orientation, palaces)
    advice = build_advice(orientation, palaces, extremes)

    # L2 大模型增强（未配置时原样返回）
    context = {"orientation": orientation, "palaces": palaces, "extremes": extremes}
    advice = enhance(advice, context)

    return ok({
        "score": score,
        "orientation": orientation,
        "palaces": palaces,
        "extremes": extremes,
        "metrics": metrics,
        "advice": advice,
        "year": payload.year,
        "house_name": payload.house_name,
        "area": payload.area,
    })


@router.get("/mountains")
def mountains():
    """二十四山列表，供手动输入坐向时使用。"""
    from ..engine.constants import MOUNTAINS
    return ok({"total": len(MOUNTAINS), "items": MOUNTAINS})
