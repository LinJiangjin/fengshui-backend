# -*- coding: utf-8 -*-
"""装修方案库路由。

方案与配色属于运营内容，放在服务端便于随时更新；
「本月五行配色」按当前月份推算，不再写死在客户端。
"""

import datetime as dt

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["library"])


def ok(data):
    return {"code": 0, "status": "ok", "data": data}


# ---------------------------------------------------------------- 运营内容
FILTERS = ["全部", "新中式", "日式侘寂", "现代原木"]

SCHEMES = [
    {"title": "新中式 · 水墨禅意", "subtitle": "五行属木 · 96㎡",
     "from": "#D9D3C4", "to": "#7C6B52", "tag": "新中式"},
    {"title": "日式侘寂 · 素白原木", "subtitle": "五行属土 · 88㎡",
     "from": "#E8E3D8", "to": "#A79C88", "tag": "日式侘寂"},
    {"title": "现代原木 · 自然光宅", "subtitle": "五行属木 · 110㎡",
     "from": "#E4DCCB", "to": "#C0A97E", "tag": "现代原木"},
    {"title": "轻奢东方 · 墨玉金线", "subtitle": "五行属金 · 128㎡",
     "from": "#2A3B35", "to": "#BE9351", "tag": "新中式"},
]

# 基础色板（设计资产，配色名称与色值固定，但「本月主打哪一组」由月份决定）
PALETTE = [
    {"name": "墨玉", "hex": "#24352F"},
    {"name": "松绿", "hex": "#3F7A5E"},
    {"name": "宣纸", "hex": "#F5F1E8"},
    {"name": "原木", "hex": "#C9A57A"},
    {"name": "黄铜", "hex": "#BE9351"},
]

# 月份 -> 当令五行（春木、夏火、秋金、冬水）
MONTH_ELEMENT = {
    1: "水", 2: "木", 3: "木", 4: "木",
    5: "火", 6: "火", 7: "火",
    8: "金", 9: "金", 10: "金",
    11: "水", 12: "水",
}

# 五行相生：本月的当令五行生出的下一五行
GENERATES = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}

# 当令五行对应的调性建议
TONE_BY_ELEMENT = {
    "木": "自然草木调",
    "火": "明快暖调",
    "土": "沉稳大地色",
    "金": "冷冽金属调",
    "水": "清冷澄澈调",
}


def monthly_palette(month: int) -> dict:
    """按月份推算本月五行配色主题。"""
    cur = MONTH_ELEMENT.get(month, "木")
    nxt = GENERATES.get(cur, "火")
    tone = TONE_BY_ELEMENT.get(cur, "自然草木调")
    return {
        "month": month,
        "element": cur,
        "title": f"{month}月五行配色推荐",
        "subtitle": f"{cur}{nxt}相生 · 宜{tone}",
        "colors": PALETTE,
        "names": " · ".join(c["name"] for c in PALETTE),
    }


@router.get("/library")
def library(month: int = 0):
    """装修方案库 + 本月五行配色。month=0 表示当前月。"""
    today = dt.date.today()
    m = month if 1 <= month <= 12 else today.month
    return ok({
        "filters": FILTERS,
        "schemes": SCHEMES,
        "palette": monthly_palette(m),
        "rules_version": "2026.1",
    })
