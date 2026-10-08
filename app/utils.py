# -*- coding: utf-8 -*-
"""跨路由共用的小工具：时间归一化、分页、id 生成。

时区策略（重要）：
- 所有时间**以 UTC 存储**，写入时统一用 `now_utc()`（带 tzinfo 的 aware datetime）。
- PostgreSQL 的 timestamptz 会保留时区，读出来是 aware；SQLite 存字符串，
  读出来是 naive。因此比较前一律用 `as_aware()` 归一化，避免
  「naive 与 aware 不能相减」这类运行期错误。
- 「今天 / 近 7 天」这类业务统计按**本地时区**（默认 UTC+8）切分，
  由 `local_day_start_utc()` 把本地零点换算成 UTC 时间点再查询。
"""

import datetime as dt
import uuid
from typing import Optional

from .config import APP_TIMEZONE_OFFSET_HOURS


def now_utc() -> dt.datetime:
    """当前 UTC 时间（aware）。全项目统一用它取「现在」。"""
    return dt.datetime.now(dt.timezone.utc)


def as_aware(value: Optional[dt.datetime]) -> Optional[dt.datetime]:
    """把数据库读出的时间统一成 aware UTC。

    SQLite 返回 naive 时按 UTC 解释；PostgreSQL 已是 aware 则原样返回。
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.timezone.utc)
    return value


def local_day_start_utc(days_ago: int = 0) -> dt.datetime:
    """本地时区「今天零点」往前推 days_ago 天，对应的 UTC 时间点。

    例：本地 +8，days_ago=0 → 返回本地 00:00 的 UTC 表示（即前一天 16:00Z）。
    """
    offset = dt.timedelta(hours=APP_TIMEZONE_OFFSET_HOURS)
    local_now = now_utc() + offset
    local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    local_start -= dt.timedelta(days=days_ago)
    return local_start - offset


def local_date_str(days_ago: int = 0) -> str:
    """本地时区的日期字符串 YYYY-MM-DD。"""
    offset = dt.timedelta(hours=APP_TIMEZONE_OFFSET_HOURS)
    return (now_utc() + offset - dt.timedelta(days=days_ago)).strftime("%Y-%m-%d")


def new_id(prefix: str) -> str:
    """业务主键：前缀 + 16 位十六进制，便于日志中一眼看出实体类型。"""
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def page_bounds(total: int, page: int, size: int) -> tuple[int, int, int]:
    """返回 (limit, offset, pages)。page / size 已由路由层约束在合法区间。"""
    pages = (total + size - 1) // size if size else 0
    return size, (page - 1) * size, pages
