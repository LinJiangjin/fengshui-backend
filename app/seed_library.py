# -*- coding: utf-8 -*-
"""方案库初始内容（seed）。

这些数据原先硬编码在 routers/library.py 里，方案库落库后改为**首次初始化**写入：

- 只在目标表为空时写入。也就是说，运营在后台删掉/改过的内容不会被重启覆盖
  （否则删掉的方案会在下次启动时复活）。
- 已有库想同步这里的文案，请直接改数据库（走后台），不要指望改这个文件。

新增初始方案时，把它追加到 SEED_SCHEMES 末尾并给一个递增的 sort_order 即可；
对已经初始化的库不会生效——那是给全新环境用的。
"""

from sqlalchemy.orm import Session

from .models import ElementNote, Scheme

# 五行相生序，同时也是展示顺序
ELEMENT_ORDER = {"木": 1, "火": 2, "土": 3, "金": 4, "水": 5}

# (五行, 宜, 忌, 排序)
SEED_ELEMENT_NOTES = [
    (
        "木",
        "木主生发，宜原木、棉麻、绿植着色，配色取青绿与浅木",
        "忌大面积金属镜面与冷白光，压抑生发之气",
        1,
    ),
    (
        "火",
        "火主炎上，宜暖光、布艺与木饰面，配色取米白与浅赭",
        "忌大面积纯黑与镜面堆叠，压住火气反而显闷",
        2,
    ),
    (
        "土",
        "土主承载，宜微水泥、陶土、棉麻等哑光材质，配色取米黄棕",
        "忌大面积高饱和色与亮面瓷砖，破坏沉静感",
        3,
    ),
    (
        "金",
        "金主收敛，宜黄铜、玻璃、大理石等冷调亮面，配色取白金灰",
        "忌过多绿植与木质堆叠，与金属调性相冲",
        4,
    ),
    (
        "水",
        "水主润下，宜深色哑光、垂坠织物与曲线家具，配色取墨蓝与灰",
        "忌大面积明黄与尖锐造型，扰动沉静的水气",
        5,
    ),
]

# 4 条初始方案。id 沿用老版本的 slug，保证已分享出去的链接仍然有效。
SEED_SCHEMES = [
    {
        "id": "ink-zen",
        "title": "新中式 · 水墨禅意",
        "subtitle": "五行属木 · 96㎡",
        "tag": "新中式",
        "element": "木",
        "area": 96,
        "from_color": "#D9D3C4",
        "to_color": "#7C6B52",
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
        "from_color": "#E8E3D8",
        "to_color": "#A79C88",
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
        "from_color": "#E4DCCB",
        "to_color": "#C0A97E",
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
        "from_color": "#2A3B35",
        "to_color": "#BE9351",
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


def seed_library(db: Session) -> tuple[int, int]:
    """表为空时写入初始方案与五行解读，返回 (写入方案数, 写入解读数)。

    幂等：两边都只在对应表「一条都没有」时才写，重启不会覆盖运营的改动。
    """
    created_schemes = 0
    created_notes = 0

    if db.query(Scheme.id).first() is None:
        for index, item in enumerate(SEED_SCHEMES, start=1):
            db.add(Scheme(sort_order=index, **item))
        created_schemes = len(SEED_SCHEMES)

    if db.query(ElementNote.element).first() is None:
        for element, fit, avoid, order in SEED_ELEMENT_NOTES:
            db.add(
                ElementNote(element=element, fit=fit, avoid=avoid, sort_order=order)
            )
        created_notes = len(SEED_ELEMENT_NOTES)

    if created_schemes or created_notes:
        db.commit()

    return created_schemes, created_notes
