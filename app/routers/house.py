# -*- coding: utf-8 -*-
"""房屋档案路由：新建 / 编辑 / 测量回写 / 删除，全部落库。

客户端不再只把房屋存在本地 SharedPreferences，改由服务端持久化：
    POST   /api/v1/houses          新建或更新（按 id upsert）
    GET    /api/v1/houses          房屋列表
    GET    /api/v1/houses/{id}     单条
    PATCH  /api/v1/houses/{id}     局部更新（罗盘测量后回写坐向）
    DELETE /api/v1/houses/{id}     删除
"""

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import House
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


def _get(db: Session, house_id: str) -> House:
    row = db.get(House, house_id)
    if row is None:
        raise HTTPException(status_code=404, detail="房屋不存在")
    return row


@router.post("/houses")
def upsert_house(payload: HouseIn, db: Session = Depends(get_db)):
    """新建或更新一套房屋，并把结果原样返回（前端以服务端返回为准）。"""
    house_id = payload.id.strip() or _new_id()
    row = db.get(House, house_id)
    if row is None:
        row = House(id=house_id)
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
def list_houses(db: Session = Depends(get_db)):
    """房屋列表，按更新时间倒序。"""
    rows = db.query(House).order_by(House.updated_at.desc()).all()
    return ok({"total": len(rows), "items": [_out(r) for r in rows]})


@router.get("/houses/{house_id}")
def get_house(house_id: str, db: Session = Depends(get_db)):
    return ok(_out(_get(db, house_id)))


@router.patch("/houses/{house_id}")
def patch_house(
    house_id: str, payload: HousePatch, db: Session = Depends(get_db)
):
    """局部更新：罗盘测量后回写坐向、保存布局方案等。"""
    row = _get(db, house_id)
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
def delete_house(house_id: str, db: Session = Depends(get_db)):
    row = db.get(House, house_id)
    if row is not None:
        db.delete(row)
        db.commit()
    return ok({"id": house_id, "deleted": row is not None})
