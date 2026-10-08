# -*- coding: utf-8 -*-
"""安全层：密码哈希 + JWT 签发 / 校验。

设计要点：
- 直接用 bcrypt，不套 passlib —— passlib 1.7.4 读取 bcrypt 4.x/5.x 的
  `__about__` 属性会抛错，而 bcrypt 本身的 API 已经足够简单。
- JWT payload 里带 `typ` 字段区分 App 用户（user）与管理员（admin），
  两端的 token 互不通用，避免 App 端 token 越权访问后台接口。
"""

import datetime as dt
from typing import Any, Literal, Optional

import bcrypt
import jwt

from .config import JWT_ALGORITHM, JWT_EXPIRE_MINUTES, JWT_SECRET

TokenType = Literal["user", "admin"]

# bcrypt 只处理前 72 字节，超出部分会被静默忽略；bcrypt 5.x 直接报错，
# 因此这里先截断，保证长密码也能正常哈希。
_BCRYPT_MAX_BYTES = 72


def _to_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    """生成密码哈希，返回可直接入库的字符串。"""
    return bcrypt.hashpw(_to_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """校验密码。哈希格式非法时返回 False，不抛异常。"""
    try:
        return bcrypt.checkpw(_to_bytes(password), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_token(subject: str, token_type: TokenType) -> tuple[str, int]:
    """签发 JWT，返回 (token, 有效期秒数)。"""
    now = dt.datetime.now(dt.timezone.utc)
    expires = now + dt.timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": subject,
        "typ": token_type,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token, JWT_EXPIRE_MINUTES * 60


def decode_token(token: str) -> Optional[dict]:
    """解析 JWT。签名错误 / 过期 / 格式非法一律返回 None，由调用方转 401。"""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
