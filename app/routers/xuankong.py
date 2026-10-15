# -*- coding: utf-8 -*-
"""玄空飞星 · 进阶路由：月盘 + 宅运盘。

    GET  /api/v1/xuankong/month   玄空月盘（?date=YYYY-MM-DD，缺省今天）
    POST /api/v1/xuankong/house   宅运盘（下卦起星）

与 `/diagnose` `/bazhai` `/almanac` 一致，本组接口是**纯计算**：不落库、不要求登录。
月盘只由日期决定，宅运盘只由坐向与元运决定，两者都是确定性规则。
「记住这套房」交给房屋档案（`/api/v1/houses`）。

月盘的日期同时接受 `?date=YYYY-MM-DD`（与 `/almanac/day` 同口径，客户端用它）
与 `?year=&month=&day=` 三元组（`/daily` 一族的老口径，缺省项按今天补齐）。

宅运盘的坐向与元运各二者取一：
* 坐向：`degree`（罗盘读数，推荐，会返回兼向提示）或 `trigram`（只知卦时取天元龙）
* 元运：`yun`（直接指定运数）或 `build_year`（按建宅年份推算）
两边都缺其一即返回 400——没有坐向或没有元运，排不出盘，这里不做默认值兜底，
否则用户会拿到一份凭空捏造的格局。
"""

import datetime as dt

from fastapi import APIRouter, HTTPException, Query

from ..engine import house_chart, month_chart, parse_date, resolve_date
from ..schemas import XuankongHouse, XuankongHouseRequest, XuankongMonth

router = APIRouter(prefix="/api/v1", tags=["xuankong"])


def ok(data):
    return {"code": 0, "status": "ok", "data": data}


def _guard(fn, *args, **kwargs):
    """把引擎的确定性异常翻译成 HTTP 语义。

    ValueError 是入参问题（400）；RuntimeError 是缺历法库之类的基础设施问题（503），
    不该算在用户头上。
    """
    try:
        return fn(*args, **kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/xuankong/month")
def xuankong_month(
    date: str = Query("", description="YYYY-MM-DD，缺省为今天；优先于 year/month/day"),
    year: int = 0,
    month: int = 0,
    day: int = 0,
):
    """玄空月盘：该日期所属节气月的九宫飞星，并与同宫流年星叠看。

    日期两种给法都可：``?date=YYYY-MM-DD``（推荐，与 `/almanac/day` 同口径）
    或 ``?year=&month=&day=`` 三元组（缺省项按今天补齐），``date`` 优先。
    注意「月」是**节气月**（立春起正月），与公历月不同步，
    响应里的 ``jieqi`` 会给出本月的界节。
    """
    target = _guard(parse_date, date)
    if target is None:
        today = dt.date.today()
        target = _guard(resolve_date, year or today.year, month, day)
    chart = _guard(month_chart, target)
    return ok(XuankongMonth(**chart))


@router.post("/xuankong/house")
def xuankong_house(payload: XuankongHouseRequest):
    """宅运盘：运星 / 山星 / 向星三盘叠加，判格局与逐宫吉凶。"""
    chart = _guard(
        house_chart,
        degree=payload.degree,
        declination=payload.declination,
        trigram=payload.trigram.strip(),
        yun=payload.yun,
        build_year=payload.build_year,
        name=payload.name,
    )
    return ok(XuankongHouse(**chart))
