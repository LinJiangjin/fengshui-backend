# -*- coding: utf-8 -*-
"""装修方案库路由。

方案与配色属于运营内容，放在服务端便于随时更新；
「本月五行配色」按当前月份推算，不再写死在客户端。

数据量很小（个位数方案），列表接口直接下发完整详情，
客户端点卡片即用本地数据渲染详情页，不再多发一次请求。
后续方案数量上来了，再把详情字段拆到 /library/{id}。
"""

import datetime as dt

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1", tags=["library"])


def ok(data):
    return {"code": 0, "status": "ok", "data": data}


# ---------------------------------------------------------------- 运营内容
FILTERS = ["全部", "新中式", "日式侘寂", "现代原木"]

# 五行属性解读：详情页的「宜 / 忌」，按方案所属五行复用，不逐条重复写
ELEMENT_NOTE = {
    "木": {
        "fit": "木主生发，宜原木、棉麻、绿植着色，配色取青绿与浅木",
        "avoid": "忌大面积金属镜面与冷白光，压抑生发之气",
    },
    "土": {
        "fit": "土主承载，宜微水泥、陶土、棉麻等哑光材质，配色取米黄棕",
        "avoid": "忌大面积高饱和色与亮面瓷砖，破坏沉静感",
    },
    "金": {
        "fit": "金主收敛，宜黄铜、玻璃、大理石等冷调亮面，配色取白金灰",
        "avoid": "忌过多绿植与木质堆叠，与金属调性相冲",
    },
}

# 面积区间筛选；max = 0 表示不设上限
AREA_RANGES = [
    {"label": "不限", "min": 0, "max": 0},
    {"label": "90㎡以下", "min": 0, "max": 90},
    {"label": "90-120㎡", "min": 90, "max": 120},
    {"label": "120㎡以上", "min": 120, "max": 0},
]

