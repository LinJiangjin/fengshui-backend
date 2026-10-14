# -*- coding: utf-8 -*-
"""FastAPI 鉴权依赖。

- `get_current_user`  App 端用户，token 里 typ 必须是 user
- `require_admin`     管理后台，token 里 typ 必须是 admin
- `get_optional_user` 可选登录，未登录返回 None（用于既能匿名又能登录的接口）

App 端 token 与后台 token 不通用：typ 不匹配直接 401，
即使 App 用户 token 泄露也无法访问 /api/v1/admin/*。
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .db import get_db
from .models import Admin, User
from .security import decode_token

# auto_error=False：自己抛 401，保证响应格式可控
_bearer = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _decode(credentials: HTTPAuthorizationCredentials | None, expect: str) -> dict:
    if credentials is None or not credentials.credentials:
        raise _unauthorized("缺少登录凭证")
    payload = decode_token(credentials.credentials)
    if payload is None:
        raise _unauthorized("登录已过期，请重新登录")
    if payload.get("typ") != expect:
        raise _unauthorized("凭证类型不匹配")
    return payload


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """取当前 App 用户；被封禁的账号一律拒绝。"""
    payload = _decode(credentials, "user")
    user = db.get(User, payload.get("sub") or "")
    if user is None:
        raise _unauthorized("用户不存在")
    # 注销与封禁都会让 status 离开 active，但提示语不同：
    # 注销是用户自己的选择，不该回一句「账号已被封禁」。
    if user.status == "deleted":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="账号已注销"
        )
    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=user.ban_reason or "账号已被封禁",
        )
    return user


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User | None:
    """可选登录：无 token / token 失效时返回 None，不抛异常。

    用于房屋列表这类「登录看自己的、未登录看空的」接口，
    避免客户端首次启动还没登录就拿到 401。
    """
    if credentials is None or not credentials.credentials:
        return None
    payload = decode_token(credentials.credentials)
    if payload is None or payload.get("typ") != "user":
        return None
    user = db.get(User, payload.get("sub") or "")
    if user is None or user.status != "active":
        return None
    return user


def require_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> Admin:
    """取当前管理员；被停用的账号拒绝。"""
    payload = _decode(credentials, "admin")
    admin = db.get(Admin, payload.get("sub") or "")
    if admin is None:
        raise _unauthorized("管理员不存在")
    if admin.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="管理员账号已停用"
        )
    return admin
