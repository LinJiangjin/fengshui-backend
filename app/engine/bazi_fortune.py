# -*- coding: utf-8 -*-
"""八字大运与流年（确定性计算层）。

与 :mod:`app.engine.bazi` 同一条铁律：**数值由代码算，文案是确定性映射**，
不调用大模型。同一份命盘永远得到同一份结论。

规则与口径
----------
* **起运**：以出生时刻（**真太阳时**）为准，阳男阴女**顺行**数到下一个「节」，
  阴男阳女**逆行**数到上一个「节」；相隔天数按「三天为一岁、一天为四个月」
  折算成起运年龄。这里的「节」是二十四节气里的**十二节**（立春、惊蛰……
  小寒），**不含中气**——与 :func:`app.engine.xuankong.jieqi_month_of` 同一口径。
  起运一定在出生之后：顺行与逆行只是「数到哪个节」不同，折出的岁数都往后加。
* **大运干支**：自**月柱**起顺推（顺行）或逆推（逆行），每运十年。
* **流年干支**：``(year - 4) % 60``，与紫微流年
  :func:`app.engine.ziwei_year.gan_zhi_of_year` 共用同一个函数，不另写一份。
* **地支关系**：只判有明确定义的两两关系——六冲 / 六合 / 六害 / 三刑（含自刑）。
  三合需三支齐全才成立，单看一支与另一支只能算「半合」，流派口径不一，
  这里**不判**，避免把不确定的东西当结论下发。

能做什么 / 不做什么
--------------------
* **能**：这一步大运是什么天时、流年干支与命局哪一支冲合、宜动宜守的倾向。
* **不做**：不预测「某年结婚 / 升职 / 生病」这类具体事件。命理给的是倾向
  而非必然；涉及健康只作「宜规律作息、按时体检」这类提醒，不作诊断。

文案约定
--------
命理行话一律**就地解释**：出现「伤官」就同一条内说明它代表什么，
不留未解释的名词。每段另给一句 ``plain`` 白话导语。
"""

from __future__ import annotations

import calendar
import datetime as _dt
from typing import Any

try:  # pragma: no cover - 依赖缺失时不影响其它引擎模块被导入
    from lunar_python import Solar
except ImportError as _exc:  # pragma: no cover
    Solar = None  # type: ignore[assignment]
    _IMPORT_ERROR: Exception | None = _exc
else:
    _IMPORT_ERROR = None

from .bazi import jiazi_index, na_yin_of, relation_of, shi_shen_of
from .constants import (
    BAZI_YEAR_COUNT,
    BRANCH_CLASH,
    BRANCH_HARM,
    BRANCH_HE,
    BRANCH_PUNISH_GROUPS,
    BRANCH_RELATION_PLAIN,
    BRANCH_SELF_PUNISH,
    DA_YUN_DAYS_PER_YEAR,
    DA_YUN_MONTHS_PER_DAY,
    DA_YUN_SPAN,
    DA_YUN_STEPS,
    EARTHLY_BRANCHES,
    HEAVENLY_STEMS,
    SHI_SHEN_FIELD,
    STEM_ELEMENT,
    STEM_YIN_YANG,
)
from .ziwei_year import gan_zhi_of_year

__all__ = [
    "build_bazi_fortune",
    "build_bazi_years",
    "da_yun_of",
    "da_yun_forward_of",
    "gan_zhi_of_year",
]

# 十神白话：命理行话一律就地解释，不留未解释的名词
SHI_SHEN_PLAIN = {
    "比肩": "跟你同类的力量——同辈、合伙，也意味着凡事更多要靠自己",
    "劫财": "跟你同类但带竞争性——机会多、花销也多，钱容易左手进右手出",
    "食神": "你生出来的东西——才华、产出，也代表稳定而温和的回报",
    "伤官": "你生出来的锋利部分——想法多、表达强，也容易不服管、起变动",
    "偏财": "你能支配的流动之财——机会财、人脉财、非固定收入",
    "正财": "你能支配的稳定之财——工资、积蓄这类看得见的收入",
    "七杀": "压着你的力量——压力与考验集中，扛过去就是魄力",
    "正官": "管着你的力量——规则、名分、上级与责任，讲秩序才有收获",
    "偏印": "生你的偏门力量——学习、冷门技能，也容易想得多、钻牛角尖",
    "正印": "生你的正统力量——贵人、文凭、靠山，也代表安全感",
}

