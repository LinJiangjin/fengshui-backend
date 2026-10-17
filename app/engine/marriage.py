# -*- coding: utf-8 -*-
"""合婚配对（确定性计算层）。

与项目其它引擎同一条铁律：**数值由代码算，文案是确定性映射**，不调大模型。

规则与口径
----------
* **生肖一律按立春分界**取年支（与八字年柱同口径，见 :func:`bazhai.lichun_year`）。
  公历 1、2 月出生的人若按元旦算生肖会整整差一年，这一条不能省。
* 地支关系（六合 / 六冲 / 六害 / 三刑 / 自刑）复用八字与玄空共用的
  ``BRANCH_HE`` / ``BRANCH_CLASH`` / ``BRANCH_HARM`` / ``BRANCH_PUNISH_GROUPS``
  / ``BRANCH_SELF_PUNISH``，**不另建一套**。
* 天干五合：甲己化土、乙庚化金、丙辛化水、丁壬化木、戊癸化火。
* 喜用神互补：双方喜用五行**相生或相同**即为互补。

能做什么 / 不做什么
--------------------
* **能**：给出生肖 / 年支、日干、日支、喜用几层的配对关系与综合倾向。
* **不做**：不断「能不能成」「会不会离」这类定论。合婚看的是**相处中的
  摩擦点与助力点**，不是判决书；文案一律落在「宜如何相处」上。
"""

from __future__ import annotations

from typing import Any

from .bazi import build_bazi
from .bazhai import lichun_year
from .constants import (
    BRANCH_CLASH,
    BRANCH_ELEMENT,
    BRANCH_HARM,
    BRANCH_HE,
    BRANCH_PUNISH_GROUPS,
    BRANCH_SAN_HE,
    BRANCH_SELF_PUNISH,
    EARTHLY_BRANCHES,
    GENERATES,
    HEAVENLY_STEMS,
    MARRIAGE_LEVELS,
    MARRIAGE_RULES_VERSION,
    MARRIAGE_SCORE,
    STEM_CLASH,
    STEM_ELEMENT,
    STEM_HE,
    STEM_HE_ELEMENT,
    ZODIACS,
)

__all__ = [
    "bazi_match",
    "branch_relation_of",
    "build_match",
    "san_he_of",
    "zodiac_branch_of",
    "zodiac_match",
]

ZODIAC_BY_BRANCH = dict(zip(EARTHLY_BRANCHES, ZODIACS))


def zodiac_branch_of(year: int, month: int = 0, day: int = 0) -> tuple[str, str, int]:
    """出生年（公历）-> (生肖, 年支, 校正后的农历年)。

    以**立春**为界：立春前出生算上一年。只给年份时不做修正。
    """
    solar_year, _ = lichun_year(year, month, day)
    branch = EARTHLY_BRANCHES[(solar_year - 4) % 12]
    return ZODIAC_BY_BRANCH[branch], branch, solar_year


def san_he_of(a: str, b: str) -> dict[str, str] | None:
    """两支行不行成三合局（只看这两支同属哪一局）。

    严格说三合需三支齐全，两两只见只能算「半合」。这里返回所属局，
    但 ``is_full`` 恒为 False —— 只有两支时不谎称成局。
    """
    for group in BRANCH_SAN_HE:
        if a in group["branches"] and b in group["branches"]:
            return {
                "name": group["name"],
                "element": group["element"],
                "is_full": False,
            }
    return None


