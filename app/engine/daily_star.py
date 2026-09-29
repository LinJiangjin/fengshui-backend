# -*- coding: utf-8 -*-
"""日家紫白 · 每日九宫飞星。

规则（全部由代码确定性计算，不交给大模型）
------------------------------------------
1. **分阴阳遁**：以冬至 / 夏至交节为界
   * 冬至后 → 夏至前：**阳遁**，入中星顺行（每日 +1）
   * 夏至后 → 冬至前：**阴遁**，入中星逆行（每日 -1）
2. **分三元**：以交节后第一个甲子日为上元之始，每 60 日一元，三元 180 日一循环
   * 阳遁：上元甲子起一白、中元甲子起四绿、下元甲子起七赤
   * 阴遁：上元甲子起九紫、中元甲子起三碧、下元甲子六白
   （两个序列都是每元 +3，只是每日行进方向相反）
3. **入中后一律按洛书轨迹顺飞九宫**（与年盘同轨），得到当日九宫星曜。

冬至 / 夏至的交节时刻属于天文历法数据，取自 ``lunar-python`` 的节气表；
未安装该库时回退到 12-21 / 06-21 的近似值（差一天最多影响 1 天的结果）。
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

try:  # pragma: no cover - 仅用于取节气交节日，缺失时走近似值
    from lunar_python import Solar
except ImportError:  # pragma: no cover
    Solar = None  # type: ignore[assignment]

from .bazi import day_pillar_from_anchor
from .constants import FLYING_ORDER, PALACE_BY_LUOSHU, STAR_INFO
from .flying_star import pick_extremes

# 日柱锚点：1900-01-01 为甲戌日（六十甲子序号 10），故甲子日为 1899-12-22
_DAY_ANCHOR_DATE = _dt.date(1900, 1, 1)
_DAY_ANCHOR_INDEX = 10
JIAZI_ANCHOR_ORD = _DAY_ANCHOR_DATE.toordinal() - _DAY_ANCHOR_INDEX

# 三元甲子日的起星（上元 / 中元 / 下元）
YANG_BASE = (1, 4, 7)  # 阳遁：一白 / 四绿 / 七赤
YIN_BASE = (9, 3, 6)   # 阴遁：九紫 / 三碧 / 六白
YUAN_NAMES = ("上元", "中元", "下元")

DONGZHI_KEYS = ("冬至", "DONG_ZHI")
XIAZHI_KEYS = ("夏至", "XIA_ZHI")
# lunar-python 缺失时的近似交节日
FALLBACK_DONGZHI = (12, 21)
FALLBACK_XIAZHI = (6, 21)

__all__ = [
    "build_daily_palaces",
    "center_star_of_date",
    "daily_chart",
    "dongzhi_of",
    "escape_of",
    "jiazi_offset",
    "resolve_date",
    "solar_term_range_of",
    "xiazhi_of",
    "yuan_of",
]


# ---------------------------------------------------------------- 节气
def _jieqi_date(year: int, keys: tuple[str, ...], fallback: tuple[int, int]) -> _dt.date:
    """取指定阳历年某个节气的交节日期。"""
    if Solar is not None:
        for probe_year in (year, year - 1, year + 1):
            try:
                table = (
                    Solar.fromYmd(probe_year, 6, 1).getLunar().getJieQiTable()
                )
            except Exception:  # pragma: no cover - 历法库异常时走兜底
                continue
            for key, solar in table.items():
                if key not in keys:
                    continue
                y, m, d = (int(x) for x in solar.toYmd().split("-"))
                if y == year:
                    return _dt.date(y, m, d)
    return _dt.date(year, fallback[0], fallback[1])


def dongzhi_of(year: int) -> _dt.date:
    """某年冬至的交节日期。"""
    return _jieqi_date(year, DONGZHI_KEYS, FALLBACK_DONGZHI)


def xiazhi_of(year: int) -> _dt.date:
    """某年夏至的交节日期。"""
    return _jieqi_date(year, XIAZHI_KEYS, FALLBACK_XIAZHI)


def solar_term_range_of(date: _dt.date) -> str:
    """当日所处节气区间，如「秋分后 · 寒露前」。"""
    if Solar is None:
        return ""
    try:
        lunar = Solar.fromYmd(date.year, date.month, date.day).getLunar()
        return f"{lunar.getPrevJieQi().getName()}后 · {lunar.getNextJieQi().getName()}前"
    except Exception:  # pragma: no cover
        return ""


# ---------------------------------------------------------------- 干支 / 三元
def jiazi_offset(date: _dt.date) -> int:
    """当日距最近一个甲子日的天数（0-59，0 即甲子日，等于六十甲子序号）。"""
    return (date.toordinal() - JIAZI_ANCHOR_ORD) % 60


def escape_of(date: _dt.date) -> dict[str, Any]:
    """判断当日属阳遁还是阴遁，并给出本段起算的交节日。

    冬至（含）之后、夏至之前为阳遁；夏至（含）之后、冬至之前为阴遁。
    1 月 1 日至当年夏至之间，属于上一年冬至开启的阳遁段。
    """
    dz = dongzhi_of(date.year)
    xz = xiazhi_of(date.year)
    if date >= dz:
        escape, boundary = "阳遁", dz
    elif date >= xz:
        escape, boundary = "阴遁", xz
    else:
        escape, boundary = "阳遁", dongzhi_of(date.year - 1)
    return {
        "escape": escape,
        "desc": "冬至后顺行" if escape == "阳遁" else "夏至后逆行",
        "boundary": boundary,
    }


def yuan_of(date: _dt.date, boundary: _dt.date) -> tuple[str, int]:
    """三元：交节后第一个甲子日起上元，每 60 日一元。

    交节日到第一个甲子日之间的零头并入上元（通书的「超神 / 接气」从简处理）。
    """
    first_jiazi = boundary.toordinal() + (JIAZI_ANCHOR_ORD - boundary.toordinal()) % 60
    delta = date.toordinal() - first_jiazi
    index = (delta // 60) % 3 if delta >= 0 else 0
    return YUAN_NAMES[index], index


# ---------------------------------------------------------------- 入中星 / 九宫
def center_star_of_date(date: _dt.date) -> int:
    """当日入中星（1-9）。"""
    esc = escape_of(date)
    _, yuan_index = yuan_of(date, esc["boundary"])
    base = (YANG_BASE if esc["escape"] == "阳遁" else YIN_BASE)[yuan_index]
    offset = jiazi_offset(date)
    if esc["escape"] == "阳遁":
        return (base - 1 + offset) % 9 + 1
    return (base - 1 - offset) % 9 + 1


def build_daily_palaces(date: _dt.date) -> list[dict[str, Any]]:
    """生成当日九宫飞星盘（结构与年盘一致，便于前端复用）。"""
    center = center_star_of_date(date)
    palaces: list[dict[str, Any]] = []
    for step, luoshu in enumerate(FLYING_ORDER):
        number = (center + step - 1) % 9 + 1
        trigram, direction = PALACE_BY_LUOSHU[luoshu]
        star = STAR_INFO[number]
        palaces.append({
            "luoshu": luoshu,
            "key": direction,
            "trigram": trigram,
            "direction": direction,
            "star": number,
            "star_name": star["name"],
            "element": star["element"],
            "level": star["level"],
            "label": star["label"],
            "note": star["note"],
            "is_center": luoshu == 5,
        })
    return palaces


def resolve_date(year: int, month: int = 0, day: int = 0) -> _dt.date:
    """把入参的月 / 日解析成日期；month / day 为 0（缺省）时取今天。"""
    today = _dt.date.today()
    m = month if 1 <= month <= 12 else today.month
    d = day if 1 <= day <= 31 else today.day
    try:
        return _dt.date(year, m, d)
    except ValueError:
        # 例如 2 月 30 日：回退到当月最后一天
        for candidate in range(d, 0, -1):
            try:
                return _dt.date(year, m, candidate)
            except ValueError:
                continue
        return _dt.date(year, m, 1)


def daily_chart(date: _dt.date) -> dict[str, Any]:
    """当日紫白盘：日柱、阴阳遁、三元、入中星、九宫与今日吉位 / 忌方。"""
    esc = escape_of(date)
    yuan_name, _ = yuan_of(date, esc["boundary"])
    center = center_star_of_date(date)
    palaces = build_daily_palaces(date)
    extremes = pick_extremes(palaces)

    return {
        "date": date.isoformat(),
        "day_pillar": day_pillar_from_anchor(date),
        "solar_term_range": solar_term_range_of(date),
        "escape": esc["escape"],
        "escape_desc": esc["desc"],
        "boundary": esc["boundary"].isoformat(),
        "yuan": yuan_name,
        "center_star": center,
        "center_star_name": STAR_INFO[center]["name"],
        "palaces": palaces,
        "best": extremes["best"],
        "worst": extremes["worst"],
    }
