# -*- coding: utf-8 -*-
"""lunar-python 的 LunarYear 多年份缓存补丁。

背景
----
``lunar_python.LunarYear.fromYear`` 自带缓存，但**只有单槽**
（类属性 ``__CACHE_YEAR``，见 LunarYear.py:23）。黄历一次查询需要同时用到
多个年份的历法表：节气探测要 (year-1, year, year+1)，农历年与公历年在春节
前后还会错位。单槽缓存因此在年份之间反复失效——实测推一份单日通书要重建
53 次 ``LunarYear``，每次建表都跑上万次天文计算（``eLon`` 被调 2 万余次），
单日耗时约 90ms；一次 30 天择日扫描因此要 2.5 秒。

``LunarYear`` 在 ``compute()`` 之后是只读的（已核对：私有字段仅在
``__init__`` / ``compute`` 中赋值，库内无任何外部写入），库自身也长期复用
同一实例，所以按年份做多槽缓存是安全的。补丁后单日通书降到个位数毫秒，
且因缓存命中，输出与打补丁前逐字段一致（测试里做了对照）。

兼容性
------
若后续版本移除 / 改名 ``fromYear``，``install()`` 返回 False 并静默跳过——
功能不受影响，只是退回原来的速度。不要在业务代码里依赖 ``INSTALLED``。
"""

from __future__ import annotations

import functools
import os

# 调试用开关：置 1 可关闭补丁，用于和打补丁后的输出做逐字段对照排查。
_DISABLE_ENV = "FENGSHUI_DISABLE_LUNAR_CACHE"

# 缓存年份数上限。黄历实际只会在当前年前后几年内取值，64 槽足够覆盖；
# 设上限是为了避免长期运行的无界增长（每次建表结果含 15 个月序 + 节气表）。
_MAX_YEARS = 64


def install() -> bool:
    """给 LunarYear.fromYear 装多年份缓存；已装或装不上时返回是否可用。"""
    if os.environ.get(_DISABLE_ENV) == "1":  # pragma: no cover - 仅调试用
        return False

    try:
        from lunar_python.LunarYear import LunarYear
    except Exception:  # pragma: no cover - 未安装 lunar-python
        return False

    if getattr(LunarYear, "_fengshui_year_cache", False):
        return True

    original = getattr(LunarYear, "fromYear", None)
    if not callable(original):
        return False

    @functools.lru_cache(maxsize=_MAX_YEARS)
    def cached_from_year(lunar_year):
        return original(lunar_year)

    try:
        LunarYear.fromYear = staticmethod(cached_from_year)
    except Exception:  # pragma: no cover - 类不可写（极少见）
        return False

    LunarYear._fengshui_year_cache = True
    return True


INSTALLED = install()