def branch_relation_of(a: str, b: str) -> dict[str, Any]:
    """两支行不行成关系，返回最重的一种。

    优先级：六冲 > 六合 > 六害 > 三刑 / 自刑 > 半合（三合局同属）。
    六合与六害不会同时命中（两组地支不重叠），但刑与害可以，
    所以这里取最重的一种展示，明细另给。
    """
    if BRANCH_CLASH.get(a) == b:
        return {"key": "六冲", "level": "大凶",
                "plain": "正对着，性格与节奏容易硬碰硬"}
    if BRANCH_HE.get(a) == b:
        return {"key": "六合", "level": "旺",
                "plain": "天然投缘，是最省心的一种配对"}
    if BRANCH_HARM.get(a) == b:
        return {"key": "六害", "level": "煞",
                "plain": "暗地里别扭，容易在细节上互相消耗"}
    if a == b and a in BRANCH_SELF_PUNISH:
        return {"key": "自刑", "level": "煞",
                "plain": "同属一个生肖且该生肖自刑，容易自己跟自己较劲"}
    for group in BRANCH_PUNISH_GROUPS:
        if a in group and b in group:
            return {"key": "相刑", "level": "煞",
                    "plain": "彼此较劲，容易在原则问题上僵住"}
    if a == b:
        return {"key": "同支", "level": "平",
                "plain": "同一个生肖，性情相近，好处是投契、坏处是缺点会叠在一起"}
    group = san_he_of(a, b)
    if group is not None:
        return {"key": "半合", "level": "平", "san_he": group,
                "plain": f"同属{group['name']}的两支，有缘分底子，"
                         f"但只有两支不算成局（三合要三支齐全）"}
    return {"key": "无合冲", "level": "平", "plain": "没有明显的合冲刑害"}


def _stem_relation(a: str, b: str) -> dict[str, Any]:
    """两天干的五合 / 相冲。"""
    if STEM_HE.get(a) == b:
        pair = "".join(sorted((a, b), key=HEAVENLY_STEMS.index))
        element = STEM_HE_ELEMENT.get(pair, "")
        return {
            "key": "天干五合",
            "element": element,
            "level": "旺",
            "plain": f"{a}{b}相合化{element}，古称「夫妇之合」，"
                     f"是两个人之间最强的吸引力",
        }
    if STEM_CLASH.get(a) == b:
        return {"key": "天干相冲", "level": "煞",
                "plain": f"{a}{b}相冲，想法与表达方式容易对不上"}
    return {"key": "无合冲", "level": "平", "plain": "天干无合冲"}


def _yong_complement(a_yong: list[dict], b_yong: list[dict]) -> dict[str, Any]:
    """喜用神互补：双方喜用五行**相生或相同**即算互补。"""
    a_set = {g["element"] for g in a_yong}
    b_set = {g["element"] for g in b_yong}
    if not a_set or not b_set:
        return {"key": "不足", "level": "平", "plain": "喜用神不足，不好判断互补"}

    hits: list[str] = []
    for x in sorted(a_set):
        for y in sorted(b_set):
            if x == y:
                hits.append(f"{x}{y}同气")
            elif GENERATES[x] == y:
                hits.append(f"{x}生{y}")
            elif GENERATES[y] == x:
                hits.append(f"{y}生{x}")
    if hits:
        return {
            "key": "互补",
            "level": "旺",
            "hits": hits,
            "plain": f"双方喜用{'、'.join(hits[:3])}——"
                     f"你要的正好是对方有的，相处起来互相补位",
        }
    return {"key": "不互补", "level": "平",
            "plain": "双方喜用五行既不相生也不同气，谈不上互补，"
                     "但也未必冲突，看具体命局"}


def _item(
    key: str, label: str, relation: dict[str, Any], score: int,
    detail: str,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "relation": relation["key"],
        "level": relation["level"],
        "score": score,
        "plain": relation["plain"],
        "detail": detail,
    }


def _level_of(score: int) -> tuple[str, str]:
    for threshold, name, level in MARRIAGE_LEVELS:
        if score >= threshold:
            return name, level
    last = MARRIAGE_LEVELS[-1]
    return last[1], last[2]


