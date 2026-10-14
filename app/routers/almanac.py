# -*- coding: utf-8 -*-
"""黄历路由：通书日课与择日。

    GET  /api/v1/almanac/today      今日通书
    GET  /api/v1/almanac/day        指定日通书（?date=YYYY-MM-DD，缺省今天）
    GET  /api/v1/almanac/activities 可择日事项清单
    GET  /api/v1/almanac/month      整月每日吉凶（?year=&month=&activity=&zodiac=）
    POST /api/v1/almanac/select     择日：事项 + 区间 -> 按分排序的吉日

与 `/api/v1/bazi`、`/api/v1/bazhai` 同口径：纯计算、无状态、不落库、不要求登录。
历法数据来自 lunar-python；该库缺失时返回 503——黄历不能靠近似值兜底，
给不出真实通书就如实报错，好过给一份编出来的宜忌。
"""

from fastapi import APIRouter, HTTPException, Query

from ..engine import (
    day_almanac,
    list_activities,
    month_overview,
    resolve_day,
    select_dates,
)
from ..schemas import (
    AlmanacCalendar,
    AlmanacDay,
    AlmanacSelectRequest,
    AlmanacSelectResponse,
)

router = APIRouter(prefix="/api/v1", tags=["almanac"])


def ok(data):
    return {"code": 0, "status": "ok", "data": data}


def _guard(fn):
    """统一把引擎异常翻译成 HTTP 语义。

    ValueError -> 400（用户入参/事项不存在）；RuntimeError -> 503（历法库缺失）。
    """
    try:
        return fn()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/almanac/today")
def almanac_today():
    """今日通书。与 ``/almanac/day`` 无参调用等价，单独提供便于客户端直接使用。"""
    chart = _guard(lambda: day_almanac(resolve_day(None)))
    return ok(AlmanacDay(**chart))


@router.get("/almanac/day")
def almanac_day(
    date: str = Query("", description="YYYY-MM-DD，缺省为今天"),
):
    """指定日期的通书。"""
    chart = _guard(lambda: day_almanac(resolve_day(date)))
    return ok(AlmanacDay(**chart))


@router.get("/almanac/activities")
def almanac_activities():
    """可择日的事项清单（前端渲染筛选用）。"""
    return ok({"activities": list_activities()})


@router.get("/almanac/month")
def almanac_month(
    year: int = Query(..., ge=1900, le=2100, description="公历年"),
    month: int = Query(..., ge=1, le=12, description="公历月"),
    activity: str = Query("", description="事项 key；留空则返回当日总体吉凶"),
    zodiac: str = Query("", description="用户生肖，用于标注冲日"),
):
    """整月每日吉凶评分，供月历热力展示。"""
    overview = _guard(lambda: month_overview(year, month, activity.strip(), zodiac.strip()))
    return ok(AlmanacCalendar(**overview))


@router.post("/almanac/select")
def almanac_select(payload: AlmanacSelectRequest):
    """择日：在给定区间内为该事项挑吉日，按分数降序返回。"""
    result = _guard(
        lambda: select_dates(
            activity_key=payload.activity,
            start=resolve_day(payload.start_date),
            days=payload.days,
            zodiac=(payload.zodiac or "").strip(),
            limit=payload.limit,
            min_score=payload.min_score,
        )
    )
    return ok(AlmanacSelectResponse(**result))