SCHEMES = [
    {
        "id": "ink-zen",
        "title": "新中式 · 水墨禅意",
        "subtitle": "五行属木 · 96㎡",
        "tag": "新中式",
        "element": "木",
        "area": 96,
        "from": "#D9D3C4",
        "to": "#7C6B52",
        "summary": "以宣纸白铺底、墨色压住重心，木色作骨架。留白多、进深浅，"
                   "适合采光一般的紧凑户型。",
        "highlights": [
            "客厅通铺浅色原木地板，视觉上拉长进深",
            "玄关以水墨山水立屏作端景，挡煞又聚气",
            "家具选细腿款，地面通透不压层高",
            "主灯位改隐藏灯带，光从顶上漫下来",
        ],
        "colors": [
            {"name": "宣纸白", "hex": "#F5F1E8"},
            {"name": "浅木", "hex": "#C9A57A"},
            {"name": "灰陶", "hex": "#A79C88"},
            {"name": "墨玉", "hex": "#24352F"},
        ],
        "rooms": [
            {"name": "客厅", "hex": "#D9D3C4",
             "note": "墙面宣纸白，原木地板通铺，沙发选灰陶色布艺"},
            {"name": "主卧", "hex": "#C9A57A",
             "note": "床头背墙浅木护墙板，床品用月白棉麻"},
            {"name": "书房", "hex": "#7C6B52",
             "note": "一张深木书桌定调，配一盆文竹"},
            {"name": "玄关", "hex": "#24352F",
             "note": "水墨立屏作端景，鞋柜下沉式收口"},
        ],
    },
    {
        "id": "wabi-sabi",
        "title": "日式侘寂 · 素白原木",
        "subtitle": "五行属土 · 88㎡",
        "tag": "日式侘寂",
        "element": "土",
        "area": 88,
        "from": "#E8E3D8",
        "to": "#A79C88",
        "summary": "素色微水泥肌理墙打底，原木与手工陶器补充温度。弱化线条与装饰，"
                   "适合独居或二人小户型。",
        "highlights": [
            "全屋微水泥墙地一体，接缝少、观感整",
            "家具只用原木，低矮款压低视线重心",
            "手工陶器与干枝作陈设，刻意留出不完美",
            "窗帘用亚麻本色，遮光而不遮光感",
        ],
        "colors": [
            {"name": "素白", "hex": "#E8E3D8"},
            {"name": "燕麦", "hex": "#D9CDB4"},
            {"name": "原木", "hex": "#C0A97E"},
            {"name": "灰陶", "hex": "#8C8577"},
        ],
        "rooms": [
            {"name": "客厅", "hex": "#E8E3D8",
             "note": "素白微水泥墙，原木矮柜，亚麻沙发"},
            {"name": "卧室", "hex": "#D9CDB4",
             "note": "燕麦色床品，无主灯，纸质落地灯作夜灯"},
            {"name": "餐厨", "hex": "#C0A97E",
             "note": "原木餐桌配手作陶器，开放式厨房"},
            {"name": "卫浴", "hex": "#8C8577",
             "note": "灰陶色微水泥，木质格栅分隔干湿"},
        ],
    },
    {
        "id": "natural-light",
        "title": "现代原木 · 自然光宅",
        "subtitle": "五行属木 · 110㎡",
        "tag": "现代原木",
        "element": "木",
        "area": 110,
        "from": "#E4DCCB",
        "to": "#C0A97E",
        "summary": "把南向采光当成主材料：大面积落地窗 + 白色基底 + 原木点缀，"
                   "适合采光良好的三房。",
        "highlights": [
            "客厅与阳台打通，光线直达餐厅",
            "墙面只做白色乳胶漆，不做造型压低层高",
            "原木只落在地板、餐边柜与门套三处呼应",
            "取消主灯，改用轨道灯与灯带",
        ],
        "colors": [
            {"name": "珍珠白", "hex": "#F2F0EA"},
            {"name": "浅橡木", "hex": "#D9C6A5"},
            {"name": "原木", "hex": "#B8895A"},
            {"name": "石墨灰", "hex": "#4A4E4A"},
        ],
        "rooms": [
            {"name": "客厅", "hex": "#F2F0EA",
             "note": "白色墙面留空，浅橡木地板引光到中段"},
            {"name": "餐厨", "hex": "#D9C6A5",
             "note": "餐边柜浅橡木，岛台面向窗户"},
            {"name": "主卧", "hex": "#B8895A",
             "note": "原木床架，床头留白给窗外景色"},
            {"name": "儿童房", "hex": "#4A4E4A",
             "note": "石墨灰黑板墙，其余留白可随年龄改"},
        ],
    },
    {
        "id": "oriental-luxe",
        "title": "轻奢东方 · 墨玉金线",
        "subtitle": "五行属金 · 128㎡",
        "tag": "新中式",
        "element": "金",
        "area": 128,
        "from": "#2A3B35",
        "to": "#BE9351",
        "summary": "深墨玉色打底，黄铜细线收边，靠材质而非装饰做奢华感，"
                   "适合采光充足的大平层。",
        "highlights": [
            "玄关到客厅一条黄铜嵌条贯穿，串起空间",
            "电视墙用墨玉色岩板，细金线收口",
            "餐边柜做黄铜框架玻璃门，藏露结合",
            "全屋灯光 3000K 暖白，金属才不显冷硬",
        ],
        "colors": [
            {"name": "墨玉", "hex": "#24352F"},
            {"name": "黄铜", "hex": "#BE9351"},
            {"name": "珍珠白", "hex": "#F2F0EA"},
            {"name": "烟灰", "hex": "#5C5F63"},
        ],
        "rooms": [
            {"name": "客厅", "hex": "#24352F",
             "note": "墨玉岩板电视墙，黄铜嵌条收边"},
            {"name": "餐厨", "hex": "#BE9351",
             "note": "餐边柜黄铜玻璃门，大理石餐桌"},
            {"name": "主卧", "hex": "#F2F0EA",
             "note": "珍珠白墙面，床头一对金属壁灯"},
            {"name": "玄关", "hex": "#5C5F63",
             "note": "烟灰色地砖 + 黄铜门套，进门即定调"},
        ],
    },
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


def _scheme_out(s: dict) -> dict:
    """补上按五行复用的宜忌解读，客户端拿到即用。"""
    out = dict(s)
    out["element_note"] = ELEMENT_NOTE.get(
        s.get("element", ""), {"fit": "", "avoid": ""}
    )
    return out


@router.get("/library")
def library(month: int = 0):
    """装修方案库 + 本月五行配色。month=0 表示当前月。"""
    today = dt.date.today()
    m = month if 1 <= month <= 12 else today.month
    schemes = [_scheme_out(s) for s in SCHEMES]
    # 五行筛选项按实际数据去重，新增方案时不用再手改这个列表
    elements = list(dict.fromkeys(s["element"] for s in schemes))
    return ok({
        "filters": FILTERS,
        "elements": elements,
        "area_ranges": AREA_RANGES,
        "schemes": schemes,
        "palette": monthly_palette(m),
        "rules_version": "2026.2",
    })


@router.get("/library/{scheme_id}")
def library_detail(scheme_id: str):
    """单条方案详情。

    客户端目前直接用列表接口返回的完整数据渲染详情页，这里是给分享链接 /
    后续方案变多时的备用入口。
    """
    for s in SCHEMES:
        if s["id"] == scheme_id:
            return ok(_scheme_out(s))
    raise HTTPException(status_code=404, detail="方案不存在")
