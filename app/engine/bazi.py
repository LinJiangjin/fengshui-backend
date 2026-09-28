# -*- coding: utf-8 -*-
"""八字排盘引擎（确定性计算层）。

设计原则
--------
本项目铁律：**数值必须由代码算，文案才交给大模型**。
本模块负责全部数值计算（四柱干支、藏干、五行占比、日主强弱、用神喜忌），
不调用任何 LLM；文案润色统一走 :func:`enhance` 钩子（MVP 阶段原样返回）。

四柱干支依赖 ``lunar-python`` 提供节气交节时刻与干支推算（这部分属于
天文历法数据，自造轮子既易错又无收益）。以下逻辑为本模块自研的纯函数，
均可通过单元测试验证：

* :func:`true_solar_time`   —— 真太阳时校正（经度时差）
* :func:`hour_pillar_gan`   —— 五鼠遁定时干
* :func:`score_elements`    —— 天干 + 地支藏干加权计分并归一化为百分比
* :func:`judge_strength`    —— 得令 / 得地 / 得势三段式强弱打分
* :func:`pick_gods`         —— 依日主强弱取喜用神与忌神

排盘要点
--------
* **月柱按节气分界**：立春换年、节气换月，绝不使用农历月份。
* **日柱按日差推算**：以 1900-01-01 = 甲戌 为锚点（见 :func:`day_pillar_from_anchor`），
  该锚点同时作为对 ``lunar-python`` 结果的独立交叉校验。
* **时柱用五鼠遁**：日干定起时天干；23:00-01:00 为子时，其中 23:00 之后
  标记为「夜子时」（``is_night_zi``）。
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

from .constants import (
    BRANCH_ELEMENT,
    CONTROLS,
    EARTHLY_BRANCHES,
    ELEMENT_COLOR_KEY,
    ELEMENT_ORDER,
    ELEMENT_PHRASE,
    GENERATES,
    HEAVENLY_STEMS,
    HIDDEN_GAN,
    HIDDEN_GAN_WEIGHT,
    HOUR_BRANCHES,
    NAYIN,
    RELATION_LABEL,
    SHI_SHEN,
    STEM_ELEMENT,
    STEM_YIN_YANG,
    STRENGTH_THRESHOLD,
    STRENGTH_WEIGHT,
    WU_SHU_DUN,
)

# 日柱锚点：1900-01-01 为甲戌日（六十甲子序号 10）
_DAY_ANCHOR_DATE = _dt.date(1900, 1, 1)
_DAY_ANCHOR_INDEX = 10

# 真太阳时基准经线（东经 120°，即北京时间标准经线）
STANDARD_LONGITUDE = 120.0
# 每经度对应 4 分钟时差
MINUTES_PER_LONGITUDE = 4.0

__all__ = [
    "build_bazi",
    "enhance",
    "true_solar_time",
    "hour_branch_of",
    "hour_pillar_gan",
    "day_pillar_from_anchor",
    "jiazi_index",
    "na_yin_of",
    "shi_shen_of",
    "apply_night_zi_fix",
    "score_elements",
    "to_percent",
    "relation_of",
    "judge_strength",
    "pick_gods",
    "element_summary_of",
]


# ---------------------------------------------------------------- 基础工具
def _require_solar() -> Any:
    """返回 lunar-python 的 Solar 类，未安装时给出明确的安装提示。"""
    if Solar is None:  # pragma: no cover
        raise RuntimeError(
            "缺少排盘依赖 lunar-python，请执行：pip install lunar-python"
        ) from _IMPORT_ERROR
    return Solar


def _pillar_of(index: int) -> str:
    """六十甲子序号(0-59) -> 干支字符串。"""
    return HEAVENLY_STEMS[index % 10] + EARTHLY_BRANCHES[index % 12]


def hour_branch_of(hour: int) -> str:
    """北京时间小时数(0-23) -> 时辰地支。

    23:00-01:00 为子时，其余每两个小时一支。
    """
    return HOUR_BRANCHES[((hour + 1) // 2) % 12]


def hour_pillar_gan(day_gan: str, hour_branch: str) -> str:
    """五鼠遁：由日干与时辰地支推出时干。

    日上起时，子时天干由日干决定（甲己还加甲……），其后顺推。
    """
    start_index = HEAVENLY_STEMS.index(WU_SHU_DUN[day_gan])
    offset = EARTHLY_BRANCHES.index(hour_branch)
    return HEAVENLY_STEMS[(start_index + offset) % 10]


def jiazi_index(gan: str, zhi: str) -> int:
    """干支 -> 六十甲子序号（0-59）。甲子为 0，癸亥为 59。"""
    target_gan = HEAVENLY_STEMS.index(gan)
    target_zhi = EARTHLY_BRANCHES.index(zhi)
    for index in range(60):
        if index % 10 == target_gan and index % 12 == target_zhi:
            return index
    raise ValueError(f"非法干支组合：{gan}{zhi}")


def na_yin_of(gan: str, zhi: str) -> str:
    """干支 -> 纳音五行（六十甲子纳音，每两柱共用一名）。"""
    return NAYIN[jiazi_index(gan, zhi) // 2]


def shi_shen_of(day_gan: str, other_gan: str) -> str:
    """十神：以日干为「我」，判断 ``other_gan`` 的十神名称。

    同性（同阴阳）为偏、异性为正。天干与日干同名时按此规则自然得到
    「比肩」——「日主」是**日柱天干这一位置**的专属称呼，由排盘库在日柱
    上标注，不由本函数产生。若在此对同名做「日主」特判，夜子时修正时柱
    天干（如甲日 23 时得甲子）会把时柱十神错标为「日主」。
    """
    relation = relation_of(STEM_ELEMENT[other_gan], STEM_ELEMENT[day_gan])
    same_polarity = STEM_YIN_YANG[other_gan] == STEM_YIN_YANG[day_gan]
    return SHI_SHEN[(relation, same_polarity)]


def apply_night_zi_fix(
    pillars: list[dict[str, Any]],
    is_night_zi: bool = False,
) -> list[dict[str, Any]]:
    """夜子时（23:00-01:00 的前半夜）时柱自洽修正。

    背景：排盘库在默认 sect=2（晚子时归当日日柱）下，日柱取当日干支，
    但时干却按「次日日干」五鼠遁出，于是拼出「当日日柱 + 次日子时天干」
    这种在六十甲子里并不存在的组合（例如 丙寅日 配 庚子时）。

    本函数在**保持「晚子时归当日日柱」约定不变**的前提下，用本模块的
    五鼠遁按当日日干重算时干，并同步刷新天干五行、十神与纳音，
    使四柱重新自洽。必须在计算五行占比与日主强弱之前调用。

    Args:
        pillars: :func:`_build_pillars` 产出的四柱。
        is_night_zi: 真太阳时是否落在 23:00-23:59。

    Returns:
        修正后的四柱（原地修改并返回）。
    """
    if not is_night_zi:
        return pillars

    day_gan = pillars[2]["gan"]
    hour_pillar = pillars[3]
    zhi = hour_pillar["zhi"]
    gan = hour_pillar_gan(day_gan, zhi)
    if gan == hour_pillar["gan"]:
        return pillars

    hour_pillar["gan"] = gan
    hour_pillar["pillar"] = gan + zhi
    hour_pillar["gan_element"] = STEM_ELEMENT[gan]
    hour_pillar["gan_shi_shen"] = shi_shen_of(day_gan, gan)
    hour_pillar["na_yin"] = na_yin_of(gan, zhi)
    return pillars


def day_pillar_from_anchor(date: _dt.date) -> str:
    """以 1900-01-01 = 甲戌 为锚点按日差推算日柱干支。

    这是对排盘库结果的独立交叉校验：两者在 1900-2100 区间应完全一致。
    """
    delta = (date - _DAY_ANCHOR_DATE).days
    return _pillar_of((_DAY_ANCHOR_INDEX + delta) % 60)


def true_solar_time(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int = 0,
    longitude: float = STANDARD_LONGITUDE,
) -> tuple[_dt.datetime, float]:
    """真太阳时校正：按当地经度与东经 120° 的时差平移出生时刻。

    每度 4 分钟，东经大于 120° 则加、小于则减。跨越 0 点时自动换日。

    Args:
        year/month/day/hour/minute: 出生时的北京时间（钟表时间）。
        longitude: 出生地东经度数。

    Returns:
        (校正后的 datetime, 偏移分钟数)。
    """
    offset = (float(longitude) - STANDARD_LONGITUDE) * MINUTES_PER_LONGITUDE
    base = _dt.datetime(year, month, day, hour, minute)
    return base + _dt.timedelta(minutes=offset), round(offset, 2)


def relation_of(element: str, day_master_element: str) -> str:
    """``element`` 相对日主五行的生克关系。

    返回 ``同我 / 生我 / 我生 / 克我 / 我克`` 之一。
    """
    if element == day_master_element:
        return "同我"
    if GENERATES[element] == day_master_element:
        return "生我"
    if GENERATES[day_master_element] == element:
        return "我生"
    if CONTROLS[element] == day_master_element:
        return "克我"
    return "我克"


# ---------------------------------------------------------------- 四柱
def _hidden_of(branch: str) -> list[dict[str, Any]]:
    """地支藏干明细：天干、五行、角色（本气/中气/余气）、计分权重。"""
    result: list[dict[str, Any]] = []
    for gan, role in HIDDEN_GAN[branch]:
        result.append({
            "gan": gan,
            "element": STEM_ELEMENT[gan],
            "role": role,
            "weight": HIDDEN_GAN_WEIGHT[role],
        })
    return result


def _build_pillars(chart: Any) -> list[dict[str, Any]]:
    """从 lunar-python 的 EightChar 组装四柱（含藏干、纳音、十神）。"""
    specs = (
        ("year", "年柱"),
        ("month", "月柱"),
        ("day", "日柱"),
        ("time", "时柱"),
    )
    pillars: list[dict[str, Any]] = []
    for key, name in specs:
        gan = getattr(chart, f"get{key.capitalize()}Gan")()
        zhi = getattr(chart, f"get{key.capitalize()}Zhi")()
        hidden = _hidden_of(zhi)
        pillars.append({
            "key": key,
            "name": name,
            "gan": gan,
            "zhi": zhi,
            "pillar": gan + zhi,
            "gan_element": STEM_ELEMENT[gan],
            "zhi_element": BRANCH_ELEMENT[zhi],
            "hidden": hidden,
            "hidden_text": "".join(h["gan"] for h in hidden),
            "na_yin": getattr(chart, f"get{key.capitalize()}NaYin")(),
            "gan_shi_shen": getattr(chart, f"get{key.capitalize()}ShiShenGan")(),
        })
    return pillars


# ---------------------------------------------------------------- 五行占比
def score_elements(pillars: list[dict[str, Any]]) -> dict[str, float]:
    """按「天干 + 地支藏干」计分得到五行原始分。

    权重：天干 1.0、地支本气 1.0、中气 0.6、余气 0.3。
    """
    scores = {element: 0.0 for element in ELEMENT_ORDER}
    for pillar in pillars:
        scores[STEM_ELEMENT[pillar["gan"]]] += 1.0
        for item in pillar["hidden"]:
            scores[item["element"]] += item["weight"]
    return {k: round(v, 4) for k, v in scores.items()}


def to_percent(scores: dict[str, float]) -> dict[str, int]:
    """把五行原始分归一化为整数百分比，合计恒为 100。

    采用「最大余数法」：先取整，再把余下的份额按小数部分从大到小分配，
    避免四舍五入导致合计为 99 或 101。
    """
    total = sum(scores.values())
    if total <= 0:
        return {element: 0 for element in scores}

    exact = {k: v * 100.0 / total for k, v in scores.items()}
    floors = {k: int(v) for k, v in exact.items()}
    remainders = {k: v - floors[k] for k, v in exact.items()}
    missing = 100 - sum(floors.values())

    # 小数部分大的优先补足；完全相同的按原始分高的优先
    ordered = sorted(
        remainders.keys(),
        key=lambda k: (remainders[k], scores[k]),
        reverse=True,
    )
    for element in ordered[:missing]:
        floors[element] += 1
    return floors


# ---------------------------------------------------------------- 日主强弱
def judge_strength(
    pillars: list[dict[str, Any]],
    day_master_element: str,
) -> dict[str, Any]:
    """三段式判定日主强弱：得令 + 得地 + 得势。

    * 得令：月支本气与日主五行的生克关系（权重最大）。
    * 得地：四支是否有日主同类之根，日支本气根最重。
    * 得势：年/月/时三天干有无比劫（同五行）与印绶（生日主）。
    """
    month_pillar = pillars[1]
    day_pillar = pillars[2]
    day_branch = day_pillar["zhi"]

    # ---------------- 得令
    month_main = month_pillar["hidden"][0]
    deling_relation = relation_of(month_main["element"], day_master_element)
    deling = STRENGTH_WEIGHT["deling"][deling_relation]

    # ---------------- 得地
    weight_dedi = STRENGTH_WEIGHT["dedi"]
    root_detail: list[str] = []
    dedi = 0.0
    for pillar in pillars:
        branch = pillar["zhi"]
        for item in pillar["hidden"]:
            if item["element"] != day_master_element:
                continue
            is_day = pillar["key"] == "day"
            is_main = item["role"] == "本气"
            if is_day and is_main:
                dedi += weight_dedi["日支本气"]
            elif is_day:
                dedi += weight_dedi["日支中余气"]
            elif is_main:
                dedi += weight_dedi["他支本气"]
            else:
                dedi += weight_dedi["他支中余气"]
            root_detail.append(f"{branch}{item['role']}根")
    if not root_detail:
        dedi = weight_dedi["无根"]
        root_detail.append("四支无根")

    # ---------------- 得势
    weight = STRENGTH_WEIGHT["deshi"]
    raw_deshi = 0.0
    help_detail: list[str] = []
    for pillar in pillars:
        if pillar["key"] == "day":
            continue
        relation = relation_of(pillar["gan_element"], day_master_element)
        if relation in ("同我", "生我"):
            raw_deshi += weight[relation]
            help_detail.append(f"{pillar['gan']}{weight[relation]:+.1f}")
        elif relation == "克我":
            raw_deshi += weight["克我"]
            help_detail.append(f"{pillar['gan']}{weight['克我']:+.1f}")
    deshi = max(weight["得势下限"], min(weight["得势上限"], raw_deshi))

    score = round(deling + dedi + deshi, 2)
    if score >= STRENGTH_THRESHOLD["偏强"]:
        level = "偏强"
    elif score <= STRENGTH_THRESHOLD["偏弱"]:
        level = "偏弱"
    else:
        level = "中和"

    return {
        "level": level,
        "score": score,
        "detail": {
            "得令": round(deling, 2),
            "得地": round(dedi, 2),
            "得势": round(deshi, 2),
            "月支本气": f"{month_main['gan']}({month_main['element']}·{deling_relation})",
            "日支": day_branch,
            "根": "、".join(root_detail),
            "天干帮扶": "、".join(help_detail) if help_detail else "无",
        },
    }


# ---------------------------------------------------------------- 用神喜忌
def _god_of(element: str, percent: dict[str, int], reason: str) -> dict[str, Any]:
    return {
        "element": element,
        "label": f"{element} · {ELEMENT_PHRASE[element]}",
        "reason": reason,
        "percent": percent.get(element, 0),
        "color_key": ELEMENT_COLOR_KEY[element],
    }


def pick_gods(
    day_master_element: str,
    strength_level: str,
    percent: dict[str, int],
    top_n: int = 2,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """按「抑强扶弱」取喜用神与忌神。

    * 身偏强：喜我克（财）、我生（食伤）、克我（官杀）以耗泄克制，
      忌生我（印）、同我（比劫）；候选项按命局占比升序取前 N（越缺越喜）。
    * 身偏弱：喜生我（印）、同我（比劫）以扶身；忌克我、我生。
    * 中和：取生我与同我为喜用，取命局过旺者为忌。

    排序键为 ``(命局占比, 类别优先级)``，占比相同时按传统取用次序
    （财 > 食伤 > 官杀；印 > 比劫）优先。
    """
    if strength_level == "偏强":
        good_candidates = ["我克", "我生", "克我"]
        bad_candidates = ["生我", "同我"]
    else:  # 偏弱 / 中和 均以扶身为主
        good_candidates = ["生我", "同我"]
        bad_candidates = ["克我", "我生"]

    good: list[dict[str, Any]] = []
    for priority, relation in enumerate(good_candidates):
        for element in ELEMENT_ORDER:
            if relation_of(element, day_master_element) != relation:
                continue
            good.append(((percent.get(element, 0), priority), element, relation))
    good.sort(key=lambda item: item[0])
    favorable = [
        _god_of(element, percent, RELATION_LABEL[relation])
        for _, element, relation in good[:top_n]
    ]

    bad: list[dict[str, Any]] = []
    for priority, relation in enumerate(bad_candidates):
        for element in ELEMENT_ORDER:
            if relation_of(element, day_master_element) != relation:
                continue
            bad.append(((-percent.get(element, 0), priority), element, relation))
    bad.sort(key=lambda item: item[0])
    unfavorable = [
        _god_of(element, percent, RELATION_LABEL[relation])
        for _, element, relation in bad[:top_n]
    ]
    return favorable, unfavorable


def element_summary_of(day_gan: str, day_master_element: str, percent: dict[str, int]) -> str:
    """五行卡副标题，如「日主丙火 · 木旺缺金」。"""
    strongest = max(ELEMENT_ORDER, key=lambda e: percent.get(e, 0))
    weakest = min(ELEMENT_ORDER, key=lambda e: percent.get(e, 0))
    head = f"日主{day_gan}{day_master_element}"
    if percent.get(weakest, 0) > 0:
        return f"{head} · 五行均衡"
    # 约 2% 的命盘会有多个五行同时为 0，此处全列，避免只报一个让人误以为不缺
    missing = [e for e in ELEMENT_ORDER if percent.get(e, 0) == 0]
    return f"{head} · {strongest}旺缺{''.join(missing)}"


# ---------------------------------------------------------------- 主入口
def build_bazi(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int = 0,
    gender: str = "男",
    longitude: float = STANDARD_LONGITUDE,
    name: str = "",
) -> dict[str, Any]:
    """排出完整八字命盘。

    Args:
        year/month/day: 出生公历日期。
        hour/minute: 出生时的北京时间（钟表时间）。
        gender: 男 / 女，仅作档案回显。
        longitude: 出生地东经度数，用于真太阳时校正。
        name: 姓名，仅作档案回显。

    Returns:
        可直接序列化的命盘字典。

    Raises:
        ValueError: 日期非法或参数越界。
    """
    if gender not in ("男", "女"):
        raise ValueError("gender 只能是「男」或「女」")
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("hour/minute 超出合法范围")
    if not -180.0 <= float(longitude) <= 180.0:
        raise ValueError("longitude 应在 -180 ~ 180 之间")
    try:
        _dt.date(year, month, day)
    except ValueError as exc:
        raise ValueError(f"非法出生日期：{year}-{month}-{day}") from exc

    solar_cls = _require_solar()

    # 1) 真太阳时校正（经度时差）
    true_dt, offset_minutes = true_solar_time(
        year, month, day, hour, minute, longitude
    )

    # 2) 以校正后的时刻排盘：月柱按节气、日柱按日差、时柱按五鼠遁
    solar = solar_cls.fromYmdHms(
        true_dt.year, true_dt.month, true_dt.day,
        true_dt.hour, true_dt.minute, 0,
    )
    lunar = solar.getLunar()
    chart = lunar.getEightChar()
    pillars = _build_pillars(chart)

    # 3) 时辰与夜子时标记（一律以真太阳时为准，保证与排盘所用的时柱一致）
    hour_branch = hour_branch_of(true_dt.hour)
    is_night_zi = true_dt.hour == 23
    # 夜子时下排盘库会拼出「当日日柱 + 次日时干」的不自洽组合，这里先修正，
    # 后续五行占比与强弱判定才能基于正确的时柱计算
    apply_night_zi_fix(pillars, is_night_zi)

    # 4) 五行占比
    scores = score_elements(pillars)
    percent = to_percent(scores)

    # 5) 日主强弱与喜忌
    day_pillar = pillars[2]
    day_master_element = STEM_ELEMENT[day_pillar["gan"]]
    strength = judge_strength(pillars, day_master_element)
    favorable, unfavorable = pick_gods(
        day_master_element, strength["level"], percent
    )

    prev_term = lunar.getPrevJieQi()
    next_term = lunar.getNextJieQi()

    return {
        "birth": {
            "name": name,
            "gender": gender,
            "longitude": round(float(longitude), 4),
            "solar": f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}",
            "true_solar": true_dt.strftime("%Y-%m-%d %H:%M"),
            "offset_minutes": offset_minutes,
            "hour_zhi": hour_branch,
            "is_night_zi": is_night_zi,
            "solar_term_range": f"{prev_term.getName()}后 · {next_term.getName()}前",
            # 副标题取真太阳时的日期与时辰：命盘本就按真太阳时排，二者保持一致
            "summary": (
                f"{true_dt.year:04d}.{true_dt.month:02d}.{true_dt.day:02d}"
                f" {hour_branch}时 · {gender}"
            ),
        },
        "day_master": {
            "gan": day_pillar["gan"],
            "zhi": day_pillar["zhi"],
            "element": day_master_element,
            "pillar": day_pillar["pillar"],
        },
        "pillars": pillars,
        "elements": [
            {
                "element": element,
                "percent": percent.get(element, 0),
                "score": scores.get(element, 0.0),
                "color_key": ELEMENT_COLOR_KEY[element],
            }
            for element in ELEMENT_ORDER
        ],
        "element_summary": element_summary_of(
            day_pillar["gan"], day_master_element, percent
        ),
        "strength": strength,
        "favorable": favorable,
        "unfavorable": unfavorable,
    }


def enhance(profile: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """大模型文案增强钩子（MVP 未启用）。

    接入方式（与 advice.enhance 一致）：
        1. 用 context（四柱、五行、强弱）构造 prompt；
        2. 以 JSON mode 强制模型只输出用神喜忌的 **解释文案**；
        3. 校验 schema 后回写文案字段，任何数值字段一律以入参为准，不采信模型输出。
    未配置模型时原样返回，保证链路可用。
    """
    return profile