def zodiac_match(
    a_year: int, b_year: int,
    a_month: int = 0, a_day: int = 0,
    b_month: int = 0, b_day: int = 0,
) -> dict[str, Any]:
    """生肖合婚：只要两人的出生年（可带月日做立春分界）。"""
    a_zodiac, a_branch, a_solar_year = zodiac_branch_of(a_year, a_month, a_day)
    b_zodiac, b_branch, b_solar_year = zodiac_branch_of(b_year, b_month, b_day)

    cfg = MARRIAGE_SCORE
    relation = branch_relation_of(a_branch, b_branch)
    group = relation.get("san_he")
    if group is not None:
        delta = cfg["san_he"]
    elif relation["key"] == "六合":
        delta = cfg["liu_he"]
    elif relation["key"] == "六冲":
        delta = cfg["year_clash"]
    elif relation["key"] == "六害":
        delta = cfg["year_harm"]
    elif relation["key"] in ("相刑", "自刑"):
        delta = cfg["year_punish"]
    else:
        delta = 0

    score = max(cfg["min"], min(cfg["max"], cfg["base"] + delta))
    name, level = _level_of(score)

    if group is not None:
        detail = f"{a_zodiac}与{b_zodiac}同属「{group['name']}」，是三合局的缘分底子。"
    else:
        detail = f"{a_zodiac}（{a_branch}）与{b_zodiac}（{b_branch}）{relation['key']}。"

    items = [_item("year", "生肖（年支）", relation, delta, detail)]

    points = [
        f"{a_zodiac}与{b_zodiac}：{detail}"
        f"（生肖一律按立春分界，{a_year} 年生人属{a_zodiac}"
        f"{'' if a_solar_year == a_year else f'，实际按农历 {a_solar_year} 年计'}）。",
        f"这一项是「{relation['key']}」——{relation['plain']}。",
        "生肖合婚只看年支，是最粗的一层：它反映的是两个人最外层的气场合不合，"
        "不能替代完整八字。要看得细，请补全出生日期做八字合婚。",
    ]

    return {
        "mode": "zodiac",
        "a": {"year": a_year, "zodiac": a_zodiac, "branch": a_branch,
              "solar_year": a_solar_year},
        "b": {"year": b_year, "zodiac": b_zodiac, "branch": b_branch,
              "solar_year": b_solar_year},
        "items": items,
        "score": score,
        "level": name,
        "level_key": level,
        "plain": (
            f"{a_zodiac}配{b_zodiac}，生肖上是「{relation['key']}」"
            f"——{relation['plain']}，综合{name}。"
        ),
        "points": points,
        "advice": _advice_of(relation, name),
        "rules_version": MARRIAGE_RULES_VERSION,
    }


