# -*- coding: utf-8 -*-
"""管理后台路由：管理员登录 + 用户管理 + 房屋管理 + 统计看板。

    POST   /api/v1/admin/login                  管理员登录
    GET    /api/v1/admin/me                     当前管理员
    GET    /api/v1/admin/users                  用户分页列表（搜索 / 状态筛选）
    GET    /api/v1/admin/users/{id}             用户详情（含名下房屋）
    PATCH  /api/v1/admin/users/{id}/status      封禁 / 解封
    PATCH  /api/v1/admin/users/{id}/remark      运营备注
    DELETE /api/v1/admin/users/{id}             删除用户（可选级联删其房屋）
    GET    /api/v1/admin/stats                  看板统计
    GET    /api/v1/admin/houses                 房屋数据分页列表
    DELETE /api/v1/admin/houses/{id}            删除房屋
    GET    /api/v1/admin/bazi-profiles          命理档案分页列表（用户录入的出生信息）
    DELETE /api/v1/admin/bazi-profiles/{id}     删除命理档案

除 login 外全部依赖 `require_admin`，App 端用户 token 访问一律 401。
"""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..config import APP_TIMEZONE_OFFSET_HOURS
from ..db import get_db
from ..deps import require_admin
from ..models import Admin, BaziProfile, House, User
from ..schemas import (
    AdminBaziProfileItem,
    AdminBaziProfilePage,
    AdminHouseItem,
    AdminHousePage,
    AdminLoginOut,
    AdminLoginRequest,
    AdminOut,
    AdminUserItem,
    AdminUserPage,
    PageMeta,
    StatsOut,
    TrendPoint,
    UserOut,
    UserRemarkUpdate,
    UserStatusUpdate,
)
from ..security import create_token, verify_password
from ..utils import as_aware, local_date_str, local_day_start_utc, now_utc, page_bounds

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def ok(data):
    return {"code": 0, "status": "ok", "data": data}


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _house_counts(db: Session, owner_ids: list[str]) -> dict[str, int]:
    """批量统计这批用户名下的房屋数，避免逐行 count 造成 N+1 查询。"""
    if not owner_ids:
        return {}
    rows = (
        db.query(House.owner_id, func.count(House.id))
        .filter(House.owner_id.in_(owner_ids))
        .group_by(House.owner_id)
        .all()
    )
    return {owner_id: count for owner_id, count in rows if owner_id}


# ------------------------------------------------------------------ 登录
@router.post("/login")
def admin_login(payload: AdminLoginRequest, db: Session = Depends(get_db)):
    """管理员账号密码登录。"""
    username = payload.username.strip()
    admin = db.query(Admin).filter(Admin.username == username).one_or_none()

    # 用户名不存在与密码错误返回同一句提示，避免账号枚举
    if admin is None or not verify_password(payload.password, admin.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码不正确"
        )
    if admin.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="该管理员账号已停用"
        )

    admin.last_login_at = now_utc()
    db.commit()
    db.refresh(admin)

    token, expires_in = create_token(admin.id, "admin")
    return ok(
        AdminLoginOut(
            token=token,
            expires_in=expires_in,
            admin=AdminOut.model_validate(admin),
        ).model_dump()
    )


@router.get("/me")
def admin_me(current: Admin = Depends(require_admin)):
    return ok(AdminOut.model_validate(current).model_dump())


