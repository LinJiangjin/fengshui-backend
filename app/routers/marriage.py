# -*- coding: utf-8 -*-
"""合婚配对路由。

    POST /api/v1/marriage   生肖合婚 / 八字合婚

与 `/bazi` `/divination` 一致，本接口是**纯计算**：不落库、不要求登录。
"""

from fastapi import APIRouter, HTTPException

from ..engine import build_match
from ..schemas import MarriageRequest, MarriageResponse

router = APIRouter(prefix="/api/v1", tags=["marriage"])


def ok(data):
    return {"code": 0, "status": "ok", "data": data}


@router.post("/marriage")
def marriage(payload: MarriageRequest):
    def party(p):
        return {
            "year": p.year, "month": p.month, "day": p.day,
            "hour": p.hour, "minute": p.minute,
            "gender": p.gender, "longitude": p.longitude, "name": p.name,
        }

    try:
        chart = build_match(
            mode=payload.mode,
            a_year=payload.a.year,
            b_year=payload.b.year,
            a=party(payload.a),
            b=party(payload.b),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        # 缺 lunar-python
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return ok(MarriageResponse(**chart))
