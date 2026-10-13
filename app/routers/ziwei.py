# -*- coding: utf-8 -*-
"""紫微斗数排盘 + 解读路由。

    POST /api/v1/ziwei    出生信息 -> 紫微命盘 + 感情 / 职业 / 运势解读

与 `/api/v1/bazi` 一样是**无状态计算**：不落库、不需要登录，
App 端在命理档案页拿到排盘结果后，用同一份出生信息追加请求本接口。
"""

from fastapi import APIRouter, HTTPException

from ..engine import build_ziwei, build_ziwei_reading, build_ziwei_years
from ..schemas import ZiweiRequest, ZiweiResponse

router = APIRouter(prefix="/api/v1", tags=["ziwei"])


def ok(data):
    return {"code": 0, "status": "ok", "data": data}


@router.post("/ziwei")
def ziwei(payload: ZiweiRequest):
    """排紫微命盘，并给出感情 / 职业 / 运势三块确定性解读。"""
    try:
        chart = build_ziwei(
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

    chart["reading"] = build_ziwei_reading(chart)
    # 逐年流年：默认自今年起 10 年
    chart["years"] = build_ziwei_years(chart, birth_year=payload.year)
    return ok(ZiweiResponse(**chart).model_dump())
