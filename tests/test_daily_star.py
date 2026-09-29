# -*- coding: utf-8 -*-
"""日家紫白（每日九宫飞星）单元测试。"""

import datetime as dt

import pytest

from app.engine.daily_star import (
    build_daily_palaces,
    center_star_of_date,
    daily_chart,
    dongzhi_of,
    escape_of,
    jiazi_offset,
    resolve_date,
    xiazhi_of,
    yuan_of,
)

# 六个甲子日样本：阳遁 上/中/下元 -> 一白/四绿/七赤；阴遁 -> 九紫/三碧/六白
JIAZI_CASES = [
    (dt.date(2026, 2, 19), "阳遁", "中元", 4),
    (dt.date(2026, 4, 20), "阳遁", "下元", 7),
    (dt.date(2026, 6, 19), "阳遁", "上元", 1),
    (dt.date(2026, 8, 18), "阴遁", "上元", 9),
    (dt.date(2026, 10, 17), "阴遁", "中元", 3),
    (dt.date(2026, 12, 16), "阴遁", "下元", 6),
]


@pytest.mark.parametrize("day, escape, yuan, star", JIAZI_CASES)
def test_jiazi_day_center_star(day, escape, yuan, star):
    """甲子日的三元起星严格对应传统口诀。"""
    assert jiazi_offset(day) == 0
    esc = escape_of(day)
    assert esc["escape"] == escape
    assert yuan_of(day, esc["boundary"])[0] == yuan
    assert center_star_of_date(day) == star


def test_escape_switches_on_terms():
    """冬至当日转阳遁、夏至当日转阴遁。"""
    assert escape_of(dongzhi_of(2026))["escape"] == "阳遁"
    assert escape_of(xiazhi_of(2026))["escape"] == "阴遁"
    # 冬至前一天仍属阴遁段
    assert escape_of(dongzhi_of(2026) - dt.timedelta(days=1))["escape"] == "阴遁"


def test_daily_star_steps_by_one():
    """同一元内，阳遁逐日 +1、阴遁逐日 -1（九循环）。"""
    start = dt.date(2026, 9, 1)
    prev = center_star_of_date(start)
    for i in range(1, 30):
        day = start + dt.timedelta(days=i)
        esc = escape_of(day)
        if esc["escape"] == "阳遁" and yuan_of(day, esc["boundary"])[1] == 0 \
                and yuan_of(start + dt.timedelta(days=i - 1), esc["boundary"])[1] == 0:
            expect = prev % 9 + 1
        elif esc["escape"] == "阴遁":
            expect = (prev - 2) % 9 + 1
        else:
            prev = center_star_of_date(day)
            continue
        assert center_star_of_date(day) == expect
        prev = center_star_of_date(day)


def test_daily_palaces_shape():
    """日盘结构与年盘一致：九宫、中宫星即入中星。"""
    day = dt.date(2026, 9, 29)
    palaces = build_daily_palaces(day)
    assert len(palaces) == 9
    center = center_star_of_date(day)
    middle = next(p for p in palaces if p["is_center"])
    assert middle["star"] == center
    assert sum(1 for p in palaces if p["is_center"]) == 1


def test_daily_chart_changes_by_day():
    """今日吉位 / 忌方随日期变化，且两者不会是同一方位。"""
    start = dt.date(2026, 9, 25)
    best_set, worst_set = set(), set()
    for i in range(30):
        chart = daily_chart(start + dt.timedelta(days=i))
        assert chart["best"]["direction"] != chart["worst"]["direction"]
        best_set.add(chart["best"]["title"])
        worst_set.add(chart["worst"]["title"])
    assert len(best_set) > 1 and len(worst_set) > 1


def test_daily_chart_fields():
    chart = daily_chart(dt.date(2026, 9, 29))
    assert chart["date"] == "2026-09-29"
    assert chart["day_pillar"] == "丙午"
    assert chart["escape"] in ("阳遁", "阴遁")
    assert chart["yuan"] in ("上元", "中元", "下元")
    assert 1 <= chart["center_star"] <= 9
    assert chart["center_star_name"]


def test_resolve_date_defaults_to_today():
    today = dt.date.today()
    assert resolve_date(today.year) == today
    assert resolve_date(2026, 9, 29) == dt.date(2026, 9, 29)
    # 非法日期回退到当月最后一天
    assert resolve_date(2026, 2, 30) == dt.date(2026, 2, 28)
