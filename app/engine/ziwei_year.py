# -*- coding: utf-8 -*-
"""紫微流年：逐年给出「重点在哪、宜动宜守」的倾向性提示。

能做什么 / 不做什么
--------------------
* **能**：某一年太岁落在哪一宫（事务焦点）、流年四化引动了哪些宫、
  十二太岁星的吉凶分布，以及在此基础上「宜主动 / 宜守成」的倾向判断。
* **不做**：不预测「某年结婚 / 升职 / 生病」这类具体事件 —— 命理给的是
  倾向而非必然，且流派分歧大；文案一律保持中性，尤其涉及健康只作提醒。

规则（与排盘层同一套来源）
--------------------------
* 流年干支：``(year - 4) % 60``（1984 甲子年为基准）。
* 太岁宫：流年地支所在的本命宫位；**岁破（大耗）必在太岁对宫**。
* 十二太岁星：自太岁宫起顺行 —— 岁建、晦气、丧门、贯索、官符、小耗、
  大耗、龙德、白虎、天德、吊客、病符（大耗落在第 6 位即正好对宫，可自洽校验）。
* 流年四化：按流年天干起四化，星曜落在本命哪一宫，即为当年被「引动」的宫。
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from .constants import EARTHLY_BRANCHES, HEAVENLY_STEMS
from .ziwei import SI_HUA, ZIWEI_PALACES

__all__ = ["build_ziwei_years", "gan_zhi_of_year"]

# 十二太岁星：自太岁宫起顺行；大耗（岁破）落在第 6 位 = 太岁对宫
TAI_SUI_STARS = [
    "岁建", "晦气", "丧门", "贯索", "官符", "小耗",
    "大耗", "龙德", "白虎", "天德", "吊客", "病符",
]

# 文案一律中性：只说「宜注意 / 宜留白 / 宜提前」，不做事件断言
TAI_SUI_TEXT = {
    "岁建": "太岁当头，此宫事务被放大，一举一动更受关注。",
    "晦气": "易有闷滞感，做事别急，沟通上多一分耐心。",
    "丧门": "情绪易低落，重大决定宜缓，多与亲近的人相处。",
    "贯索": "易有牵绊与被卡住的感觉，合约、款项宜提前理清。",
    "官符": "文书、规章、与官方打交道的事增多，务必留痕。",
    "小耗": "易有小额或预算外支出，宜提前预留余地。",
    "大耗": "岁破之位，宜守不宜攻，重大投入放慢一步。",
    "龙德": "贵人运强，遇事有人搭手，适合主动争取。",
    "白虎": "宜防磕碰与突发状况，行车运动多留意，作息保持规律。",
    "天德": "有化解之力，适合修复关系、了结旧账。",
    "吊客": "人情往来增多，情绪与行程都宜留白。",
    "病符": "健康上易有小毛病，宜规律作息、按时体检。",
}

# 只提示这几颗关键的，避免一年塞满十二颗星
KEY_TAI_SUI = ["大耗", "龙德", "白虎", "天德", "官符", "病符"]

# 宫位 -> 生活领域
PALACE_FIELD = {
    "命宫": "自我", "兄弟": "合作", "夫妻": "感情", "子女": "创作",
    "财帛": "财运", "疾厄": "健康", "迁移": "环境", "交友": "人脉",
    "官禄": "事业", "田宅": "家庭", "福德": "内心", "父母": "长辈",
}

# 宫位 -> 一句话含义
PALACE_TOPIC = {
    "命宫": "整体状态与自我定位",
    "兄弟": "同辈、合伙与资金往来",
    "夫妻": "感情与亲密关系",
    "子女": "子女、创作与产出",
    "财帛": "收入方式与理财",
    "疾厄": "身体与作息",
    "迁移": "外出、环境与外部机会",
    "交友": "人脉、同事与下属",
    "官禄": "事业与职场发展",
    "田宅": "家庭与居住、不动产",
    "福德": "内心状态与精神生活",
    "父母": "长辈、文书与上级关系",
}

YEAR_SI_HUA_TEXT = {
    "化禄": "{star}化禄入{palace}：这一年此处有资源与机会，值得投入。",
    "化权": "{star}化权入{palace}：此处需要你主导，主动推进比等待有效。",
    "化科": "{star}化科入{palace}：名声与贵人加分，遇到阻力容易有人解围。",
    "化忌": "{star}化忌入{palace}：此处是今年的关口，宜稳不宜冒进，先把风险兜住。",
}


def gan_zhi_of_year(year: int) -> str:
    """公历年 -> 干支（甲子年为 0，1984 甲子）。"""
    idx = (year - 4) % 60
    return HEAVENLY_STEMS[idx % 10] + EARTHLY_BRANCHES[idx % 12]


def _index_of_zhi(chart: dict[str, Any], zhi: str) -> int:
    for i, palace in enumerate(chart["palaces"]):
        if palace["zhi"] == zhi:
            return i
    raise ValueError(f"命盘中找不到地支：{zhi}")


def build_ziwei_years(
    chart: dict[str, Any],
    birth_year: int,
    start_year: int | None = None,
    count: int = 10,
) -> list[dict[str, Any]]:
    """在本命盘上逐年推流年，给出每一年的重点与宜忌倾向。

    Args:
        chart: :func:`app.engine.ziwei.build_ziwei` 的命盘。
        birth_year: 出生公历年（用于算当年周岁与所属大限）。
        start_year: 起始年份，默认取今年。
        count: 推几年，默认 10 年。

    Returns:
        逐年列表，可直接序列化。
    """
    palaces = chart["palaces"]
    ju_number = chart["basic"]["ju_number"]
    forward = chart["basic"]["da_xian_forward"]

    # 星曜 -> 本命所在宫（流年四化靠它定位被「引动」的宫）
    star_to_palace: dict[str, str] = {}
    for palace in palaces:
        for star in palace["main"] + palace["aux"]:
            star_to_palace.setdefault(star, palace["name"])

    first_year = start_year or _dt.date.today().year
    years = []

    for year in range(first_year, first_year + count):
        gan_zhi = gan_zhi_of_year(year)
        gan, zhi = gan_zhi[0], gan_zhi[1]
        age = year - birth_year

        # 1) 太岁宫与岁破宫
        tai_idx = _index_of_zhi(chart, zhi)
        tai_palace = palaces[tai_idx]
        po_idx = (tai_idx + 6) % 12
        po_palace = palaces[po_idx]

        # 2) 当年所属大限（与排盘层同一套顺逆规则）
        k = 0
        if age >= ju_number:
            k = min((age - ju_number) // 10, 11)
        da_xian_palace = palaces[(-k) % 12] if forward else palaces[k]

        # 3) 流年四化：按流年天干，星曜落在本命哪一宫
        si_hua = []
        for hua, star in SI_HUA[gan].items():
            palace = star_to_palace.get(star)
            if palace is None:
                continue
            si_hua.append({"star": star, "hua": hua, "palace": palace})

        # 4) 十二太岁星（自太岁宫顺行）中的关键几颗
        star_slots = {
            TAI_SUI_STARS[j]: palaces[(tai_idx + j) % 12]
            for j in range(12)
        }
        key_stars = [
            {"star": name, "palace": star_slots[name]["name"]}
            for name in KEY_TAI_SUI
        ]

        # 5) 组织文案
        points = [
            f"{year} {gan_zhi}年：太岁落在{tai_palace['name']}，"
            f"全年事务围绕「{PALACE_TOPIC.get(tai_palace['name'], tai_palace['name'])}」展开。",
        ]
        for item in si_hua:
            if item["hua"] in YEAR_SI_HUA_TEXT:
                points.append(
                    YEAR_SI_HUA_TEXT[item["hua"]].format(
                        star=item["star"], palace=item["palace"]
                    )
                )
        for item in key_stars:
            points.append(
                f"{item['star']}在{item['palace']}：{TAI_SUI_TEXT[item['star']]}"
            )

        # 6) 重点领域：太岁宫为主，叠加化禄 / 化忌所在宫
        focus_fields = [PALACE_FIELD.get(tai_palace["name"], "")]
        for item in si_hua:
            if item["hua"] in ("化禄", "化忌"):
                field = PALACE_FIELD.get(item["palace"], "")
                if field and field not in focus_fields:
                    focus_fields.append(field)
        focus = " · ".join([f for f in focus_fields if f]) or "整体"

        # 7) 宜动 / 宜守：化忌或岁破压在太岁宫上宜守，化禄或吉星照太岁宜动
        tai_name = tai_palace["name"]
        hua_at_tai = {i["hua"] for i in si_hua if i["palace"] == tai_name}
        auspicious_at_tai = any(
            item["star"] in ("龙德", "天德") and item["palace"] == tai_name
            for item in key_stars
        )
        if "化忌" in hua_at_tai or "大耗" in {s["star"] for s in key_stars
                                             if s["palace"] == tai_name}:
            stance = "宜守成"
        elif "化禄" in hua_at_tai or auspicious_at_tai:
            stance = "宜主动"
        else:
            stance = "稳中求进"

        years.append(
            {
                "year": year,
                "gan_zhi": gan_zhi,
                "age": age,
                "da_xian": {
                    "palace": da_xian_palace["name"],
                    "from": da_xian_palace["da_xian"]["from"],
                    "to": da_xian_palace["da_xian"]["to"],
                },
                "tai_sui": {
                    "palace": tai_palace["name"],
                    "zhi": zhi,
                    "topic": PALACE_TOPIC.get(tai_palace["name"], ""),
                },
                "po": {"palace": po_palace["name"], "zhi": po_palace["zhi"]},
                "si_hua": si_hua,
                "stars": key_stars,
                "focus": focus,
                "stance": stance,
                "points": points,
            }
        )

    return years
