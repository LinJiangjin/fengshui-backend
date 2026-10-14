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
    GET    /api/v1/admin/schemes                装修方案分页列表（运营内容）
    GET    /api/v1/admin/schemes/{id}           方案详情
    POST   /api/v1/admin/schemes                新建方案
    PUT    /api/v1/admin/schemes/{id}           全量更新方案
    PATCH  /api/v1/admin/schemes/{id}/status    上架 / 下架
    DELETE /api/v1/admin/schemes/{id}           删除方案
    GET    /api/v1/admin/element-notes          五行宜忌解读列表
    PUT    /api/v1/admin/element-notes/{element} 更新某行五行的解读

除 login 外全部依赖 `require_admin`，App 端用户 token 访问一律 401。
"""

import datetime as dt
import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..config import APP_TIMEZONE_OFFSET_HOURS
from ..db import get_db
from ..deps import require_admin
from ..models import Admin, BaziProfile, ElementNote, House, Scheme, User
from ..schemas import (
    AdminBaziProfileItem,
    AdminBaziProfilePage,
    AdminHouseItem,
    AdminHousePage,
    AdminLoginOut,
    AdminLoginRequest,
    AdminOut,
    AdminSchemeItem,
    AdminSchemePage,
    AdminUserItem,
    AdminUserPage,
    ElementNoteItem,
    ElementNoteUpdate,
    PageMeta,
    SchemeIn,
    SchemeStatusUpdate,
    StatsOut,
    TrendPoint,
    UserOut,
    UserRemarkUpdate,
    UserStatusUpdate,
)
from ..security import create_token, verify_password
# 五行相生序（木火土金水）：新建解读时按它排位，与初始化数据保持同一口径
from ..seed_library import ELEMENT_ORDER as _ELEMENT_SORT_ORDER
from ..utils import (
    as_aware,
    local_date_str,
    local_day_start_utc,
    new_id,
    now_utc,
    page_bounds,
)

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
        "",
        alias="status",
        description="active / banned / deleted，空表示全部（不含已注销）",
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
    if user_status in ("active", "banned", "deleted"):
        query = query.filter(User.status == user_status)
    else:
        # 默认不展示已注销账号：注销后只剩一条匿名化空壳（手机号已抹除），
        # 混在列表里没有运营价值，要看需显式传 status=deleted
        query = query.filter(User.status != "deleted")

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

    # 已注销账号（status=deleted）不计入任何用户口径：注销后它只剩一条匿名化
    # 空壳，手机号已抹除，不代表任何现存用户。若计入，看板会显示"看得见却联系
    # 不上"的幽灵用户。房屋与档案在注销时已物理删除，因此那两个口径无需过滤。
    alive = User.status != "deleted"

    total_users = db.query(func.count(User.id)).filter(alive).scalar() or 0
    new_today = (
        db.query(func.count(User.id))
        .filter(alive, User.created_at >= today_start)
        .scalar()
        or 0
    )
    new_7d = (
        db.query(func.count(User.id))
        .filter(alive, User.created_at >= week_start)
        .scalar()
        or 0
    )
    active_7d = (
        db.query(func.count(User.id))
        .filter(
            alive,
            User.last_login_at.isnot(None),
            User.last_login_at >= week_start,
        )
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
        db.query(User.created_at)
        .filter(alive, User.created_at >= trend_start)
        .all()
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


# ------------------------------------------------------------------ 方案库
def _scheme_fields(payload: SchemeIn) -> dict:
    """把入参整理成可直接写库的列值。

    - 文本两端空格统一去掉：运营在后台粘贴文案时很容易带上；
    - 色值统一转大写，和 App 端既有素材保持一致；
    - 空字符串的亮点条目直接丢弃，避免详情页出现空行。
    """
    data = payload.model_dump()
    return {
        "title": data["title"].strip(),
        "subtitle": data["subtitle"].strip(),
        "tag": data["tag"].strip(),
        "element": data["element"],
        "area": data["area"],
        "from_color": data["from_color"].upper(),
        "to_color": data["to_color"].upper(),
        "summary": data["summary"].strip(),
        "highlights": [h.strip() for h in data["highlights"] if h.strip()],
        "colors": data["colors"],
        "rooms": data["rooms"],
        "published": data["published"],
        "sort_order": data["sort_order"],
    }


def _scheme_to_item(scheme: Scheme) -> AdminSchemeItem:
    """库里一行 -> 后台出参。文本字段已由写入侧校验，这里直接透传。"""
    return AdminSchemeItem(
        id=scheme.id,
        title=scheme.title or "",
        subtitle=scheme.subtitle or "",
        tag=scheme.tag or "",
        element=scheme.element or "",
        area=scheme.area or 0,
        from_color=scheme.from_color or "",
        to_color=scheme.to_color or "",
        summary=scheme.summary or "",
        highlights=[str(h) for h in (scheme.highlights or [])],
        colors=list(scheme.colors or []),
        rooms=list(scheme.rooms or []),
        published=bool(scheme.published),
        sort_order=scheme.sort_order or 0,
        created_at=scheme.created_at,
        updated_at=scheme.updated_at,
    )


@router.get("/schemes")
def list_schemes(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    keyword: str = Query("", max_length=40, description="标题 / 副标题 / 风格 / 方案 id"),
    element: str = Query("", description="五行筛选：木 火 土 金 水，留空表示全部"),
    published: str = Query("", description="published / draft，留空表示全部"),
    current: Admin = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """装修方案分页列表。后台能看到已下架的方案，App 端看不到。"""
    if element and not re.fullmatch(r"[木火土金水]", element):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="element 只支持 木 / 火 / 土 / 金 / 水",
        )
    if published not in ("", "published", "draft"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="published 只支持 published / draft",
        )

    query = db.query(Scheme)

    kw = keyword.strip()
    if kw:
        like = f"%{kw}%"
        query = query.filter(
            or_(
                Scheme.title.like(like),
                Scheme.subtitle.like(like),
                Scheme.tag.like(like),
                Scheme.id.like(like),
            )
        )
    if element:
        query = query.filter(Scheme.element == element)
    if published == "published":
        query = query.filter(Scheme.published.is_(True))
    elif published == "draft":
        query = query.filter(Scheme.published.is_(False))

    total = query.count()
    _, offset, pages = page_bounds(total, page, size)
    rows = (
        query.order_by(Scheme.sort_order.asc(), Scheme.id.asc())
        .offset(offset)
        .limit(size)
        .all()
    )

    return ok(
        AdminSchemePage(
            page_meta=PageMeta(total=total, page=page, size=size, pages=pages),
            items=[_scheme_to_item(row) for row in rows],
        ).model_dump()
    )


@router.get("/schemes/{scheme_id}")
def get_scheme(
    scheme_id: str,
    current: Admin = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """方案详情（后台编辑表单回填用）。"""
    scheme = db.get(Scheme, scheme_id)
    if scheme is None:
        raise _not_found("方案不存在")
    return ok(_scheme_to_item(scheme).model_dump())


@router.post("/schemes")
def create_scheme(
    payload: SchemeIn,
    current: Admin = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """新建方案。id 由服务端生成，不接受客户端指定。"""
    scheme = Scheme(id=new_id("sch"), **_scheme_fields(payload))
    db.add(scheme)
    db.commit()
    db.refresh(scheme)
    return ok(_scheme_to_item(scheme).model_dump())


@router.put("/schemes/{scheme_id}")
def update_scheme(
    scheme_id: str,
    payload: SchemeIn,
    current: Admin = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """全量更新方案。

    用全量覆盖而非 PATCH：后台表单本来就把整条方案一次提交，
    部分更新反而容易让「提交了但没生效」这类问题变难查。
    """
    scheme = db.get(Scheme, scheme_id)
    if scheme is None:
        raise _not_found("方案不存在")

    for field, value in _scheme_fields(payload).items():
        setattr(scheme, field, value)
    db.commit()
    db.refresh(scheme)
    return ok(_scheme_to_item(scheme).model_dump())


@router.patch("/schemes/{scheme_id}/status")
def update_scheme_status(
    scheme_id: str,
    payload: SchemeStatusUpdate,
    current: Admin = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """上架 / 下架。下架只是从 App 端隐藏，数据保留可随时恢复。"""
    scheme = db.get(Scheme, scheme_id)
    if scheme is None:
        raise _not_found("方案不存在")
    scheme.published = payload.published
    db.commit()
    db.refresh(scheme)
    return ok(_scheme_to_item(scheme).model_dump())


@router.delete("/schemes/{scheme_id}")
def delete_scheme(
    scheme_id: str,
    current: Admin = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """删除方案。不可恢复，运营侧需二次确认。"""
    scheme = db.get(Scheme, scheme_id)
    if scheme is None:
        raise _not_found("方案不存在")
    db.delete(scheme)
    db.commit()
    return ok({"id": scheme_id, "deleted": True})


# ------------------------------------------------------------------ 五行解读
@router.get("/element-notes")
def list_element_notes(
    current: Admin = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """五行宜忌解读列表。方案详情页的「宜 / 忌」按方案所属五行取这里。"""
    rows = (
        db.query(ElementNote)
        .order_by(ElementNote.sort_order.asc(), ElementNote.element.asc())
        .all()
    )
    return ok([ElementNoteItem.model_validate(row).model_dump() for row in rows])


@router.put("/element-notes/{element}")
def upsert_element_note(
    element: str,
    payload: ElementNoteUpdate,
    current: Admin = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """更新某行五行的解读。

    用 upsert 而非纯 update：新增一行五行时不必先手工插记录，
    少了「忘了初始化就改不动」这类运营侧卡点。
    """
    if not re.fullmatch(r"[木火土金水]", element):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="五行只支持 木 / 火 / 土 / 金 / 水",
        )

    note = db.get(ElementNote, element)
    if note is None:
        note = ElementNote(
            element=element,
            sort_order=_ELEMENT_SORT_ORDER.get(element, 99),
        )
        db.add(note)

    note.fit = payload.fit.strip()
    note.avoid = payload.avoid.strip()
    db.commit()
    db.refresh(note)
    return ok(ElementNoteItem.model_validate(note).model_dump())
