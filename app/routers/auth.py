# -*- coding: utf-8 -*-
"""认证路由：手机号 + 短信验证码登录。

    POST   /api/v1/auth/send-code        发送验证码
    POST   /api/v1/auth/login            验证码登录（新手机号自动注册）
    GET    /api/v1/auth/me               当前用户资料
    PATCH  /api/v1/auth/me               修改昵称 / 头像
    POST   /api/v1/auth/delete-account   注销账号（不可恢复）

App 端没有密码体系：验证码即凭证。管理员登录走 /api/v1/admin/login，两套 token 不通用。
"""

import datetime as dt
import random
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..config import (
    SMS_CODE_TTL_SECONDS,
    SMS_DEV_CODE,
    SMS_MAX_VERIFY_ATTEMPTS,
    SMS_PROVIDER,
    SMS_SEND_INTERVAL_SECONDS,
)
from ..db import get_db
from ..deps import get_current_user
from ..models import BaziProfile, CalcRecord, House, SmsCode, User
from ..schemas import (
    DeleteAccountOut,
    DeleteAccountRequest,
    LoginOut,
    LoginRequest,
    SendCodeRequest,
    UserOut,
    UserProfileUpdate,
)
from ..security import create_token
from ..sms import SmsSendError, get_sms_provider
from ..utils import as_aware, new_id, now_utc

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def ok(data):
    return {"code": 0, "status": "ok", "data": data}


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def _client_ip(request: Request) -> str:
    # 经过 Nginx 等反代时优先取 X-Forwarded-For 的第一跳
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "")[:64]


def _gen_code() -> str:
    """console 模式用固定码方便联调；真实短信必须用随机码。"""
    if SMS_PROVIDER == "console":
        return SMS_DEV_CODE
    return "".join(random.choices("0123456789", k=6))


@router.post("/send-code")
def send_code(
    payload: SendCodeRequest, request: Request, db: Session = Depends(get_db)
):
    """发送短信验证码。同一手机号 60 秒内限发一次。"""
    phone = payload.phone.strip()
    now = now_utc()

    latest = (
        db.query(SmsCode)
        .filter(SmsCode.phone == phone)
        .order_by(SmsCode.id.desc())
        .first()
    )
    if latest is not None:
        created = as_aware(latest.created_at)
        if created is not None:
            elapsed = (now - created).total_seconds()
            if elapsed < SMS_SEND_INTERVAL_SECONDS:
                wait = int(SMS_SEND_INTERVAL_SECONDS - elapsed) + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"发送过于频繁，请 {wait} 秒后再试",
                )

    code = _gen_code()
    db.add(
        SmsCode(
            phone=phone,
            code=code,
            scene=payload.scene,
            expires_at=now + dt.timedelta(seconds=SMS_CODE_TTL_SECONDS),
            request_ip=_client_ip(request),
        )
    )
    db.commit()

    try:
        get_sms_provider().send(phone, code, payload.scene)
    except SmsSendError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc

    data = {"phone": phone, "expires_in": SMS_CODE_TTL_SECONDS}
    # console 模式把验证码直接回给调用方，避免联调时翻服务端日志。
    # 注意：真实短信模式（aliyun）下这个字段不会出现。
    if SMS_PROVIDER == "console":
        data["debug_code"] = code
        data["notice"] = "当前为 console 开发模式，未发送真实短信"
    return ok(data)


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """验证码登录。手机号未注册时自动创建用户。"""
    phone = payload.phone.strip()
    now = now_utc()

    row = (
        db.query(SmsCode)
        .filter(SmsCode.phone == phone, SmsCode.used.is_(False))
        .order_by(SmsCode.id.desc())
        .first()
    )
    if row is None:
        raise _bad_request("请先获取验证码")
    if row.attempts >= SMS_MAX_VERIFY_ATTEMPTS:
        raise _bad_request("验证码错误次数过多，请重新获取")
    expires = as_aware(row.expires_at)
    if expires is not None and expires < now:
        raise _bad_request("验证码已过期，请重新获取")
    if row.code != payload.code.strip():
        row.attempts += 1
        db.commit()
        left = max(SMS_MAX_VERIFY_ATTEMPTS - row.attempts, 0)
        raise _bad_request(f"验证码不正确，还可尝试 {left} 次")

    row.used = True  # 一次性消费，防止重放

    user = db.query(User).filter(User.phone == phone).one_or_none()
    if user is None:
        user = User(id=new_id("u"), phone=phone, nickname=f"用户{phone[-4:]}")
        db.add(user)
        db.flush()

    if user.status != "active":
        db.commit()  # 保留 used 标记，避免被封禁账号反复消耗验证码
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=user.ban_reason or "账号已被封禁，请联系客服",
        )

    user.login_count = (user.login_count or 0) + 1
    user.last_login_at = now
    db.commit()
    db.refresh(user)

    token, expires_in = create_token(user.id, "user")
    return ok(
        LoginOut(
            token=token,
            expires_in=expires_in,
            user=UserOut.model_validate(user),
        ).model_dump()
    )


