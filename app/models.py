# -*- coding: utf-8 -*-
"""ORM 模型：房屋档案落库。

房屋是诊断的唯一输入源，新建 / 编辑 / 测量回写都要入库，
不再只留在客户端本地存储里。
"""

import datetime as dt
from typing import Optional

from sqlalchemy import JSON, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _this_year() -> int:
    return dt.date.today().year


class House(Base):
    """房屋档案表。"""

    __tablename__ = "houses"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
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
