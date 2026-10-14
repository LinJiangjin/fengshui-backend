# -*- coding: utf-8 -*-
"""装修方案库路由（App 端只读）。

方案与五行宜忌解读都是**运营内容**，已落库到 schemes / element_notes 两张表，
由管理后台 /api/v1/admin/schemes 维护——运营换文案不必再改代码发版。

本模块只保留两类东西：
1. 读库 + 组装成 App 需要的形状；
2. 「本月五行配色」的推算规则（按月份定当令五行，属算法而非内容，不入库）。

数据量很小（个位数方案），列表接口直接下发完整详情，
客户端点卡片即用本地数据渲染详情页，不再多发一次请求。
"""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ElementNote, Scheme

router = APIRouter(prefix="/api/v1", tags=["library"])


def ok(data):
    return {"code": 0, "status": "ok", "data": data}


ALL_FILTER = "全部"
RULES_VERSION = "2026.3"

# 面积区间筛选；max = 0 表示不设上限。
# 这几档是固定的交互口径而非内容，因此留在代码里，不入库。
AREA_RANGES = [
    {"label": "不限", "min": 0, "max": 0},
    {"label": "90㎡以下", "min": 0, "max": 90},
    {"label": "90-120㎡", "min": 90, "max": 120},
    {"label": "120㎡以上", "min": 120, "max": 0},
]

# 基础色板（设计资产，色值固定，但「本月主打哪一组」由月份决定）
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


def _element_notes(db: Session) -> dict[str, ElementNote]:
    """一次取全五行解读，供逐条方案复用，避免 N+1 查询。"""
    return {note.element: note for note in db.query(ElementNote).all()}


def _scheme_out(scheme: Scheme, notes: dict[str, ElementNote]) -> dict:
    """把库里的行组装成 App 期望的形状。

    注意色值键名要做一次映射：库里叫 from_color / to_color（from 是 Python
    关键字，不能作列名），而 App 端模型读的是 from / to。
    """
    note = notes.get(scheme.element)
    return {
        "id": scheme.id,
        "title": scheme.title,
        "subtitle": scheme.subtitle,
        "tag": scheme.tag,
        "element": scheme.element,
        "area": scheme.area,
        "from": scheme.from_color,
        "to": scheme.to_color,
        "summary": scheme.summary,
        "highlights": list(scheme.highlights or []),
        "colors": list(scheme.colors or []),
        "rooms": list(scheme.rooms or []),
        "element_note": {
            "fit": note.fit if note else "",
            "avoid": note.avoid if note else "",
        },
    }


@router.get("/library")
def library(month: int = 0, db: Session = Depends(get_db)):
    """装修方案库 + 本月五行配色。month=0 表示当前月。"""
    today = dt.date.today()
    m = month if 1 <= month <= 12 else today.month

    notes = _element_notes(db)
    rows = (
        db.query(Scheme)
        .filter(Scheme.published.is_(True))
        .order_by(Scheme.sort_order.asc(), Scheme.id.asc())
        .all()
    )
    schemes = [_scheme_out(row, notes) for row in rows]

    # 风格 chips 与五行筛选项都按实际在架方案推导，新增方案时不必再手改常量
    tags = list(dict.fromkeys(s["tag"] for s in schemes if s["tag"]))
    elements = list(dict.fromkeys(s["element"] for s in schemes if s["element"]))

    return ok({
        "filters": [ALL_FILTER, *tags],
        "elements": elements,
        "area_ranges": AREA_RANGES,
        "schemes": schemes,
        "palette": monthly_palette(m),
        "rules_version": RULES_VERSION,
    })


@router.get("/library/{scheme_id}")
def library_detail(scheme_id: str, db: Session = Depends(get_db)):
    """单条方案详情。

    客户端目前直接用列表接口返回的完整数据渲染详情页，这里是给分享链接 /
    后续方案变多时的备用入口。已下架的方案对外等同于不存在。
    """
    scheme = db.get(Scheme, scheme_id)
    if scheme is None or not scheme.published:
        raise HTTPException(status_code=404, detail="方案不存在")
    return ok(_scheme_out(scheme, _element_notes(db)))
