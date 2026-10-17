# -*- coding: utf-8 -*-
"""号码八星（数字能量）路由。

    POST /api/v1/phone-energy   号码数组分析

与 `/bazi` `/divination` 一致，本接口是**纯计算**：不落库、不要求登录。

隐私：号码属个人信息。这里**不把原始号码写进日志与错误回显**——
报错时只报脱敏形式，响应里也只有 ``masked``。
"""

from fastapi import APIRouter, HTTPException

from ..engine import analyze_number, mask_number
from ..schemas import PhoneEnergyRequest, PhoneEnergyResponse

router = APIRouter(prefix="/api/v1", tags=["phone-energy"])


def ok(data):
    return {"code": 0, "status": "ok", "data": data}


@router.post("/phone-energy")
def phone_energy(payload: PhoneEnergyRequest):
    try:
        chart = analyze_number(payload.number, kind=payload.kind)
    except ValueError as exc:
        # 错误文案里只放脱敏号码，避免完整号码进日志
        masked = mask_number(payload.number, payload.kind)
        raise HTTPException(
            status_code=400, detail=f"{exc}（号码 {masked}）"
        ) from exc

    return ok(PhoneEnergyResponse(**chart))