def bazi_match(
    a: dict[str, Any], b: dict[str, Any],
    a_input: dict[str, Any] | None = None,
    b_input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """八字合婚：年支 / 日干 / 日支 / 喜用，逐层看。"""
    cfg = MARRIAGE_SCORE

    a_year_gan = a["pillars"][0]["gan"]
    a_year_zhi = a["pillars"][0]["zhi"]
    a_day_gan = a["day_master"]["gan"]
    a_day_zhi = a["day_master"]["zhi"]
    b_year_gan = b["pillars"][0]["gan"]
    b_year_zhi = b["pillars"][0]["zhi"]
    b_day_gan = b["day_master"]["gan"]
    b_day_zhi = b["day_master"]["zhi"]

    # 1) 年支（生肖）
    year_rel = branch_relation_of(a_year_zhi, b_year_zhi)
    group = year_rel.get("san_he")
    if group is not None:
        year_delta = cfg["san_he"]
    elif year_rel["key"] == "六合":
        year_delta = cfg["liu_he"]
    elif year_rel["key"] == "六冲":
        year_delta = cfg["year_clash"]
    elif year_rel["key"] == "六害":
        year_delta = cfg["year_harm"]
    elif year_rel["key"] in ("相刑", "自刑"):
        year_delta = cfg["year_punish"]
    else:
        year_delta = 0

    # 2) 日干（本人）五合 / 相冲
    stem_rel = _stem_relation(a_day_gan, b_day_gan)
    if stem_rel["key"] == "天干五合":
        stem_delta = cfg["stem_he"]
    elif stem_rel["key"] == "天干相冲":
        stem_delta = cfg["stem_clash"]
    else:
        stem_delta = 0

    # 3) 日支（夫妻宫）
    day_rel = branch_relation_of(a_day_zhi, b_day_zhi)
    if day_rel["key"] == "六合":
        day_delta = cfg["day_liu_he"]
    elif day_rel["key"] == "六冲":
        day_delta = cfg["day_clash"]
    elif day_rel["key"] == "六害":
        day_delta = cfg["day_harm"]
    elif day_rel["key"] in ("相刑", "自刑"):
        day_delta = cfg["self_punish"]
    else:
        day_delta = 0

    # 4) 喜用神互补
    yong_rel = _yong_complement(a["favorable"], b["favorable"])
    yong_delta = cfg["yong_complement"] if yong_rel["key"] == "互补" else 0

    total = cfg["base"] + year_delta + stem_delta + day_delta + yong_delta
    score = max(cfg["min"], min(cfg["max"], total))
    name, level = _level_of(score)

    items = [
        _item("year", "生肖（年支）", year_rel, year_delta,
              f"{ZODIAC_BY_BRANCH[a_year_zhi]}（{a_year_zhi}）配"
              f"{ZODIAC_BY_BRANCH[b_year_zhi]}（{b_year_zhi}）"),
        _item("day_stem", "日干（本人）", stem_rel, stem_delta,
              f"{a_day_gan}日配{b_day_gan}日"),
        _item("day_branch", "日支（夫妻宫）", day_rel, day_delta,
              f"{a_day_zhi}配{b_day_zhi}"),
        _item("yong", "喜用互补", yong_rel, yong_delta,
              "双方喜用神是否相生或同气"),
    ]

    good = [i for i in items if i["score"] > 0]
    bad = [i for i in items if i["score"] < 0]

    points = [
        f"年支（最外层气场）：{year_rel['key']}——{year_rel['plain']}。",
        f"日干（两个人本身）：{stem_rel['key']}——{stem_rel['plain']}。",
        f"日支（夫妻宫）：{day_rel['key']}——{day_rel['plain']}。",
        f"喜用神：{yong_rel['plain']}。",
    ]
    if good and bad:
        points.append(
            f"有合有冲：合在「{'、'.join(i['label'] for i in good)}」，"
            f"冲在「{'、'.join(i['label'] for i in bad)}」——"
            f"合处能不能解冲处，是这段关系的关键。"
        )
    elif bad:
        points.append(
            f"几处都在冲克上（{'、'.join(i['label'] for i in bad)}），"
            f"相处要刻意留缓冲，别把分歧攒着一起算。"
        )
    elif good:
        points.append(
            f"几处都在合上（{'、'.join(i['label'] for i in good)}），"
            f"底子不错，剩下的靠日常经营。"
        )
    points.append(
        "合婚看的是摩擦点与助力点，不是判决书——"
        "它说的是「你们容易在哪儿卡住、又靠什么补回来」，"
        "能不能在一起从来不只由命盘决定。"
    )

    return {
        "mode": "bazi",
        "a": {
            "year": (a_input or {}).get("year"),
            "zodiac": ZODIAC_BY_BRANCH[a_year_zhi],
            "branch": a_year_zhi,
            "day_pillar": a["day_master"]["pillar"],
            "element": a["day_master"]["element"],
            "favorable": [g["element"] for g in a["favorable"]],
        },
        "b": {
            "year": (b_input or {}).get("year"),
            "zodiac": ZODIAC_BY_BRANCH[b_year_zhi],
            "branch": b_year_zhi,
            "day_pillar": b["day_master"]["pillar"],
            "element": b["day_master"]["element"],
            "favorable": [g["element"] for g in b["favorable"]],
        },
        "items": items,
        "score": score,
        "level": name,
        "level_key": level,
        "plain": (
            f"{ZODIAC_BY_BRANCH[a_year_zhi]}配{ZODIAC_BY_BRANCH[b_year_zhi]}，"
            f"年支{year_rel['key']}、日干{stem_rel['key']}、"
            f"日支{day_rel['key']}，综合{name}。"
        ),
        "points": points,
        "advice": _advice_of(year_rel, name),
        "rules_version": MARRIAGE_RULES_VERSION,
    }


def _advice_of(relation: dict[str, Any], level_name: str) -> str:
    """按最外层（生肖）关系与综合档位给一句落到相处上的建议。"""
    key = relation["key"]
    if key == "六冲":
        return "冲不是不能在一起，是节奏对不上：大事提前说开，小事各让一步，别在同一个时间点上抢方向盘。"
    if key == "六害":
        return "害主暗耗，问题多半出在「没说出口的期待」上。定期把不舒服的事摊开讲，比忍着强。"
    if key in ("相刑", "自刑"):
        return "刑主较劲，双方都容易在原则问题上不退。约定一个「僵住就先暂停」的规则，比当场分胜负有用。"
    if key == "六合":
        return "底子投缘，不用刻意经营也能顺畅；要留意的是别因为太顺而忽略对方真正想要的东西。"
    if key in ("半合", "同支"):
        return "有缘分底子，但同一类性情也会让缺点叠在一起。出现摩擦时先想「这是不是我自己也有的问题」。"
    if level_name in ("上吉", "吉"):
        return "几处都合得上，是省心的组合；剩下的靠日常经营，别把好底子当理所当然。"
    return "没有明显的合冲，属于「靠相处定好坏」的类型：沟通质量比命盘更能决定结果。"


def build_match(
    mode: str = "zodiac",
    a_year: int | None = None,
    b_year: int | None = None,
    a: dict[str, Any] | None = None,
    b: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """统一入口。

    Args:
        mode: ``zodiac`` 只要两人的出生年；``bazi`` 需要完整出生信息。
        a_year / b_year: 生肖模式的出生年（可配 ``a`` / ``b`` 里的月日做立春分界）。
        a / b: 出生信息字典，八字模式必填
            ``{year, month, day, hour, minute, gender, longitude}``。

    Returns:
        可直接序列化的配对结果。
    """
    if mode == "zodiac":
        if a_year is None or b_year is None:
            raise ValueError("生肖合婚必须给两人的出生年")
        a_info = a or {}
        b_info = b or {}
        return zodiac_match(
            a_year, b_year,
            a_month=int(a_info.get("month", 0) or 0),
            a_day=int(a_info.get("day", 0) or 0),
            b_month=int(b_info.get("month", 0) or 0),
            b_day=int(b_info.get("day", 0) or 0),
        )
    if mode == "bazi":
        if not a or not b:
            raise ValueError("八字合婚必须给两人的完整出生信息")
        required = ("year", "month", "day", "hour", "gender")
        for tag, info in (("甲方", a), ("乙方", b)):
            missing = [k for k in required if k not in info]
            if missing:
                raise ValueError(f"{tag}缺少：{'、'.join(missing)}")
            # 生肖模式允许 month/day 为 0（不参与立春分界），八字模式不行——
            # 不在这里卡住的话，0 会一路漏到 build_bazi 变成「非法出生日期」
            if not 1 <= int(info["month"]) <= 12 or not 1 <= int(info["day"]) <= 31:
                raise ValueError(
                    f"{tag}的出生月日不完整，八字合婚需要完整的出生年月日时"
                )
        a_chart = build_bazi(
            year=int(a["year"]), month=int(a["month"]), day=int(a["day"]),
            hour=int(a["hour"]), minute=int(a.get("minute", 0) or 0),
            gender=a["gender"], longitude=float(a.get("longitude", 120.0)),
            name=str(a.get("name", "")),
        )
        b_chart = build_bazi(
            year=int(b["year"]), month=int(b["month"]), day=int(b["day"]),
            hour=int(b["hour"]), minute=int(b.get("minute", 0) or 0),
            gender=b["gender"], longitude=float(b.get("longitude", 120.0)),
            name=str(b.get("name", "")),
        )
        return bazi_match(a_chart, b_chart, a, b)
    raise ValueError("mode 只能是 zodiac 或 bazi")
