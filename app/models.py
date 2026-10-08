# -*- coding: utf-8 -*-
"""ORM 模型：用户体系 + 房屋档案。

- users      App 端用户，手机号唯一，走短信验证码登录
- admins     管理后台账号，独立于 users，权限边界分离
- sms_codes  短信验证码（落库而非内存，避免多进程 / 重启丢失）
- houses     房屋档案，通过 owner_id 归属到某个用户
"""

import datetime as dt
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _this_year() -> int:
    return dt.date.today().year


class User(Base):
    """App 端用户。手机号即账号，首次登录自动注册。"""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    phone: Mapped[str] = mapped_column(
        String(20), nullable=False, unique=True, index=True
    )
    nickname: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    avatar: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    # active / banned：封禁后 App 端登录被拒，但数据保留
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    ban_reason: Mapped[str] = mapped_column(String(200), nullable=False, default="")

    # 备注：运营在后台手工标注，仅后台可见
    remark: Mapped[str] = mapped_column(String(200), nullable=False, default="")

    login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_login_at: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Admin(Base):
    """管理后台账号。与 users 完全隔离，App 端 token 无法访问后台接口。"""

    __tablename__ = "admins"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(
        String(40), nullable=False, unique=True, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(40), nullable=False, default="")

    # active / disabled
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")

    last_login_at: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SmsCode(Base):
    """短信验证码记录。

    一次请求一行，校验通过后置 used=True；同一手机号限频见 auth 路由。
    """

    __tablename__ = "sms_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(8), nullable=False)
    scene: Mapped[str] = mapped_column(String(20), nullable=False, default="login")

    used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 校验失败次数，超过上限后该码作废，防止暴力穷举
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 发送方 IP，便于排查刷码
    request_ip: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    expires_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class House(Base):
    """房屋档案表。"""

    __tablename__ = "houses"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    # 归属用户；NULL 表示历史遗留数据（用户体系上线前创建的）
    owner_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )

    name: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    layout: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    area: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # 手机读取的磁方位角；NULL 表示还没用罗盘测量（不做 0 度兜底）
    degree: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    declination: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    year: Mapped[int] = mapped_column(
        Integer, nullable=False, default=_this_year
    )

    # 房间布局：JSON 数组 [{id, name, cell}]，与客户端 RoomProfile 一一对应
    rooms: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