# 同一柱上可能同时命中多种关系（如寅巳既是害又是刑），
# 展示时只取最重的那一种，避免一条塞满四个字让用户无从判断
_RELATION_ORDER = ("冲", "刑", "害", "合")

_RELATION_TABLES = (
    ("冲", BRANCH_CLASH),
    ("害", BRANCH_HARM),
    ("合", BRANCH_HE),
)


def _require_solar() -> Any:
    """返回 lunar-python 的 Solar 类，未安装时给出明确的安装提示。"""
    if Solar is None:  # pragma: no cover
        raise RuntimeError(
            "缺少排盘依赖 lunar-python，请执行：pip install lunar-python"
        ) from _IMPORT_ERROR
    return Solar


def _solar_to_datetime(solar: Any) -> _dt.datetime:
    """lunar-python 的 Solar -> datetime。"""
    ymd, hms = solar.toYmdHms().split(" ")
    y, m, d = (int(x) for x in ymd.split("-"))
    hh, mm, ss = (int(x) for x in hms.split(":"))
    return _dt.datetime(y, m, d, hh, mm, ss)


def _walk_jie(moment: _dt.datetime, forward: bool) -> tuple[str, _dt.datetime]:
    """从 ``moment`` 顺 / 逆找最近一个「节」。

    ``getNextJieQi()`` / ``getPrevJieQi()`` 返回的是**节气**（含中气），
    必须逐个跳过中气直到 ``isJie()`` 为真；跨年时会自然落到相邻年的节上
    （如 1991-12-20 顺行得 1992 年的小寒）。
    """
    solar_cls = _require_solar()
    cursor = solar_cls.fromYmdHms(
        moment.year, moment.month, moment.day, moment.hour, moment.minute, 0
    )
    for _ in range(4):
        lunar = cursor.getLunar()
        jq = lunar.getNextJieQi() if forward else lunar.getPrevJieQi()
        if jq.isJie():
            return jq.getName(), _solar_to_datetime(jq.getSolar())
        # 是中气就跨过它继续找：进 / 退一天，避开该节气时刻自身
        cursor = jq.getSolar().next(1 if forward else -1)
    raise RuntimeError(f"找不到 {moment.isoformat()} 附近的节")  # pragma: no cover


def da_yun_forward_of(year_gan: str, gender: str) -> bool:
    """大运顺逆：**阳男阴女顺行，阴男阳女逆行**。

    阳年干 = 甲丙戊庚壬；「顺」指从出生时刻往后数到下一个节。

    名字带 ``da_yun_`` 前缀：玄空那边已有一个 ``forward_of``（判山向飞星顺逆），
    两者同名会在 ``engine/__init__.py`` 里互相覆盖，必须区分开。
    """
    if gender not in ("男", "女"):
        raise ValueError("gender 只能是「男」或「女」")
    if year_gan not in STEM_YIN_YANG:
        raise ValueError(f"非法年干：{year_gan}")
    return (STEM_YIN_YANG[year_gan] == "阳") == (gender == "男")


def _add_months(base: _dt.date, years: int, months: int) -> _dt.date:
    """在 ``base`` 上加 ``years`` 年 ``months`` 个月，日号超出月末则取月末。"""
    month = base.month + months
    year = base.year + years
    while month > 12:
        month -= 12
        year += 1
    while month < 1:
        month += 12
        year -= 1
    day = min(base.day, calendar.monthrange(year, month)[1])
    return _dt.date(year, month, day)


def _da_yun_step_plain(
    gan_zhi: str, shi_shen: str, from_age: int, to_age: int,
    from_year: int, to_year: int,
) -> str:
    """一步大运的白话：它是什么、对日主意味着什么、管多少年。"""
    field = SHI_SHEN_FIELD.get(shi_shen, "整体")
    plain = SHI_SHEN_PLAIN.get(shi_shen, "")
    return (
        f"{gan_zhi}运（{from_age}-{to_age} 岁，约 {from_year}-{to_year} 年）："
        f"这十年的天时对日主来说是「{shi_shen}」，主{field}"
        + (f"——{plain}。" if plain else "。")
    )


