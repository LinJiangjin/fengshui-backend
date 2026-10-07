# -*- coding: utf-8 -*-
"""诊断路由：定坐向 -> 出报告（MVP 主链路）。"""

import datetime as dt

from fastapi import APIRouter

from ..engine.constants import RULES_VERSION
from ..schemas import DiagnoseRequest
from ..engine import (
    orient,
    build_palaces,
    pick_extremes,
    score_of,
    build_metrics,
    build_advice,
    build_daily_advice,
    build_furniture_tips,
    build_layout_guide,
    daily_chart,
    enhance,
    resolve_date,
)

router = APIRouter(prefix="/api/v1", tags=["diagnose"])


def ok(data):
    return {"code": 0, "status": "ok", "data": data}


@router.post("/diagnose")
def diagnose(payload: DiagnoseRequest):
    # L1 确定性计算
    orientation = orient(payload.degree, payload.declination)
    palaces = build_palaces(payload.year)          # 流年盘（年内不变）
    extremes = pick_extremes(palaces)
    score = score_of(palaces)
    metrics = build_metrics(orientation, palaces)
    advice = build_advice(orientation, palaces, extremes)

    # 日家紫白：按测算当日推算，今日吉位 / 今日忌方随日期变化
    chart_date = resolve_date(payload.year, payload.month, payload.day)
    daily = daily_chart(chart_date)
    advice = build_daily_advice(daily) + advice

    # 家具摆放建议：按当日吉凶 + 流年星曜生成，供布局页展示
    tips = build_furniture_tips(orientation, palaces, daily["best"], daily["worst"])

    # 功能区布局建议表：按户型生成，前端不再自行推算
    layout_guide = build_layout_guide(
        payload.layout, orientation, palaces, daily["best"], daily["worst"]
    )

    # L2 大模型增强（未配置时原样返回）
    context = {
        "orientation": orientation,
        "palaces": palaces,
        "extremes": extremes,
        "daily": daily,
    }
    advice = enhance(advice, context)

    return ok({
        "score": score,
        "orientation": orientation,
        "palaces": palaces,
        "extremes": extremes,
        "metrics": metrics,
        "advice": advice,
        "tips": tips,
        "layout_guide": layout_guide,
        "rules_version": RULES_VERSION,
        "year": payload.year,
        "house_name": payload.house_name,
        "area": payload.area,
        "daily": daily,
    })


@router.get("/daily")
def daily(month: int = 0, day: int = 0, year: int = 0):
    """当日紫白盘：今日吉位 / 今日忌方（不依赖坐向，便于单独调试）。"""
    today = dt.date.today()
    return ok(daily_chart(resolve_date(year or today.year, month, day)))


@router.get("/mountains")
def mountains():
    """二十四山列表，供手动输入坐向时使用。"""
    from ..engine.constants import MOUNTAINS
    return ok({"total": len(MOUNTAINS), "items": MOUNTAINS})
