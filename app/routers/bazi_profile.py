# -*- coding: utf-8 -*-
"""命理档案路由：把用户录入的出生信息落库，一个用户一份。

    GET    /api/v1/bazi/profile    读取当前用户的命理档案（没有则 data 为 null）
    PUT    /api/v1/bazi/profile    保存 / 覆盖当前用户的命理档案
    DELETE /api/v1/bazi/profile    清空当前用户的命理档案

排盘本身仍是 `POST /api/v1/bazi` 的无状态计算；本组接口只负责「记住用户
上次录入的信息」，App 端进入命理档案页时据此回填表单并直接出盘。
重新录入视为修改同一份档案（不保留历史版本），避免列表里出现一堆重复记录。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..engine import build_bazi
from ..models import BaziProfile, User
from ..schemas import BaziProfileIn, BaziProfileOut
from ..utils import new_id

router = APIRouter(prefix="/api/v1", tags=["bazi-profile"])


def ok(data):
    return {"code": 0, "status": "ok", "data": data}


def _owned(db: Session, user: User):
    """当前用户的命理档案。

    正常只会有一条；按更新时间倒序取第一条，兜住可能存在的历史脏数据。
    """
    return (
        db.query(BaziProfile)
        .filter(BaziProfile.owner_id == user.id)
        .order_by(BaziProfile.updated_at.desc())
        .first()
    )


def _pillars_summary(payload: BaziProfileIn) -> str:
    """算一次四柱摘要（如「辛未 丁酉 癸未 丙辰」），仅作后台展示。

    摘要算不出来（非法日期等）不影响档案落库，留空即可——真太阳时与四柱
    始终由 App 端调用排盘接口实时计算，这里不把结果当权威数据。
    """
    try:
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
    except Exception:  # noqa: BLE001 - 附加信息，失败就留空
        return ""
    return " ".join(f"{p['gan']}{p['zhi']}" for p in profile.get("pillars", []))


def _out(row: BaziProfile) -> dict:
    return BaziProfileOut.model_validate(row).model_dump()


@router.get("/bazi/profile")
def get_bazi_profile(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """读取当前用户的命理档案；data 为 null 表示还没录入过。"""
    row = _owned(db, user)
    return ok(_out(row) if row is not None else None)


@router.put("/bazi/profile")
def save_bazi_profile(
    payload: BaziProfileIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """保存或覆盖当前用户的命理档案（重新录入即更新同一条）。"""
    row = _owned(db, user)
    if row is None:
        row = BaziProfile(id=new_id("bazi"), owner_id=user.id)
        db.add(row)

    row.name = payload.name.strip()
    row.gender = payload.gender
    row.year = payload.year
    row.month = payload.month
    row.day = payload.day
    row.hour = payload.hour
    row.minute = payload.minute
    row.province = payload.province.strip()
    row.city = payload.city.strip()
    row.longitude = payload.longitude
    row.pillars = _pillars_summary(payload)

    db.commit()
    db.refresh(row)
    return ok(_out(row))


@router.delete("/bazi/profile")
def delete_bazi_profile(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """清空当前用户的命理档案；本来就没有时同样返回 deleted=False。"""
    row = _owned(db, user)
    deleted = row is not None
    if row is not None:
        db.delete(row)
        db.commit()
    return ok({"deleted": deleted})
