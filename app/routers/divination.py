# -*- coding: utf-8 -*-
"""占卜路由：六爻纳甲 / 梅花易数。

    POST /api/v1/divination   问卦

与 `/diagnose` `/bazi` `/almanac` 一致，本接口是**纯计算**：不落库、不要求登录。
服务端不产生随机数——起卦（铜钱、取数）由客户端完成，这里只做确定性的
装卦与解读，因此同一份入参永远得到同一份卦例。
"""

import datetime as dt

from fastapi import APIRouter, HTTPException

from ..engine import build_divination
from ..schemas import DivinationRequest, DivinationResponse

router = APIRouter(prefix="/api/v1", tags=["divination"])


def ok(data):
    return {"code": 0, "status": "ok", "data": data}


@router.post("/divination")
def divination(payload: DivinationRequest):
    when: dt.datetime | None = None
    if payload.when:
        try:
            # 用 strptime 而不是 fromisoformat：后者会放行 20261017 这类紧凑格式
            when = dt.datetime.strptime(payload.when, "%Y-%m-%d %H:%M")
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail="when 需形如 2026-10-17 09:30"
            ) from exc

    try:
        chart = build_divination(
            mode=payload.mode,
            lines=payload.lines,
            when=when,
            numbers=payload.numbers,
            topic=payload.topic,
            gender=payload.gender,
            question=payload.question,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        # 缺 lunar-python
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return ok(DivinationResponse(**chart))
