# -*- coding: utf-8 -*-
"""测算记录路由：保存 / 列表 / 详情 / 删除，全部落库、全部要求登录。

与计算类接口（/bazi、/ziwei、/xuankong 等）的分界，也是本文件的存在理由：

- 计算类无状态、不落库、不要求登录——**一个字节都不改**；
- 本路由是档案类：必须登录，跨用户访问一律 404（不泄露「该 id 存在」）。

记录存的是**参数**而非结果快照：打开记录时由客户端按 params 重新请求对应
计算接口。引擎规则随 RULES_VERSION 改版，快照会留下过期判词；而六爻 / 梅花的
服务端装卦是纯函数（不含随机数），同一份入参必然还原同一次测算。

号码八星（phone_energy）刻意不在可保存范围：号码属个人信息，不往数据库里
落完整号码——与 phone-energy 接口只回脱敏号码同一口径。

    POST   /api/v1/records          保存（同参已存在则更新，不堆重复行）
    GET    /api/v1/records          当前用户的记录列表（updated_at 倒序）
    GET    /api/v1/records/{id}     单条详情（含 params）
    DELETE /api/v1/records/{id}     删除
"""

import hashlib
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import CalcRecord, User
from ..schemas import RecordDetailOut, RecordIn, RecordOut

router = APIRouter(prefix="/api/v1", tags=["records"])

# 可保存的测算类型白名单。新增页面接入保存时同步加这里，tests/test_records_api.py
# 锁住这份集合；label（「八字排盘」等展示名）由客户端持有，后端只做校验。
RECORD_KINDS = frozenset(
    {
        "bazi",  # 八字排盘（同一页含紫微盘）
        "bazhai",  # 八宅游年
        "xuankong",  # 玄空飞星（月盘 / 宅运盘，params.mode 区分）
        "almanac",  # 黄历（指定日期的通书）
        "divination",  # 六爻 / 梅花易数
        "marriage",  # 合婚配对
        "diagnose",  # 户型诊断
    }
)

# params 规范化序列化后的长度上限（字符）。各 kind 入参都是几十到几百字节，
# 8KB 足够，同时挡住误把整份结果传上来的情况。
MAX_PARAMS_CHARS = 8192

# 列表条数上限：记录只增不减，不设上限的话老用户的列表会无限变大
MAX_LIST_ITEMS = 200


def ok(data):
    return {"code": 0, "status": "ok", "data": data}


def _new_id() -> str:
    return "rec_" + uuid.uuid4().hex[:16]


def _canonical_params(params: dict) -> str:
    """参数规范化序列化：键排序，保证同一份入参得到同一个哈希。

    allow_nan=False：JSON 输入里可能混进 NaN / Infinity（Python 的 json.loads
    默认放行），它们无法写进 JSON 列，在这里先挡掉并转成 400。
    """
    return json.dumps(
        params, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _params_hash(params: dict) -> str:
    return hashlib.sha256(_canonical_params(params).encode("utf-8")).hexdigest()


def _out(row: CalcRecord) -> dict:
    return RecordOut.model_validate(row).model_dump()


def _detail(row: CalcRecord) -> dict:
    return RecordDetailOut.model_validate(row).model_dump()


def _get_owned(db: Session, record_id: str, user: User) -> CalcRecord:
    """取当前用户名下的记录；不存在或不属于自己都按 404 处理。"""
    row = db.get(CalcRecord, record_id)
    if row is None or row.owner_id != user.id:
        raise HTTPException(status_code=404, detail="测算记录不存在")
    return row


@router.post("/records")
def save_record(
    payload: RecordIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """保存一次测算。

    同参重复保存走**更新**（title / summary 刷新，updated_at 上浮），不为同一份
    入参堆重复行——列表按 updated_at 倒序，重存即置顶，语义是「最近再看一次」。
    """
    if payload.kind not in RECORD_KINDS:
        raise HTTPException(status_code=400, detail="不支持的测算类型")
    if not payload.params:
        raise HTTPException(status_code=400, detail="params 不能为空")
    try:
        canonical = _canonical_params(payload.params)
    except ValueError:
        raise HTTPException(status_code=400, detail="params 含非法数值（NaN 等）")
    if len(canonical) > MAX_PARAMS_CHARS:
        raise HTTPException(status_code=400, detail="params 过大")

    digest = _params_hash(payload.params)
    row = (
        db.query(CalcRecord)
        .filter(
            CalcRecord.owner_id == user.id,
            CalcRecord.kind == payload.kind,
            CalcRecord.params_hash == digest,
        )
        .first()
    )
    if row is None:
        row = CalcRecord(
            id=_new_id(),
            owner_id=user.id,
            kind=payload.kind,
            params_hash=digest,
        )
        db.add(row)

    row.title = payload.title.strip()
    row.summary = payload.summary.strip()
    row.params = payload.params
    try:
        db.commit()
    except IntegrityError:
        # 并发保存同一份入参时，唯一约束先一步拦住：回滚后按更新处理
        db.rollback()
        row = (
            db.query(CalcRecord)
            .filter(
                CalcRecord.owner_id == user.id,
                CalcRecord.kind == payload.kind,
                CalcRecord.params_hash == digest,
            )
            .first()
        )
        if row is None:
            raise HTTPException(status_code=409, detail="保存冲突，请重试")
        row.title = payload.title.strip()
        row.summary = payload.summary.strip()
        row.params = payload.params
        db.commit()

    db.refresh(row)
    return ok(_detail(row))


@router.get("/records")
def list_records(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """当前用户的记录列表，按更新时间倒序（重存过的会浮到最前）。"""
    rows = (
        db.query(CalcRecord)
        .filter(CalcRecord.owner_id == user.id)
        .order_by(CalcRecord.updated_at.desc())
        .limit(MAX_LIST_ITEMS)
        .all()
    )
    return ok({"total": len(rows), "items": [_out(r) for r in rows]})


@router.get("/records/{record_id}")
def get_record(
    record_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """单条详情，含 params——客户端拿到后按 kind 回放到对应测算页。"""
    return ok(_detail(_get_owned(db, record_id, user)))


@router.delete("/records/{record_id}")
def delete_record(
    record_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.get(CalcRecord, record_id)
    owned = row is not None and row.owner_id == user.id
    if owned:
        db.delete(row)
        db.commit()
    # 不属于自己时同样返回 deleted=False，不暴露 id 是否存在
    return ok({"id": record_id, "deleted": owned})