@router.get("/me")
def me(current: User = Depends(get_current_user)):
    """当前登录用户资料。App 启动时用它校验 token 是否仍有效。"""
    return ok(UserOut.model_validate(current).model_dump())


@router.patch("/me")
def update_me(
    payload: UserProfileUpdate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """修改昵称 / 头像。只允许改这两个字段。"""
    data = payload.model_dump(exclude_unset=True)
    if "nickname" in data and data["nickname"] is not None:
        current.nickname = data["nickname"].strip()
    if "avatar" in data and data["avatar"] is not None:
        current.avatar = data["avatar"].strip()
    db.commit()
    db.refresh(current)
    return ok(UserOut.model_validate(current).model_dump())


@router.post("/delete-account")
def delete_account(
    payload: DeleteAccountRequest,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """注销账号（不可恢复）。个人信息保护法下的账号删除入口。

    处置策略分两类，理由不同：

    - **物理删除**：命理档案、房屋档案、测算记录、短信验证码记录。这几类都是
      实打实的个人信息（出生时刻、住址特征、测算参数、手机号），注销时即刻抹掉。
    - **匿名化保留**：用户行本身。清空昵称 / 头像 / 备注 / 封禁原因，手机号
      改写为不可逆标记值，status 置 deleted。这样手机号被释放（同一号码可重新
      注册成全新账号），而 created_at / login_count 等统计字段留存，后台看板
      不会因为用户注销而出现数据断层。

    匿名化后 status != active，get_current_user 会直接拒绝，旧 token 立即失效。
    """
    if not payload.confirm:
        raise _bad_request("请确认后再执行注销")

    user_id = current.id
    phone = current.phone

    removed_bazi = (
        db.query(BaziProfile)
        .filter(BaziProfile.owner_id == user_id)
        .delete(synchronize_session=False)
    )
    removed_houses = (
        db.query(House)
        .filter(House.owner_id == user_id)
        .delete(synchronize_session=False)
    )
    # 测算记录里是出生信息与测算参数，同属个人信息，注销时一并物理删除
    removed_records = (
        db.query(CalcRecord)
        .filter(CalcRecord.owner_id == user_id)
        .delete(synchronize_session=False)
    )
    # 验证码按手机号清理：注销后这些码既无用途，也不该继续留存
    removed_sms = (
        db.query(SmsCode)
        .filter(SmsCode.phone == phone)
        .delete(synchronize_session=False)
    )

    # 手机号必须改写：phone 上有 unique 约束，不改写同一号码就再也注册不了。
    # 固定 16 字符，留足 phone 列 20 的上限，且与手机号格式明显区分，
    # 运营在后台一眼能看出这是已注销账号。
    current.phone = f"del-{uuid.uuid4().hex[:12]}"
    current.nickname = ""
    current.avatar = ""
    current.remark = ""
    current.ban_reason = ""
    current.status = "deleted"
    db.commit()

    return ok(
        DeleteAccountOut(
            user_id=user_id,
            removed_bazi_profiles=removed_bazi,
            removed_houses=removed_houses,
            removed_sms_codes=removed_sms,
            removed_calc_records=removed_records,
        ).model_dump()
    )