def da_yun_of(
    profile: dict[str, Any],
    true_dt: _dt.datetime,
    birth_year: int,
    today: _dt.date | None = None,
) -> dict[str, Any]:
    """排大运：起运岁数 + 八步运程。

    Args:
        profile: :func:`app.engine.bazi.build_bazi` 的命盘。
        true_dt: 出生时刻的**真太阳时**（排盘与起运必须用同一时刻，否则
            出生在交节附近的人会算出两套结果）。
        birth_year: 公历出生年，用于定「当前几岁、走到第几步」。
        today: 仅用于测试注入「今天」，默认取系统日期。

    Returns:
        可直接序列化的大运字典。
    """
    pillars = profile["pillars"]
    gender = profile["birth"]["gender"]
    year_gan = pillars[0]["gan"]
    month_pillar = pillars[1]
    day_gan = profile["day_master"]["gan"]

    forward = da_yun_forward_of(year_gan, gender)

    # 1) 数到最近的「节」，把相隔天数折成起运年龄
    jie_name, jie_dt = _walk_jie(true_dt, forward)
    gap_days = int(abs((jie_dt - true_dt).total_seconds()) // 86400)
    start_age = gap_days // DA_YUN_DAYS_PER_YEAR
    start_months = (gap_days % DA_YUN_DAYS_PER_YEAR) * DA_YUN_MONTHS_PER_DAY
    start_date = _add_months(true_dt.date(), start_age, start_months)
    start_year = start_date.year

    # 2) 自月柱顺 / 逆推八步
    month_idx = jiazi_index(month_pillar["gan"], month_pillar["zhi"])
    steps: list[dict[str, Any]] = []
    for i in range(DA_YUN_STEPS):
        offset = i + 1
        idx = (month_idx + offset) % 60 if forward else (month_idx - offset) % 60
        gan = HEAVENLY_STEMS[idx % 10]
        zhi = EARTHLY_BRANCHES[idx % 12]
        from_age = start_age + i * DA_YUN_SPAN
        to_age = from_age + DA_YUN_SPAN - 1
        from_year = start_year + i * DA_YUN_SPAN
        to_year = from_year + DA_YUN_SPAN - 1
        shi_shen = shi_shen_of(day_gan, gan)
        steps.append({
            "index": i,
            "gan_zhi": gan + zhi,
            "gan": gan,
            "zhi": zhi,
            "element": STEM_ELEMENT[gan],
            "shi_shen": shi_shen,
            "na_yin": na_yin_of(gan, zhi),
            "field": SHI_SHEN_FIELD.get(shi_shen, "整体"),
            # 字段名避开 Python 关键字：JSON 里是 from_age / to_age，不是 from / to
            "from_age": from_age,
            "to_age": to_age,
            "from_year": from_year,
            "to_year": to_year,
            "is_current": False,
            "plain": _da_yun_step_plain(
                gan + zhi, shi_shen, from_age, to_age, from_year, to_year
            ),
        })

    # 3) 标出当前这一步；未入运（童限）时 step 为 None，按传统以月柱看
    today = today or _dt.date.today()
    age = today.year - birth_year
    current: dict[str, Any] | None = None
    if age >= start_age:
        k = min((age - start_age) // DA_YUN_SPAN, len(steps) - 1)
        steps[k]["is_current"] = True
        current = steps[k]

    basis = (
        f"{'阳' if STEM_YIN_YANG[year_gan] == '阳' else '阴'}年{gender}命，"
        f"{'顺行，数到出生后的下一个节' if forward else '逆行，数到出生前的上一个节'}"
        f"「{jie_name}」，相隔 {gap_days} 天 —— 按三天折一岁，"
        f"{start_age} 岁{start_months} 个月起运（约 {start_date.isoformat()}）。"
    )
    if current is None:
        plain = (
            f"你 {age} 周岁，还没到起运年龄（{start_age} 岁起运），"
            f"这段按传统看月柱「{month_pillar['pillar']}」的气色。"
        )
    else:
        plain = (
            f"你 {age} 周岁，正走第 {current['index'] + 1} 步大运"
            f"「{current['gan_zhi']}」"
            f"（{current['from_age']}-{current['to_age']} 岁）；"
            f"这十年的天时对日主来说是「{current['shi_shen']}」，"
            f"主{current['field']}。"
        )

    return {
        "forward": forward,
        "jie_name": jie_name,
        "jie_at": jie_dt.strftime("%Y-%m-%d %H:%M"),
        "gap_days": gap_days,
        "start_age": start_age,
        "start_months": start_months,
        "start_date": start_date.isoformat(),
        "start_year": start_year,
        "age": age,
        "basis": basis,
        "plain": plain,
        "steps": steps,
        "current": current,
    }


def _branch_relations(zhi: str, pillars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """流年地支与命局四支的关系，每柱只取最重的一种。"""
    out: list[dict[str, Any]] = []
    for pillar in pillars:
        target = pillar["zhi"]
        hits: list[str] = []
        for kind, table in _RELATION_TABLES:
            if table.get(zhi) == target:
                hits.append(kind)
        if target != zhi:
            for group in BRANCH_PUNISH_GROUPS:
                if zhi in group and target in group:
                    hits.append("刑")
                    break
        elif zhi in BRANCH_SELF_PUNISH:
            hits.append("刑")
        if not hits:
            continue
        kind = next(k for k in _RELATION_ORDER if k in hits)
        out.append({
            "kind": kind,
            "palace": pillar["name"],
            "branch": target,
            "plain": BRANCH_RELATION_PLAIN[kind],
        })
    return out[:3]


def _year_points(
    year: int, gan_zhi: str, shi_shen: str, age: int,
    step: dict[str, Any] | None, start_age: int,
    relations: list[dict[str, Any]], tian_ke_di_chong: bool,
    stance: str,
) -> list[str]:
    """流年逐条结论。行话一律就地解释。"""
    points: list[str] = [
        f"{year} {gan_zhi}年：这一年的天干对日主来说是「{shi_shen}」——"
        f"{SHI_SHEN_PLAIN.get(shi_shen, '代表当年的主旋律')}，"
        f"所以这一年的主题偏「{SHI_SHEN_FIELD.get(shi_shen, '整体')}」。",
    ]
    if step is None:
        points.append(
            f"你这一年 {age} 周岁，还没到起运年龄（{start_age} 岁起运），"
            f"流年按传统只看命局本身，不叠大运。"
        )
    else:
        points.append(
            f"大运仍在第 {step['index'] + 1} 步「{step['gan_zhi']}」"
            f"（{step['from_age']}-{step['to_age']} 岁）之内，"
            f"流年是在这十年天时之上再叠一层当年的变化。"
        )

    if tian_ke_di_chong:
        points.append(
            f"这一年与你的日柱「天克地冲」（天干相克、地支又正冲）——"
            f"传统上认为这是变动最集中的年份，宜守不宜攻，"
            f"重大决定缓一步，先把身体和手上的事稳住。"
        )
    for rel in relations:
        points.append(
            f"流年地支与你的{rel['palace']}（{rel['branch']}）相{rel['kind']}——"
            f"{rel['plain']}，所以{rel['palace']}这一块今年最容易被牵动。"
        )
    points.append(f"整体看，这一年{stance}。")
    return points


def build_bazi_years(
    profile: dict[str, Any],
    da_yun: dict[str, Any],
    birth_year: int,
    start_year: int | None = None,
    count: int = BAZI_YEAR_COUNT,
) -> list[dict[str, Any]]:
    """在八字命盘上逐年推流年，给出每一年的主题与宜动宜守倾向。

    Args:
        profile: :func:`app.engine.bazi.build_bazi` 的命盘。
        da_yun: :func:`da_yun_of` 的结果（提供起运岁数与八步运程）。
        birth_year: 公历出生年。
        start_year: 起始年份，默认取今年。
        count: 推几年，默认 12 —— 大运十年一换，12 年能保证至少跨过一次
            换运，10 年有可能整窗都卡在同一运里、也可能刚好错过换运点。

    Returns:
        逐年列表，可直接序列化。
    """
    pillars = profile["pillars"]
    day_gan = profile["day_master"]["gan"]
    day_zhi = profile["day_master"]["zhi"]
    day_element = profile["day_master"]["element"]
    favorable = {g["element"] for g in profile["favorable"]}
    unfavorable = {g["element"] for g in profile["unfavorable"]}
    start_age = da_yun["start_age"]
    steps = da_yun["steps"]

    first_year = start_year or _dt.date.today().year
    years: list[dict[str, Any]] = []

    for year in range(first_year, first_year + count):
        gan_zhi = gan_zhi_of_year(year)
        gan, zhi = gan_zhi[0], gan_zhi[1]
        age = year - birth_year
        gan_element = STEM_ELEMENT[gan]

        # 1) 所属大运与是否换运
        if age < start_age:
            step: dict[str, Any] | None = None
            is_switch = False
        else:
            k = min((age - start_age) // DA_YUN_SPAN, len(steps) - 1)
            step = steps[k]
            is_switch = (age - start_age) % DA_YUN_SPAN == 0

        # 2) 流年天干十神（相对日主）
        shi_shen = shi_shen_of(day_gan, gan)

        # 3) 流年地支与命局四支的关系
        relations = _branch_relations(zhi, pillars)

        # 4) 天克地冲：流年天干克日干、且流年地支冲日支
        gan_ke_day = relation_of(gan_element, day_element) == "克我"
        tian_ke_di_chong = gan_ke_day and BRANCH_CLASH.get(zhi) == day_zhi

        # 5) 流年天干五行是否踩在喜用 / 忌神上
        favorable_hit = gan_element in favorable
        unfavorable_hit = gan_element in unfavorable

        if tian_ke_di_chong or unfavorable_hit:
            stance = "宜守成"
        elif favorable_hit and not any(r["kind"] == "冲" for r in relations):
            stance = "宜主动"
        else:
            stance = "稳中求进"

        # 6) 重点领域：十神为主，叠加被冲的那一柱
        focus_parts = [SHI_SHEN_FIELD.get(shi_shen, "整体")]
        for rel in relations:
            if rel["kind"] == "冲":
                mark = f"{rel['palace']}有变"
                if mark not in focus_parts:
                    focus_parts.append(mark)
        focus = " · ".join(focus_parts)

        if is_switch and step is not None:
            # 第 0 步是「入运」不是「换运」，两者对用户含义不同，别混着说
            verb = "开始走第一步大运（入运）" if step["index"] == 0 else "换大运"
            plain = (
                f"你这一年 {age} 周岁，{verb}——走进第 {step['index'] + 1} 步"
                f"「{step['gan_zhi']}」（{step['from_age']}-{step['to_age']} 岁）；"
                f"当年主题偏「{SHI_SHEN_FIELD.get(shi_shen, '整体')}」，"
                f"整体{stance}。换运年本身就要多一分稳。"
            )
        elif step is None:
            plain = (
                f"你这一年 {age} 周岁，尚未入运（{start_age} 岁起运），"
                f"当年主题偏「{SHI_SHEN_FIELD.get(shi_shen, '整体')}」，"
                f"整体{stance}。"
            )
        else:
            plain = (
                f"你这一年 {age} 周岁，仍在第 {step['index'] + 1} 步大运"
                f"「{step['gan_zhi']}」之内；当年主题偏"
                f"「{SHI_SHEN_FIELD.get(shi_shen, '整体')}」，整体{stance}。"
            )

        years.append({
            "year": year,
            "gan_zhi": gan_zhi,
            "age": age,
            "shi_shen": shi_shen,
            "shi_shen_plain": SHI_SHEN_PLAIN.get(shi_shen, ""),
            "da_yun": None if step is None else {
                "index": step["index"],
                "gan_zhi": step["gan_zhi"],
                "from_age": step["from_age"],
                "to_age": step["to_age"],
            },
            "is_da_yun_switch": is_switch,
            "relations": relations,
            "tian_ke_di_chong": tian_ke_di_chong,
            "favorable_hit": favorable_hit,
            "unfavorable_hit": unfavorable_hit,
            "focus": focus,
            "stance": stance,
            "plain": plain,
            "points": _year_points(
                year, gan_zhi, shi_shen, age, step, start_age,
                relations, tian_ke_di_chong, stance,
            ),
        })

    return years


def build_bazi_fortune(
    profile: dict[str, Any],
    true_dt: _dt.datetime,
    birth_year: int,
    start_year: int | None = None,
    count: int = BAZI_YEAR_COUNT,
    today: _dt.date | None = None,
) -> dict[str, Any]:
    """算出大运与流年，供路由合进八字响应。

    Args:
        profile: :func:`app.engine.bazi.build_bazi` 的命盘。
        true_dt: 出生时刻的真太阳时（必须与排盘所用时刻一致）。
        birth_year: 公历出生年。
        start_year: 流年起始年，默认今年。
        count: 流年条数，默认 12。
        today: 仅用于测试注入「今天」。

    Returns:
        ``{"da_yun": ..., "years": [...]}``
    """
    da_yun = da_yun_of(profile, true_dt, birth_year, today=today)
    years = build_bazi_years(
        profile, da_yun, birth_year, start_year=start_year, count=count
    )
    return {"da_yun": da_yun, "years": years}
