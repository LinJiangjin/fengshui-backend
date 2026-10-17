# -*- coding: utf-8 -*-
"""玄空飞星 · 进阶盘（玄空月盘 + 宅运盘）。

与既有模块的分工
----------------
* :mod:`.flying_star` —— **流年盘**：一年一星入中，答「今年财位在哪」。
* :mod:`.daily_star`  —— **日家紫白**：一日一星入中，答「今日吉位 / 忌方」。
* :mod:`.xuankong`（本模块）—— 两条进阶线：

  * **玄空月盘**：一月一星入中，看流月吉凶，与流年盘叠参。
  * **宅运盘**：以「运星 / 山星 / 向星」三盘叠加论一宅格局，回答
    「这套房子本身旺不旺、哪个宫宜主人、哪个宫宜聚财」。

三条规则一律确定性计算，不调用任何大模型
------------------------------------------
1. **三元九运**：1864 年（甲子）为一运之始，每运 20 年，九运 180 年一轮。
   接建宅年份自动定运，也允许直接指定运数。
2. **下卦起星**：运星入中顺飞得运盘；取运盘上「坐山宫 / 向首宫」之数分别作
   山星、向星入中数，再依坐山 / 向首的**阴阳**决定顺飞或逆飞
   （阳顺阴逆），三盘叠加成一宅之盘。
3. **月白**：依《紫白诀》「子午卯酉八白求，辰戌丑未五黄头，寅申巳亥二黑起，
   逆数年月不须愁」定正月入中星，再逐月逆退。节气月以十二「节」为界
   （立春起正月），与八字月柱同口径。

刻意不做的部分
--------------
**兼向替卦不实现**。坐向度数偏离该山中心 4.5 度以上时，传统上要另起替卦，
而替卦涉及「五黄无阴阳可辨、须寄宫」等流派分歧较大的处理。本模块一律按
**正针下卦**起星，并在结果里用 ``offset`` / ``兼向`` 标注提示，不给出
未经统一口径的替卦结论——宁可少说，不说错。

本模块为纯函数实现，输出可复现、可单元测试。
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

try:  # pragma: no cover - 依赖缺失时不影响其它引擎模块被导入
    from lunar_python import Solar
except ImportError as _exc:  # pragma: no cover
    Solar = None  # type: ignore[assignment]
    _IMPORT_ERROR: Exception | None = _exc
else:
    _IMPORT_ERROR = None

from .bazhai import lichun_year
from .compass import opposite_mountain, orient
from .constants import (
    CONTROLS,
    DOUBLE_STAR_CLASSIC,
    DRAGON_MOUNTAINS,
    EARTHLY_BRANCHES,
    FLYING_ORDER,
    GENERATES,
    JIE_TO_MONTH,
    MONTH_NAMES,
    MONTH_WHITE_BASE,
    MOUNTAIN_DRAGON,
    MOUNTAIN_YIN_YANG,
    PAIR_WUHUANG_FLOOR,
    PAIR_WUXING_TEXT,
    PALACE_BY_LUOSHU,
    PATTERN_INFO,
    STAR_INFO,
    STAR_STATE_BY_DELTA,
    TRIGRAM_BY_MOUNTAIN,
    TRIGRAM_INFO,
    WUHUANG_LOST_LEVEL,
    WUHUANG_LOST_NOTE,
    XUANKONG_LEVELS,
    XUANKONG_ROLE,
    XUANKONG_RULES_VERSION,
    XUANKONG_SCORE,
    YUAN_YUN_SPAN,
    YUAN_YUN_START_YEAR,
    YUN_INFO,
)
from .flying_star import build_palaces, center_star_of_year
from .lunar_cache import INSTALLED as _LUNAR_YEAR_CACHE  # noqa: F401  装多年份历法表缓存

__all__ = [
    "build_month_palaces",
    "center_star_of_month",
    "double_star_of",
    "dragon_mountain_of",
    "dragon_of",
    "forward_of",
    "house_chart",
    "jieqi_month_of",
    "judge_pattern",
    "month_chart",
    "patched",
    "stack_advice",
    "star_state",
    "tianyuan_of_trigram",
    "year_branch_of",
    "yin_yang_of",
    "yun_of_year",
]

# 兼向判定的容差：每山 15 度，中心线两侧各 7.5 度为该山正针；
# 传统上偏离中心超过 4.5 度即视为「兼向」（骑缝），需另起替卦。
# 本模块不做替卦，只在此阈值外给出提示。
JIANXIANG_TOLERANCE = 4.5


def patched() -> bool:
    """历法表多年份缓存是否已生效（供自检与调试）。"""
    return bool(_LUNAR_YEAR_CACHE)


def _require_solar() -> Any:
    """返回 lunar-python 的 Solar 类，未安装时给出明确的安装提示。"""
    if Solar is None:  # pragma: no cover
        raise RuntimeError(
            "缺少排盘依赖 lunar-python，请执行：pip install lunar-python"
        ) from _IMPORT_ERROR
    return Solar


# ================================================================ 三元九运
def yun_of_year(year: int, source: str = "year") -> dict[str, Any]:
    """公历年 -> 三元九运。

    上元一运自 1864 年（同治三年 · 甲子）起，每运 20 年::

        运 = ((year - 1864) // 20) % 9 + 1

    Raises:
        ValueError: 年份越出三元九运的有效区间（1864-2043 之外仍可推，
            但早于 1864 无意义）。
    """
    if year < YUAN_YUN_START_YEAR:
        raise ValueError(
            f"三元九运自 {YUAN_YUN_START_YEAR} 年起算，{year} 年无对应运数"
        )
    number = ((year - YUAN_YUN_START_YEAR) // YUAN_YUN_SPAN) % 9 + 1
    return _yun_payload(number, year, source)


def _yun_payload(number: int, year: int | None, source: str) -> dict[str, Any]:
    """把运数展开成完整描述。"""
    if not 1 <= number <= 9:
        raise ValueError(f"运数只能是 1-9，收到：{number}")
    info = YUN_INFO[number]
    star = STAR_INFO[number]
    start = YUAN_YUN_START_YEAR + (number - 1) * YUAN_YUN_SPAN
    return {
        "number": number,
        "name": info["name"],
        "yuan": info["yuan"],
        "element": info["element"],
        "star": number,
        "star_name": star["name"],
        "start_year": start,
        "end_year": start + YUAN_YUN_SPAN - 1,
        "source": source,
        "label": f"{info['yuan']}{info['name']}",
        "summary": (
            f"{info['name']}（{info['yuan']}）当元，"
            f"{star['name']}入中为旺星，主 {star['label']}。"
        ),
    }


# ================================================================ 飞布
def _fly(center: int, forward: bool) -> dict[int, int]:
    """以 ``center`` 入中飞布九宫，返回 ``{宫位洛书数: 星数}``。

    一律沿 :data:`FLYING_ORDER`（中 -> 乾 -> 兑 -> 艮 -> 离 -> 坎 -> 坤 -> 震 -> 巽）
    走，只是方向不同：

    * 顺飞：入中之数起，每步 +1
    * 逆飞：入中之数起，每步 -1
    """
    out: dict[int, int] = {}
    for step, luoshu in enumerate(FLYING_ORDER):
        if forward:
            out[luoshu] = (center + step - 1) % 9 + 1
        else:
            out[luoshu] = (center - step - 1) % 9 + 1
    return out


# ================================================================ 月盘
def _prev_jie(date: _dt.date) -> tuple[str, _dt.date]:
    """该日期之前最近一个已交的「节」（十二节之一）。

    二十四节气里「节」与「中气」交替，``getPrevJieQi()`` 可能返回中气
    （如霜降），此时再往前退一天继续找，最多退三次即可命中。

    Returns:
        (节名, 交节日期)
    """
    solar_cls = _require_solar()
    cursor = solar_cls.fromYmd(date.year, date.month, date.day)
    for _ in range(3):
        jq = cursor.getLunar().getPrevJieQi()
        if jq.isJie():
            solar = jq.getSolar()
            y, m, d = (int(x) for x in solar.toYmd().split("-"))
            return jq.getName(), _dt.date(y, m, d)
        cursor = jq.getSolar().next(-1)
    raise RuntimeError(f"找不到 {date.isoformat()} 之前最近的节")  # pragma: no cover


def jieqi_month_of(date: _dt.date) -> tuple[int, str, str]:
    """日期 -> (节气月序 1-12, 月名, 所属节名)。

    节气月以「节」为界：立春起正月、惊蛰起二月……小寒起十二月。
    注意与公历月不同——2026-01-06 属十二月（小寒），而非次年正月。
    """
    name, _ = _prev_jie(date)
    index = JIE_TO_MONTH[name]
    return index, MONTH_NAMES[index - 1], name


def year_branch_of(date: _dt.date) -> str:
    """该日期所属的地支年（**以立春为界**）。

    年支用六十甲子的确定性公式 ``(year - 4) % 12``，年份本身先经
    :func:`bazhai.lichun_year` 按立春校正——否则 1 月出生/测算会取错年支，
    进而把月白起法算错整整一档。
    """
    solar_year, _ = lichun_year(date.year, date.month, date.day)
    return EARTHLY_BRANCHES[(solar_year - 4) % 12]


def center_star_of_month(branch: str, month_index: int) -> int:
    """月白入中星。

    Args:
        branch: 年支（立春分界后的）。
        month_index: 节气月序，1 起（正月）。

    《紫白诀》：子午卯酉年八白起正月，辰戌丑未年五黄起正月，
    寅申巳亥年二黑起正月，逐月**逆退**一位。
    """
    if branch not in MONTH_WHITE_BASE:
        raise ValueError(f"年支只能是十二地支之一，收到：{branch}")
    if not 1 <= month_index <= 12:
        raise ValueError(f"节气月序应在 1-12 之间，收到：{month_index}")
    base = MONTH_WHITE_BASE[branch]
    return (base - (month_index - 1) - 1) % 9 + 1


# 月星与流年星同宫时的复合结论。两盘都是「顺飞」，只有入中之数相同时
# 才会出现同星同宫，因此更常见的是不同星同宫——那种组合才是逐宫取舍的依据。
_LEVEL_SCORE = {"旺": 2, "平": 0, "煞": -1, "大凶": -3}


def stack_advice(month_star: int, year_star: int) -> dict[str, Any]:
    """同宫里月星与流年星的复合结论。

    五黄是硬约束：只要同宫有失运五黄，不论配什么星都宜静守；两五黄叠临最重。
    其余按两星自身档位求和分档。
    """
    same = month_star == year_star
    wuhuang = 5 in (month_star, year_star)

    if wuhuang and same:
        return {"key": "双五黄", "level": "大凶",
                "note": "两盘五黄叠临此宫，为全盘最重之煞，忌动土、安床、开门。"}
    if wuhuang:
        return {"key": "五黄同宫", "level": "煞",
                "note": "此宫有失运五黄同宫，本月宜静守，忌动土、安床，可用金属化泄。"}

    score = _LEVEL_SCORE[STAR_INFO[month_star]["level"]] + \
        _LEVEL_SCORE[STAR_INFO[year_star]["level"]]
    if score >= 4:
        return {"key": "叠吉", "level": "旺",
                "note": "两吉星同宫，此位本月效应加倍，宜作重点使用的方位。"}
    if score >= 1:
        return {"key": "小吉", "level": "平",
                "note": "一吉一平（或旺星压住煞星），此位本月可用。"}
    if score >= -1:
        return {"key": "参半", "level": "平",
                "note": "吉凶相参，此位本月宜守不宜攻。"}
    if score >= -3:
        return {"key": "叠凶", "level": "煞",
                "note": "两盘凶星同宫，此位本月宜静守，忌动土与久居。"}
    return {"key": "重凶", "level": "大凶",
            "note": "两盘重凶同宫，此位本月忌动土、安床、开门。"}


def build_month_palaces(year: int, month_index: int, branch: str) -> list[dict[str, Any]]:
    """玄空月盘九宫，并与同宫流年星叠看。

    每宫给出 ``star``（月星）、``year_star``（流年星）与两者的复合结论
    ``stack``；两盘同星同宫时 ``stacked`` 为真（两盘都是顺飞，故这要求
    入中之数恰好相同）。
    """
    center = center_star_of_month(branch, month_index)
    year_palaces = {p["luoshu"]: p for p in build_palaces(year)}
    palaces: list[dict[str, Any]] = []
    for step, luoshu in enumerate(FLYING_ORDER):
        number = (center + step - 1) % 9 + 1
        trigram, direction = PALACE_BY_LUOSHU[luoshu]
        star = STAR_INFO[number]
        year_star = year_palaces[luoshu]["star"]
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
            "year_star": year_star,
            "year_star_name": STAR_INFO[year_star]["name"],
            "year_star_level": STAR_INFO[year_star]["level"],
            "stacked": year_star == number,
            "stack": stack_advice(number, year_star),
        })
    return palaces


# 九星的吉序（越小越吉）：同档位时用来挑出「相对最旺之宫 / 最需避忌之宫」
_STAR_ORDER = {8: 0, 9: 1, 1: 2, 6: 3, 4: 4, 3: 5, 2: 6, 7: 7, 5: 8}
_LEVEL_ORDER = {"旺": 0, "平": 1, "煞": 2, "大凶": 3}


def _pick_extremes(palaces: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    """挑出月盘的最旺宫与最凶宫。

    先比吉凶档位，同档再比九星自身的吉序。九运的盘整张都是失运之星，
    八宫常常落在同一档，此时只按星数排会挑出两宫相同的方向——加一层
    星曜吉序后必然分出高下，且两宫恒不相同。
    """
    outer = [p for p in palaces if not p["is_center"]]
    key = lambda p: (_LEVEL_ORDER[p["level"]], _STAR_ORDER[p["star"]])  # noqa: E731
    return min(outer, key=key), max(outer, key=key)


def _extreme_payload(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "direction": p["direction"],
        "trigram": p["trigram"],
        "star": p["star"],
        "star_name": p["star_name"],
        "label": p["label"],
        "level": p["level"],
        "note": p["note"],
        "title": f"{p['direction']} · {p['star_name']}",
    }


def _month_key_points(chart: dict[str, Any]) -> list[str]:
    """把月盘结论压成可执行的三五条。"""
    best, worst = chart["best"], chart["worst"]

    points = [
        f"{chart['month_name']}月星 {STAR_INFO[chart['center_star']]['name']} 入中，"
        f"本月气机以此为主。",
        f"本月最旺之宫在{best['direction']}（{best['star_name']}），"
        f"{best['label']}，宜作本月重点使用的方位。",
        f"本月最需避忌之宫在{worst['direction']}（{worst['star_name']}），"
        f"{worst['label']}，忌动土、安床，宜静守。",
    ]

    risky = [p for p in chart["palaces"]
             if not p["is_center"] and p["stack"]["level"] in ("煞", "大凶")]
    if risky:
        names = "、".join(
            f"{p['direction']}（{p['star_name']}·{p['year_star_name']}）" for p in risky[:3]
        )
        points.append(f"月星与流年星同宫偏凶之宫：{names}，本月宜静守，忌动土安床。")

    stacked = [p for p in chart["palaces"] if p["stacked"]]
    if stacked:
        points.append(
            f"本月月星与流年星同数（{stacked[0]['star_name']}）同宫，"
            "两盘吉凶共振，宜以整宅为单位统筹布局。"
        )
    else:
        points.append(
            f"流年星 {chart['year_center_star_name']} 入中、月星 "
            f"{chart['center_star_name']} 入中，两盘入中之数不同，"
            "逐宫请对看月星与流年星的组合。"
        )

    points.append(
        f"月盘用节气月（{chart['jieqi']}起算），与公历月不同步，换月请以交节为准。"
    )
    return points


def month_chart(date: _dt.date) -> dict[str, Any]:
    """玄空月盘：按日期所在节气月起飞星盘，并与流年盘叠看。"""
    month_index, month_name, jieqi = jieqi_month_of(date)
    branch = year_branch_of(date)
    center = center_star_of_month(branch, month_index)
    palaces = build_month_palaces(date.year, month_index, branch)
    year_center = center_star_of_year(date.year)

    best_p, worst_p = _pick_extremes(palaces)

    chart: dict[str, Any] = {
        "date": date.isoformat(),
        "year": date.year,
        "branch": branch,
        "month_index": month_index,
        "month_name": month_name,
        "jieqi": jieqi,
        "jieqi_mnemonic": "子午卯酉八白求，辰戌丑未五黄头，寅申巳亥二黑起，逆数年月不须愁。",
        "center_star": center,
        "center_star_name": STAR_INFO[center]["name"],
        "year_center_star": year_center,
        "year_center_star_name": STAR_INFO[year_center]["name"],
        "palaces": palaces,
        "best": _extreme_payload(best_p),
        "worst": _extreme_payload(worst_p),
        "rules_version": XUANKONG_RULES_VERSION,
    }
    chart["key_points"] = _month_key_points(chart)
    return chart


# ================================================================ 三元龙与阴阳
def dragon_of(mountain: str) -> str:
    """山 -> 三元龙（天元 / 地元 / 人元）。"""
    if mountain not in MOUNTAIN_DRAGON:
        raise ValueError(f"未知的山：{mountain}")
    return MOUNTAIN_DRAGON[mountain]


def yin_yang_of(mountain: str) -> str:
    """山 -> 阴阳（决定该山所在盘顺飞还是逆飞）。"""
    if mountain not in MOUNTAIN_YIN_YANG:
        raise ValueError(f"未知的山：{mountain}")
    return MOUNTAIN_YIN_YANG[mountain]


def tianyuan_of_trigram(trigram: str) -> str:
    """卦 -> 该卦的天元龙之山。

    只知宅卦而不知具体坐山时取天元龙——天元龙恒居每卦正中
    （如坎卦三山壬子癸，子居中），是「正针」默认解。
    """
    for mountain in DRAGON_MOUNTAINS["天元"]:
        if TRIGRAM_BY_MOUNTAIN[mountain] == trigram:
            return mountain
    raise ValueError(f"未知的卦：{trigram}")


def dragon_mountain_of(trigram: str, dragon: str) -> str:
    """卦 + 元龙 -> 该卦中属于这一元龙的那一山。

    每卦三山恰好各占一元，因此这个映射是唯一的（如巽卦 = 辰/巽/巳 分别属
    地元/天元/人元）。
    """
    for mountain in DRAGON_MOUNTAINS[dragon]:
        if TRIGRAM_BY_MOUNTAIN[mountain] == trigram:
            return mountain
    raise ValueError(f"{trigram} 卦中没有{dragon}龙")  # pragma: no cover


def forward_of(center: int, dragon: str, mountain: str) -> bool:
    """山星 / 向星该顺飞还是逆飞。

    这是下卦起星里最容易记错、也最容易做错的一步，单独抽出来便于测试。

    规则（沈氏玄空下卦起星）：取**入中之数**在**元旦盘**（洛书本盘：
    坎1 坤2 震3 巽4 中5 乾6 兑7 艮8 离9）所对应之宫，再取该宫中
    **与坐山（向首）同一元龙**的那一山，由该山之阴阳决定：
    **逢阳顺飞，逢阴逆飞**。

    注意不是看坐山自身的阴阳——曾按「坐山阴阳」实现，结果推出「凡是阴山
    必然到山」的恒等式，与《四十八局旺山旺向》全表对不上。

    Args:
        center: 该盘入中之数（1-9）。
        dragon: 坐山（向首）所属元龙：天元 / 地元 / 人元。
        mountain: 坐山（向首）本身，仅在入中之数为 5 时用到。

    Returns:
        True 表示顺飞。
    """
    if center == 5:
        # 中宫无卦可寄，无从取「同元之山」，退而取本山自身的阴阳。
        # 另有一派主张五黄前十年寄坤、后十年寄艮，本模块不采，见模块文档。
        return MOUNTAIN_YIN_YANG[mountain] == "阳"
    trigram = PALACE_BY_LUOSHU[center][0]
    other = dragon_mountain_of(trigram, dragon)
    return MOUNTAIN_YIN_YANG[other] == "阳"


def _forward_basis(center: int, dragon: str, mountain: str) -> str:
    """顺逆判据的可读说明，直接透出给前端，便于用户追溯。"""
    if center == 5:
        return (
            f"{center} 属中宫无卦，取{mountain}自身阴阳"
            f"（{MOUNTAIN_YIN_YANG[mountain]}）定顺逆"
        )
    trigram = PALACE_BY_LUOSHU[center][0]
    other = dragon_mountain_of(trigram, dragon)
    return (
        f"{center} 属元旦盘{trigram}宫，{mountain}为{dragon}龙，"
        f"故取该宫{dragon}龙之{other}（{MOUNTAIN_YIN_YANG[other]}）定顺逆"
    )


def _mountain_payload(mountain: str, degree: float | None = None,
                      offset: float | None = None) -> dict[str, Any]:
    """坐山 / 向首的完整描述。"""
    trigram = TRIGRAM_BY_MOUNTAIN[mountain]
    info = TRIGRAM_INFO[trigram]
    yin_yang = MOUNTAIN_YIN_YANG[mountain]
    return {
        "mountain": mountain,
        "trigram": trigram,
        "direction": info["direction"],
        "luoshu": info["luoshu"],
        "dragon": MOUNTAIN_DRAGON[mountain],
        "yin_yang": yin_yang,
        "degree": None if degree is None else round(degree, 1),
        "offset": None if offset is None else round(offset, 1),
        "label": f"{mountain}（{MOUNTAIN_DRAGON[mountain]}龙 · {yin_yang}）",
    }


# ================================================================ 星曜旺衰
def star_state(star: int, yun: int) -> dict[str, Any]:
    """某星在某一运下的旺衰。

    玄空论吉凶不看星曜的固定吉凶，而看它与**当运**的关系：
    当运为旺、下一运为生气、上一运为退气，更远为死气 / 煞气。
    五黄是唯一例外——除五运当元外，不论落何运皆主灾。

    Args:
        star: 星数 1-9。
        yun: 当运之数 1-9。

    Returns:
        ``{state, level, note, delta, is_wang}``
    """
    delta = (star - yun) % 9
    state, level, note = STAR_STATE_BY_DELTA[delta]
    if star == 5 and delta != 0:
        # 五黄失运：压过通用档位
        level, note = WUHUANG_LOST_LEVEL, WUHUANG_LOST_NOTE
    return {
        "state": state,
        "level": level,
        "note": note,
        "delta": delta,
        "is_wang": delta == 0,
    }


# ================================================================ 格局
def judge_pattern(shan: dict[int, int], xiang: dict[int, int],
                  sit_luoshu: int, face_luoshu: int, yun: int) -> dict[str, Any]:
    """判定宅运格局。

    「到山」= 山盘旺星落在坐山宫，「到向」= 向盘旺星落在向首宫。据此分出：
    旺山旺向 / 双星会向 / 双星会坐 / 上山下水 / 到山 / 到向 / 两不到。

    优先级按吉凶显著性排列，取第一个命中者（旺山旺向 > 上山下水 >
    双星会向 > 双星会坐 > 单到 > 两不到）。
    """
    shan_to_sit = shan[sit_luoshu] == yun
    shan_to_face = shan[face_luoshu] == yun
    xiang_to_sit = xiang[sit_luoshu] == yun
    xiang_to_face = xiang[face_luoshu] == yun

    if shan_to_sit and xiang_to_face:
        key = "旺山旺向"
    elif shan_to_face and xiang_to_sit:
        key = "上山下水"
    elif shan_to_face and xiang_to_face:
        key = "双星会向"
    elif shan_to_sit and xiang_to_sit:
        key = "双星会坐"
    elif shan_to_sit:
        key = "到山"
    elif xiang_to_face:
        key = "到向"
    else:
        key = "两不到"

    info = PATTERN_INFO[key]
    return {
        "key": key,
        "name": key,
        "level": info["level"],
        "summary": info["summary"],
        "advice": info["advice"],
        "to_sit": shan_to_sit,      # 山盘旺星到坐山
        "to_face": xiang_to_face,   # 向盘旺星到向首
        "shan_at_sit": shan_to_sit,
        "shan_at_face": shan_to_face,
        "xiang_at_sit": xiang_to_sit,
        "xiang_at_face": xiang_to_face,
    }


# ================================================================ 宅运盘
def _palace_level(shan_state: dict[str, Any], xiang_state: dict[str, Any],
                  is_center: bool = False) -> str:
    """把同宫的山星、向星旺衰压成一个四档吉凶（复用 palaceBg 的值域）。

    只有「失运五黄」才会把一宫打成大凶——两星皆失运虽然不佳，但九运一张盘
    上大半宫都是如此（当运星只有一个），若一律判大凶会让整张盘失去区分度。

    中宫不以外围吉凶论：它是全宅气机枢纽，无论飞入何星都只作「平」，
    另见 :func:`_palace_role` 给出的中宫单独建议。
    """
    if is_center:
        return "平"
    weights = {"旺": 3, "生": 2, "退": 0, "死": -1.5, "煞": -2}
    total = weights[shan_state["state"]] + weights[xiang_state["state"]]
    if shan_state["level"] == "大凶" or xiang_state["level"] == "大凶":
        return "大凶"
    if total >= 4:
        return "旺"
    if total >= -1:
        return "平"
    if total >= -4:
        return "煞"
    return "大凶"


def _pair_wuxing(a: int, b: int) -> str:
    """两星五行的生克关系，返回 ``比和 / 相生 / 我生 / 生我 / 相克 / 我克 / 克我``。

    ``我`` 指排在前面的山星。比和与相生 / 相克是对称关系，取不到方向性。
    """
    ea = STAR_INFO[a]["element"]
    eb = STAR_INFO[b]["element"]
    if ea == eb:
        return "比和"
    if GENERATES[ea] == eb:
        return "我生"
    if GENERATES[eb] == ea:
        return "生我"
    if CONTROLS[ea] == eb:
        return "我克"
    return "克我"


def double_star_of(
    shan: int,
    xiang: int,
    shan_state: dict[str, Any],
    xiang_state: dict[str, Any],
    is_center: bool = False,
) -> dict[str, Any]:
    """山星与向星同宫的「双星组合」判词。

    单看一颗星的旺衰只能说「得不得时」；两星交会才生出「出什么事」。
    判词分两层（见 ``DOUBLE_STAR_CLASSIC`` 的说明）：
    有可靠赋文的走经典层，没有的只由五行生克 + 当令与否推出，不编兆应。

    Args:
        shan: 山星数 1-9。
        xiang: 向星数 1-9。
        shan_state / xiang_state: :func:`star_state` 的结果，用来定当令与否。
        is_center: 是否中宫。中宫恒判「平」（与 :func:`_palace_level` 同口径）。

    Returns:
        ``{key, name, source, wuxing, timing, nature, verdict, level, advice}``
    """
    a, b = sorted((shan, xiang))
    entry = DOUBLE_STAR_CLASSIC.get((a, b))

    # 当令：山星或向星其一得时（旺 / 生）即算当令——组合里有一颗得力就压得住
    timing = "当令" if (
        shan_state["state"] in ("旺", "生") or xiang_state["state"] in ("旺", "生")
    ) else "失令"

    relation = _pair_wuxing(shan, xiang)
    # 「我生 / 生我」统称相生，「我克 / 克我」统称相克，用于取推导层模板
    bucket = {
        "我生": "我生", "生我": "生我",
        "我克": "我克", "克我": "克我",
        "比和": "比和",
    }[relation]

    if entry is not None:
        name = entry["name"]
        source = entry["source"]
        nature = entry["nature"]
        verdict = entry["on"] if timing == "当令" else entry["off"]
        level = entry["level_on"] if timing == "当令" else entry["level_off"]
        advice = entry["advice"]
    else:
        # 组合名取**规范序**（小星在前）：同宫征象与谁在山谁在向无关，
        # 山向顺序由 shan_star / xiang_star 两个字段各自带着，不丢信息。
        # 同数叠见（如 9+9）写「九紫九紫同宫」读着别扭，改说「叠见」。
        name = (f"{STAR_INFO[a]['name']}叠见" if a == b
                else f"{STAR_INFO[a]['name']}{STAR_INFO[b]['name']}同宫")
        source = "五行生克"
        ea = STAR_INFO[shan]["element"]
        eb = STAR_INFO[xiang]["element"]
        if relation == "比和":
            nature = f"{STAR_INFO[shan]['name']}与{STAR_INFO[xiang]['name']}" \
                     f"同属{ea}，两星同气。"
        elif bucket in ("我生", "生我"):
            nature = f"{ea}与{eb}相生（{relation}），两星有情。"
        else:
            nature = f"{ea}与{eb}相克（{relation}），两星相战。"
        tpl = PAIR_WUXING_TEXT[bucket]
        verdict = tpl["on"] if timing == "当令" else tpl["off"]
        level = tpl["level_on"] if timing == "当令" else tpl["level_off"]
        advice = "当令宜作常用之区，保持整洁明亮。" if timing == "当令" \
            else "失令宜静守，作储物或次要空间，不宜大动。"

    # 五黄是硬约束：只要组合里有五黄，档位至少压到「煞」，不参与生克累加。
    # 二五交加 / 五黄重叠本身已经把五黄说透了，其余组合必须补一句——
    # 否则「四绿五黄同宫」只讲生克，用户看不出这一宫为什么特殊。
    if 5 in (a, b):
        order = ["旺", "平", "煞", "大凶"]
        if order.index(level) < order.index(PAIR_WUHUANG_FLOOR):
            level = PAIR_WUHUANG_FLOOR
        if (a, b) not in ((2, 5), (5, 5)):
            # 前端是纯文本渲染，不能用 markdown 星号
            nature = (
                f"{nature}另外，五黄是正煞——玄空里最凶的一颗星，"
                f"只要它落在这宫，就不能只按五行生克看。"
            )
            advice = (
                "五黄所在宜静：不作卧室、厨房，不动土，不放大件电器；"
                "宜用铜器或金属化泄，保持整洁。"
            )

    if is_center:
        # 中宫是全宅气机枢纽，不以飞星吉凶论（与 _palace_level 同口径）
        level = "平"

    return {
        "key": f"{a}{b}",
        "shan_star": shan,
        "xiang_star": xiang,
        "name": name,
        "source": source,
        "wuxing": relation,
        "timing": timing,
        "nature": nature,
        "verdict": verdict,
        "level": level,
        "advice": advice,
    }


def _palace_role(shan_state: dict[str, Any], xiang_state: dict[str, Any],
                 is_center: bool) -> str:
    """该宫宜作何用的建议文案。"""
    if is_center:
        return "中宫为全宅气口枢纽，宜整洁明亮，不宜堆杂物。"
    if shan_state["level"] == "大凶" or xiang_state["level"] == "大凶":
        return "此宫有失运五黄，忌动土、安床、开门，宜作储物或卫浴，用金属化泄。"
    if shan_state["is_wang"] and xiang_state["is_wang"]:
        return "山向两旺星同宫，宜作主卧兼起居，人丁财禄俱旺。"
    if shan_state["is_wang"]:
        return "旺星到山，宜作主卧、长辈房，安床于此得人丁之利。"
    if xiang_state["is_wang"]:
        return "旺星到向，宜作客厅、门厅、办公位，纳气于此得财禄之利。"
    if shan_state["state"] in ("死", "煞") and xiang_state["state"] in ("死", "煞"):
        return "山向俱衰退，宜静不宜动，作书房、储物间为妥。"
    return "吉凶相参，宜居中布置，不必刻意催发或化煞。"


def _score_house(pattern: dict[str, Any], palaces: list[dict[str, Any]]) -> int:
    """宅运盘综合评分（可解释：格局分 + 逐宫旺衰分 + 五黄修正 + 凶星组合修正）。

    「凶星组合」只罚 **大凶档** 的双星（二五交加、五黄重叠这类有明确赋文的），
    且带上限：双星组合本来是逐宫解读用的，若整张盘的分数都由它决定，
    就抢了格局分的主判据地位。
    """
    cfg = XUANKONG_SCORE
    total = float(cfg["base"] + cfg["pattern"].get(pattern["key"], 0))

    acc = 0.0
    wuhuang = 0
    bad_pair = 0
    for p in palaces:
        if p["is_center"]:
            continue
        acc += cfg["state"].get(p["shan_state"]["state"], 0)
        acc += cfg["state"].get(p["xiang_state"]["state"], 0)
        if p["has_lost_wuhuang"]:
            wuhuang += 1
        if p["pair"]["level"] == "大凶":
            bad_pair += 1

    acc = max(-cfg["state_cap"], min(cfg["state_cap"], acc))
    total += acc
    total += max(cfg["wuhuang_cap"], cfg["wuhuang"] * wuhuang)
    total += max(cfg["pair_cap"], cfg["pair"] * bad_pair)
    return int(max(cfg["min"], min(cfg["max"], round(total))))


def _score_level(score: int) -> tuple[str, str]:
    """分数 -> (档位名, 四档吉凶)。"""
    for threshold, name, level in XUANKONG_LEVELS:
        if score >= threshold:
            return name, level
    last = XUANKONG_LEVELS[-1]
    return last[1], last[2]


def _house_key_points(chart: dict[str, Any]) -> list[str]:
    """把宅运盘结论压成可执行的行动要点。"""
    sit, face, pattern, yun = chart["sit"], chart["face"], chart["pattern"], chart["yun"]
    points = [
        f"{sit['mountain']}山{face['mountain']}向，值{yun['name']}，"
        f"当运旺星为{STAR_INFO[yun['number']]['name']}。",
        pattern["summary"],
    ]
    points.append(pattern["advice"])

    bad = [p for p in chart["palaces"]
           if not p["is_center"] and p["has_lost_wuhuang"]]
    if bad:
        where = "、".join(p["direction"] for p in bad)
        points.append(
            f"{where}有失运五黄，忌动土、安床与开门；"
            "宜用金属器物或静水化泄，保持此位整洁。"
        )

    # 双星组合里的大凶档（二五交加 / 五黄重叠这类有赋文的）必须单独点出来：
    # 它们不看当令与否都凶，是唯一需要优先处理的逐宫事项
    worst_pairs = [p for p in chart["palaces"]
                   if not p["is_center"] and p["pair"]["level"] == "大凶"]
    for p in worst_pairs:
        points.append(
            f"{p['direction']}（{p['trigram']}宫）是「{p['pair']['name']}」："
            f"{p['pair']['verdict']}{p['pair']['advice']}"
        )

    wang = [p for p in chart["palaces"]
            if not p["is_center"] and p["shan_state"]["is_wang"] and p["xiang_state"]["is_wang"]]
    if wang:
        where = "、".join(f"{p['direction']}（{p['trigram']}宫）" for p in wang)
        points.append(f"{where}山向两旺，宜作主卧、客厅等常动常用之区。")

    if chart["jianxiang"]:
        points.append(
            "坐向偏离该山中心较多，已属兼向；本盘按正针下卦起星，"
            "替卦须另定，结论仅作参考。"
        )
    return points


def house_chart(
    degree: float | None = None,
    declination: float = 0.0,
    trigram: str = "",
    yun: int | None = None,
    build_year: int | None = None,
    name: str = "",
) -> dict[str, Any]:
    """排出宅运盘（玄空下卦起星）。

    Args:
        degree: 罗盘读到的磁方位角（推荐）。与 ``trigram`` 二选一。
        declination: 当地磁偏角，仅在给 ``degree`` 时有效。
        trigram: 直接指定坐山卦；只知卦不知度数时取该卦的**天元龙**为坐山。
        yun: 当运之数 1-9，显式指定。
        build_year: 建宅 / 入宅年份，用于自动定运。与 ``yun`` 二选一，
            两者都给时以 ``yun`` 为准。
        name: 名称，仅作回显。

    Returns:
        可直接序列化的宅运盘字典。

    Raises:
        ValueError: 既未给 degree 也未给 trigram，或运数 / 年份越界。
    """
    # ---- 坐向来源
    orientation: dict[str, Any] | None = None
    if degree is not None:
        orientation = orient(degree, declination)
        sit_mountain = orientation["mountain"]
        face_mountain = orientation["facing"]
    elif trigram:
        tri = trigram.strip()
        if tri not in TRIGRAM_INFO:
            raise ValueError(
                f"宅卦只能是 {'、'.join(TRIGRAM_INFO)} 之一，收到：{tri}"
            )
        sit_mountain = tianyuan_of_trigram(tri)
        face_mountain = opposite_mountain(sit_mountain)
    else:
        raise ValueError("请至少提供 degree（罗盘读数）或 trigram（坐山卦）之一")

    # ---- 运的来源
    if yun is not None:
        if not 1 <= yun <= 9:
            raise ValueError(f"运数只能是 1-9，收到：{yun}")
        yun_info = _yun_payload(yun, build_year, "explicit")
    elif build_year is not None:
        yun_info = yun_of_year(build_year, source="build_year")
    else:
        raise ValueError("请至少提供 yun（运数）或 build_year（建宅年份）之一")

    ynum = yun_info["number"]

    # ---- 三盘
    yun_stars = _fly(ynum, forward=True)  # 运盘恒顺飞
    sit_luoshu = TRIGRAM_INFO[TRIGRAM_BY_MOUNTAIN[sit_mountain]]["luoshu"]
    face_luoshu = TRIGRAM_INFO[TRIGRAM_BY_MOUNTAIN[face_mountain]]["luoshu"]

    shan_center = yun_stars[sit_luoshu]    # 坐山宫之运星 -> 山星入中
    xiang_center = yun_stars[face_luoshu]  # 向首宫之运星 -> 向星入中
    sit_dragon = MOUNTAIN_DRAGON[sit_mountain]
    face_dragon = MOUNTAIN_DRAGON[face_mountain]
    shan_forward = forward_of(shan_center, sit_dragon, sit_mountain)
    xiang_forward = forward_of(xiang_center, face_dragon, face_mountain)
    shan_stars = _fly(shan_center, shan_forward)
    xiang_stars = _fly(xiang_center, xiang_forward)

    pattern = judge_pattern(shan_stars, xiang_stars, sit_luoshu, face_luoshu, ynum)

    # ---- 逐宫组装
    palaces: list[dict[str, Any]] = []
    for luoshu in FLYING_ORDER:
        tri, direction = PALACE_BY_LUOSHU[luoshu]
        is_center = luoshu == 5
        shan = shan_stars[luoshu]
        xiang = xiang_stars[luoshu]
        yun_star = yun_stars[luoshu]
        shan_st = star_state(shan, ynum)
        xiang_st = star_state(xiang, ynum)
        lost_wuhuang = (shan == 5 and shan_st["level"] == "大凶") or (
            xiang == 5 and xiang_st["level"] == "大凶"
        )
        palaces.append({
            "luoshu": luoshu,
            "key": direction,
            "trigram": tri,
            "direction": direction,
            "is_center": is_center,
            # 传统写法：山星在左上、运星在中、向星在右上
            "shan_star": shan,
            "shan_star_name": STAR_INFO[shan]["name"],
            "yun_star": yun_star,
            "yun_star_name": STAR_INFO[yun_star]["name"],
            "xiang_star": xiang,
            "xiang_star_name": STAR_INFO[xiang]["name"],
            "shan_state": shan_st,
            "xiang_state": xiang_st,
            "yun_state": star_state(yun_star, ynum),
            "level": _palace_level(shan_st, xiang_st, is_center),
            "role": _palace_role(shan_st, xiang_st, is_center),
            # 双星组合：两星同宫的「应事」判词，与上面按旺衰得出的 level
            # 是两个维度——level 说得不得时，pair 说出什么事
            "pair": double_star_of(shan, xiang, shan_st, xiang_st, is_center),
            "has_lost_wuhuang": lost_wuhuang,
            "is_sit": luoshu == sit_luoshu,
            "is_face": luoshu == face_luoshu,
        })

    score = _score_house(pattern, palaces)
    level_name, level_key = _score_level(score)

    jianxiang = bool(
        orientation
        and abs(orientation["offset"]) > JIANXIANG_TOLERANCE
    )

    chart: dict[str, Any] = {
        "name": name.strip(),
        "sit": _mountain_payload(
            sit_mountain,
            orientation["degree"] if orientation else None,
            orientation["offset"] if orientation else None,
        ),
        "face": _mountain_payload(face_mountain),
        "orientation": orientation or {},
        "yun": yun_info,
        "center": {
            "shan_star": shan_center,
            "shan_forward": shan_forward,
            "xiang_star": xiang_center,
            "xiang_forward": xiang_forward,
            "shan_direction": "顺飞" if shan_forward else "逆飞",
            "xiang_direction": "顺飞" if xiang_forward else "逆飞",
            # 顺逆判据的可读说明，便于用户追溯这一步是怎么定的
            "shan_basis": _forward_basis(shan_center, sit_dragon, sit_mountain),
            "xiang_basis": _forward_basis(xiang_center, face_dragon, face_mountain),
        },
        "palaces": palaces,
        "pattern": pattern,
        "score": score,
        "level": level_name,
        "level_key": level_key,
        "jianxiang": jianxiang,
        "roles": XUANKONG_ROLE,
        "rules_version": XUANKONG_RULES_VERSION,
    }
    chart["title"] = f"{sit_mountain}山{face_mountain}向 · {yun_info['name']}宅运盘"
    chart["key_points"] = _house_key_points(chart)
    return chart
