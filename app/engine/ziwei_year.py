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
from .ziwei import PALACE_PLAIN, SI_HUA, ZIWEI_PALACES

__all__ = ["build_ziwei_years", "gan_zhi_of_year"]

# 十二太岁星：自太岁宫起顺行；大耗（岁破）落在第 6 位 = 太岁对宫
TAI_SUI_STARS = [
    "岁建", "晦气", "丧门", "贯索", "官符", "小耗",
    "大耗", "龙德", "白虎", "天德", "吊客", "病符",
]

# 文案一律中性：只说「宜注意 / 宜留白 / 宜提前」，不做事件断言
TAI_SUI_TEXT = {
    "岁建": "它就是今年太岁所在的那一宫，相关的事会被放大，一举一动更受关注。",
    "晦气": "易有闷滞感，做事别急，沟通上多一分耐心。",
    "丧门": "情绪易低落，重大决定宜缓，多与亲近的人相处。",
    "贯索": "易有牵绊、被卡住的感觉，合约与款项宜提前理清。",
    "官符": "与文书、规章、官方打交道的事增多，务必留痕。",
    "小耗": "易有小额或预算外支出，宜提前预留余地。",
    "大耗": "这是「岁破」的位置（正对着太岁），宜守不宜攻，重大投入放慢一步。",
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

# 宫位白话（「这一宫管什么」）与排盘层共用同一份 PALACE_PLAIN，不在这里另建一份

YEAR_SI_HUA_TEXT = {
    "化禄": "{star}星今年「化禄」——「禄」代表机会与资源——落到{palace}："
            "这一年这一块值得主动投入。",
    "化权": "{star}星今年「化权」——「权」代表主导与掌控——落到{palace}："
            "这一年这一块得你自己拿主意推，主动比等待有效。",
    "化科": "{star}星今年「化科」——「科」代表名声与贵人——落到{palace}："
            "这一年这一块更容易被认可，卡住时有人出面。",
    "化忌": "{star}星今年「化忌」——「忌」代表反复与牵挂——落到{palace}："
            "这一年这一块是关口，宜稳不宜冒进，先把风险兜住。",
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

        # 5) 组织文案（一律先给白话解释，再给结论）
        points = [
            f"{year} {gan_zhi}年：这一年的「太岁」落在{tai_palace['name']}宫——"
            f"太岁就是当年当值的那一宫，代表今年事情最集中的地方，"
            f"也就是「{PALACE_PLAIN.get(tai_palace['name'], tai_palace['name'])}」。",
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
                f"{item['star']}星落在{item['palace']}宫："
                f"{TAI_SUI_TEXT[item['star']]}"
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
                    "topic": PALACE_PLAIN.get(tai_palace["name"], ""),
                },
                "po": {"palace": po_palace["name"], "zhi": po_palace["zhi"]},
                "si_hua": si_hua,
                "stars": key_stars,
                "focus": focus,
                "stance": stance,
                # 白话导语：把「年龄 / 大限 / 太岁」三个数字与宫名翻译成一句话
                "plain": (
                    f"你这一年 {age} 周岁，正走"
                    f"「{da_xian_palace['name']}」宫当值的这十年"
                    f"（{da_xian_palace['da_xian']['from']}-"
                    f"{da_xian_palace['da_xian']['to']} 岁）；"
                    f"今年事情最集中在「{PALACE_PLAIN.get(tai_name, tai_name)}」上，"
                    f"整体{stance}。"
                ),
                "points": points,
            }
        )

    return years
