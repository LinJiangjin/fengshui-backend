# -*- coding: utf-8 -*-
"""房屋档案路由：新建 / 编辑 / 测量回写 / 删除，全部落库。

用户体系上线后，房屋与用户绑定：所有读写都在当前登录用户名下，
跨用户访问一律返回 404（而非 403，避免泄露「该 id 存在」这一信息）。

    POST   /api/v1/houses          新建或更新（按 id upsert）
    GET    /api/v1/houses          当前用户的房屋列表
    GET    /api/v1/houses/{id}     单条
    PATCH  /api/v1/houses/{id}     局部更新（罗盘测量后回写坐向）
    DELETE /api/v1/houses/{id}     删除

注意：用户体系上线前的历史房屋记录 owner_id 为 NULL，不再出现在任何用户的
列表里。如需保留，见 scripts/claim_orphan_houses.py。
"""

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import House, User
from ..schemas import HouseIn, HouseOut, HousePatch, RoomIn

router = APIRouter(prefix="/api/v1", tags=["house"])


def ok(data):
    return {"code": 0, "status": "ok", "data": data}


def _norm_degree(degree):
    """磁北读数归一化到 [0, 360)；None 表示未测量，原样返回。"""
    if degree is None:
        return None
    return degree % 360.0


def _new_id() -> str:
    return "house_" + uuid.uuid4().hex[:16]


def _rooms_dicts(rooms) -> list:
    return [r.model_dump() if isinstance(r, RoomIn) else dict(r) for r in (rooms or [])]


def _out(row: House) -> dict:
    return HouseOut(
        id=row.id,
        name=row.name,
        layout=row.layout or "",
        area=row.area or 0.0,
        degree=row.degree,
        declination=row.declination or 0.0,
        year=row.year,
        rooms=[RoomIn(**r) for r in (row.rooms or [])],
    ).model_dump()


def _get_owned(db: Session, house_id: str, user: User) -> House:
    """取当前用户名下的房屋；不存在或不属于自己都按 404 处理。"""
    row = db.get(House, house_id)
    if row is None or row.owner_id != user.id:
        raise HTTPException(status_code=404, detail="房屋不存在")
    return row


@router.post("/houses")
def upsert_house(
    payload: HouseIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """新建或更新一套房屋，并把结果原样返回（前端以服务端返回为准）。"""
    house_id = payload.id.strip()
    if house_id:
        row = _get_owned(db, house_id, user)  # 已有房屋：必须是自己名下的
    else:
        house_id = _new_id()
        row = House(id=house_id, owner_id=user.id)
        db.add(row)

    row.name = payload.name.strip()
    row.layout = payload.layout.strip()
    row.area = payload.area
    row.degree = _norm_degree(payload.degree)
    row.declination = payload.declination
    row.year = payload.year or row.year or dt.date.today().year
    row.rooms = _rooms_dicts(payload.rooms)

    db.commit()
    db.refresh(row)
    return ok(_out(row))


@router.get("/houses")
def list_houses(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """当前用户的房屋列表，按更新时间倒序。"""
    rows = (
        db.query(House)
        .filter(House.owner_id == user.id)
        .order_by(House.updated_at.desc())
        .all()
    )
    return ok({"total": len(rows), "items": [_out(r) for r in rows]})


@router.get("/houses/{house_id}")
def get_house(
    house_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ok(_out(_get_owned(db, house_id, user)))


@router.patch("/houses/{house_id}")
def patch_house(
    house_id: str,
    payload: HousePatch,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """局部更新：罗盘测量后回写坐向、保存布局方案等。"""
    row = _get_owned(db, house_id, user)
    data = payload.model_dump(exclude_unset=True)

    if "degree" in data:
        row.degree = _norm_degree(data["degree"])
    if "declination" in data:
        row.declination = data["declination"]
    if "name" in data:
        row.name = data["name"].strip()
    if "layout" in data:
        row.layout = data["layout"].strip()
    if "area" in data:
        row.area = data["area"]
    if "rooms" in data:
        row.rooms = [dict(r) for r in (data["rooms"] or [])]

    db.commit()
    db.refresh(row)
    return ok(_out(row))


@router.delete("/houses/{house_id}")
def delete_house(
    house_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.get(House, house_id)
    owned = row is not None and row.owner_id == user.id
    if owned:
        db.delete(row)
        db.commit()
    # 不属于自己时同样返回 deleted=False，不暴露 id 是否存在
    return ok({"id": house_id, "deleted": owned})
