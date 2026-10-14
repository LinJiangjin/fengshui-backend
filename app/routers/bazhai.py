# -*- coding: utf-8 -*-
"""八宅路由：出生年 + 性别 + 坐向 -> 命卦 / 宅卦 / 游年八星 / 房间选位。

    POST /api/v1/bazhai    排八宅盘（无状态计算）

与 `/api/v1/bazi`、`/api/v1/ziwei` 一致，本接口是纯计算：不落库、不要求登录——
命卦只由出生年与性别决定，宅卦只由坐向决定，两者都是确定性规则。
「记住用户信息」交给命理档案（/api/v1/bazi/profile）与房屋档案（/api/v1/houses）。

宅卦二者取一：传 `degree`（罗盘读数，推荐）或直接传 `trigram`（坐山卦）。
两者都缺时返回 400——没有坐向就定不出宅卦，这里不做「默认坐北朝南」的兜底，
否则用户会拿到一份凭空捏造的吉凶表。
"""

from fastapi import APIRouter, HTTPException

from ..engine import build_bazhai
from ..schemas import BazhaiRequest, BazhaiResponse

router = APIRouter(prefix="/api/v1", tags=["bazhai"])


def ok(data):
    return {"code": 0, "status": "ok", "data": data}


@router.post("/bazhai")
def bazhai(payload: BazhaiRequest):
    try:
        chart = build_bazhai(
            year=payload.year,
            gender=payload.gender,
            month=payload.month,
            day=payload.day,
            hour=payload.hour,
            minute=payload.minute,
            degree=payload.degree,
            declination=payload.declination,
            trigram=payload.trigram.strip(),
            name=payload.name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # 用 pydantic 模型做一次出参校验，保证与 BazhaiResponse 契约一致
    return ok(BazhaiResponse(**chart))