# ------------------------------------------------------------------ 用户管理
@router.get("/users")
def list_users(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    keyword: str = Query("", max_length=40, description="手机号 / 昵称 / id 模糊匹配"),
    user_status: str = Query(
        "", alias="status", description="active / banned，空表示全部"
    ),
    current: Admin = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """用户分页列表，按注册时间倒序。"""
    query = db.query(User)

    kw = keyword.strip()
    if kw:
        like = f"%{kw}%"
        query = query.filter(
            or_(User.phone.like(like), User.nickname.like(like), User.id.like(like))
        )
    if user_status in ("active", "banned"):
        query = query.filter(User.status == user_status)

    total = query.count()
    _, offset, pages = page_bounds(total, page, size)
    rows = (
        query.order_by(User.created_at.desc(), User.id.desc())
        .offset(offset)
        .limit(size)
        .all()
    )

    counts = _house_counts(db, [r.id for r in rows])
    items = [
        AdminUserItem(
            **UserOut.model_validate(r).model_dump(),
            house_count=counts.get(r.id, 0),
        )
        for r in rows
    ]
    return ok(
        AdminUserPage(
            page_meta=PageMeta(total=total, page=page, size=size, pages=pages),
            items=items,
        ).model_dump()
    )


@router.get("/users/{user_id}")
def get_user(
    user_id: str,
    current: Admin = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """用户详情：资料 + 名下房屋摘要。"""
    user = db.get(User, user_id)
    if user is None:
        raise _not_found("用户不存在")

    house_rows = (
        db.query(House)
        .filter(House.owner_id == user_id)
        .order_by(House.updated_at.desc())
        .all()
    )

    return ok(
        {
            "user": UserOut.model_validate(user).model_dump(),
            "houses": [
                AdminHouseItem(
                    id=h.id,
                    owner_id=h.owner_id,
                    owner_phone=user.phone,
                    owner_nickname=user.nickname,
                    name=h.name or "",
                    layout=h.layout or "",
                    area=h.area or 0.0,
                    degree=h.degree,
                    year=h.year,
                    room_count=len(h.rooms or []),
                    created_at=h.created_at,
                    updated_at=h.updated_at,
                ).model_dump()
                for h in house_rows
            ],
        }
    )


@router.patch("/users/{user_id}/status")
def update_user_status(
    user_id: str,
    payload: UserStatusUpdate,
    current: Admin = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """封禁 / 解封。封禁需填原因，解封时自动清空。"""
    user = db.get(User, user_id)
    if user is None:
        raise _not_found("用户不存在")

    if payload.status == "banned":
        user.ban_reason = payload.reason.strip() or "违反社区规范"
    else:
        user.ban_reason = ""

    user.status = payload.status
    db.commit()
    db.refresh(user)
    return ok(UserOut.model_validate(user).model_dump())


@router.patch("/users/{user_id}/remark")
def update_user_remark(
    user_id: str,
    payload: UserRemarkUpdate,
    current: Admin = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """更新运营备注，仅后台可见，App 端不返回该字段的编辑入口。"""
    user = db.get(User, user_id)
    if user is None:
        raise _not_found("用户不存在")
    user.remark = payload.remark.strip()
    db.commit()
    db.refresh(user)
    return ok(UserOut.model_validate(user).model_dump())


@router.delete("/users/{user_id}")
def delete_user(
    user_id: str,
    with_houses: bool = Query(False, description="是否同时删除该用户名下所有房屋"),
    current: Admin = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """删除用户。默认保留房屋（owner_id 置空），with_houses=true 时一并删除。

    默认保留是刻意的：误删账号不该顺带毁掉数据，需要连数据一起清理时显式传参。
    """
    user = db.get(User, user_id)
    if user is None:
        raise _not_found("用户不存在")

    houses = db.query(House).filter(House.owner_id == user_id).all()
    if with_houses:
        for house in houses:
            db.delete(house)
        removed_houses = len(houses)
    else:
        for house in houses:
            house.owner_id = None  # 保留数据，解除归属
        removed_houses = 0

    db.delete(user)
    db.commit()
    return ok(
        {
            "id": user_id,
            "deleted": True,
            "detached_houses": len(houses) if not with_houses else 0,
            "deleted_houses": removed_houses,
        }
    )


# ------------------------------------------------------------------ 看板
@router.get("/stats")
def stats(
    current: Admin = Depends(require_admin), db: Session = Depends(get_db)
):
    """看板统计。时间口径按本地时区切分，见 app/utils.py。"""
    today_start = local_day_start_utc(0)
    week_start = local_day_start_utc(6)

    total_users = db.query(func.count(User.id)).scalar() or 0
    new_today = (
        db.query(func.count(User.id)).filter(User.created_at >= today_start).scalar()
        or 0
    )
    new_7d = (
        db.query(func.count(User.id)).filter(User.created_at >= week_start).scalar()
        or 0
    )
    active_7d = (
        db.query(func.count(User.id))
        .filter(User.last_login_at.isnot(None), User.last_login_at >= week_start)
        .scalar()
        or 0
    )
    banned_users = (
        db.query(func.count(User.id)).filter(User.status == "banned").scalar() or 0
    )
    total_houses = db.query(func.count(House.id)).scalar() or 0
    measured_houses = (
        db.query(func.count(House.id)).filter(House.degree.isnot(None)).scalar() or 0
    )

    # 近 14 天新增趋势：只取该区间数据，在 Python 侧按本地日期分桶
    span_days = 14
    trend_start = local_day_start_utc(span_days - 1)
    created_rows = (
        db.query(User.created_at).filter(User.created_at >= trend_start).all()
    )
    offset = dt.timedelta(hours=APP_TIMEZONE_OFFSET_HOURS)
    buckets: dict[str, int] = {}
    for (created_at,) in created_rows:
        aware = as_aware(created_at)
        if aware is None:
            continue
        key = (aware + offset).strftime("%Y-%m-%d")
        buckets[key] = buckets.get(key, 0) + 1

    trend = [
        TrendPoint(
            date=local_date_str(span_days - 1 - i),
            new_users=buckets.get(local_date_str(span_days - 1 - i), 0),
        )
        for i in range(span_days)
    ]

    return ok(
        StatsOut(
            total_users=total_users,
            new_today=new_today,
            new_7d=new_7d,
            active_7d=active_7d,
            banned_users=banned_users,
            total_houses=total_houses,
            measured_houses=measured_houses,
            trend=trend,
        ).model_dump()
    )


# ------------------------------------------------------------------ 房屋管理
@router.get("/houses")
def list_houses(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    keyword: str = Query("", max_length=40, description="房屋名 / 用户手机号 / 房屋 id"),
    current: Admin = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """房屋数据分页列表，带归属用户信息。"""
    query = db.query(House, User).outerjoin(User, House.owner_id == User.id)

    kw = keyword.strip()
    if kw:
        like = f"%{kw}%"
        query = query.filter(
            or_(House.name.like(like), House.id.like(like), User.phone.like(like))
        )

    total = query.count()
    _, offset, pages = page_bounds(total, page, size)
    rows = (
        query.order_by(House.updated_at.desc(), House.id.desc())
        .offset(offset)
        .limit(size)
        .all()
    )

    # 传模型实例而非 model_dump() 的 dict：AdminHousePage.items 声明为
    # list[AdminHouseItem]，list 类型参数不变，dict 不能顶替模型（也省掉一轮
    # dict -> 模型的重复校验）。最终由外层 .model_dump() 统一序列化。
    items: list[AdminHouseItem] = [
        AdminHouseItem(
            id=house.id,
            owner_id=house.owner_id,
            owner_phone=user.phone if user else "",
            owner_nickname=user.nickname if user else "",
            name=house.name or "",
            layout=house.layout or "",
            area=house.area or 0.0,
            degree=house.degree,
            year=house.year,
            room_count=len(house.rooms or []),
            created_at=house.created_at,
            updated_at=house.updated_at,
        )
        for house, user in rows
    ]
    return ok(
        AdminHousePage(
            page_meta=PageMeta(total=total, page=page, size=size, pages=pages),
            items=items,
        ).model_dump()
    )


@router.delete("/houses/{house_id}")
def delete_house(
    house_id: str,
    current: Admin = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """删除房屋（违规内容清理用）。"""
    house = db.get(House, house_id)
    if house is None:
        raise _not_found("房屋不存在")
    db.delete(house)
    db.commit()
    return ok({"id": house_id, "deleted": True})


# ------------------------------------------------------------------ 命理档案
@router.get("/bazi-profiles")
def list_bazi_profiles(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    keyword: str = Query("", max_length=40, description="姓名 / 用户手机号 / 昵称"),
    gender: str = Query("", description="性别筛选：男 / 女，留空表示全部"),
    current: Admin = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """命理档案分页列表，带归属用户信息。"""
    if gender not in ("", "男", "女"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="gender 只支持 男 / 女",
        )

    query = db.query(BaziProfile, User).outerjoin(
        User, BaziProfile.owner_id == User.id
    )

    kw = keyword.strip()
    if kw:
        like = f"%{kw}%"
        query = query.filter(
            or_(
                BaziProfile.name.like(like),
                User.phone.like(like),
                User.nickname.like(like),
            )
        )
    if gender:
        query = query.filter(BaziProfile.gender == gender)

    total = query.count()
    _, offset, pages = page_bounds(total, page, size)
    rows = (
        query.order_by(BaziProfile.updated_at.desc(), BaziProfile.id.desc())
        .offset(offset)
        .limit(size)
        .all()
    )

    items: list[AdminBaziProfileItem] = []
    for profile, user in rows:
        item = AdminBaziProfileItem.model_validate(profile)
        # 归属用户信息不在档案模型里，单独补上
        item.owner_id = profile.owner_id
        item.owner_phone = user.phone if user else ""
        item.owner_nickname = user.nickname if user else ""
        items.append(item)

    return ok(
        AdminBaziProfilePage(
            page_meta=PageMeta(total=total, page=page, size=size, pages=pages),
            items=items,
        ).model_dump()
    )


@router.delete("/bazi-profiles/{profile_id}")
def delete_bazi_profile(
    profile_id: str,
    current: Admin = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """删除命理档案（违规内容清理用）。"""
    profile = db.get(BaziProfile, profile_id)
    if profile is None:
        raise _not_found("命理档案不存在")
    db.delete(profile)
    db.commit()
    return ok({"id": profile_id, "deleted": True})
