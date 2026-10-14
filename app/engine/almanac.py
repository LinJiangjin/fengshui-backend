# -*- coding: utf-8 -*-
"""黄历 · 通书与择日。

与玄空、八宅不同，黄历的历法数据**不是自研规则**，而是天文历法事实，
因此全部取自 ``lunar-python``：

* 农历日期、年月日干支、旬空
* 建除十二神（getZhiXing）、日家十二天神（getDayTianShen*）
* 二十八宿（getXiu / getXiuLuck）、冲煞（getDayChong* / getDaySha）
* 每日宜忌（getDayYi / getDayJi）、吉神凶煞（getDayJiShen / getDayXiongSha）
* 彭祖百忌、五神方位（喜神 / 福神 / 财神 / 阳贵 / 阴贵）
* 十三时辰的黄黑道、时宜时忌（getTimes）

``engine/constants.py`` 只提供「词表含义 + 吉凶分档 + 打分权重」，不参与历法推算。

**择日**是本模块的增值部分：把某一事项需要的关键宜项（如装修开工的
「动土、修造、上梁」）与当日的宜忌、建除档位、日天神、宿曜、黄道吉时数
综合成 0-100 分，并**逐条给出加减分理由**——分数必须可解释，否则用户
无法判断该不该信。冲用户生肖的日子额外扣分并在结果里显式标注。

兼容性：缺失 ``lunar-python`` 时无法取得历法数据，此处直接抛
``RuntimeError``，由路由层转成 503；不做「用近似值冒充通书」的兜底。
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Iterable, Optional

try:
    from lunar_python import Solar
except ImportError:  # pragma: no cover - 依赖缺失时明确报错，不静默降级
    Solar = None  # type: ignore[assignment]

from .constants import (
    ALMANAC_ACTIVITIES,
    ALMANAC_LEVELS,
    ALMANAC_RULES_VERSION,
    ALMANAC_SCORE,
    ALMANAC_SELECT_MAX_DAYS,
    FIVE_GOD_KEYS,
    JIANCHU_INFO,
    JIANCHU_MNEMONIC,
    TIAN_SHEN_INFO,
    WEEKDAY_NAMES,
    XIU_INFO,
    ZODIACS,
)
from .daily_star import daily_chart, solar_term_range_of
from .lunar_cache import INSTALLED as _LUNAR_YEAR_CACHE  # noqa: F401  装多年份历法表缓存

__all__ = [
    "ACTIVITIES_BY_KEY",
    "activity_of",
    "day_almanac",
    "day_score",
    "list_activities",
    "month_overview",
    "parse_date",
    "resolve_day",
    "select_dates",
]

_LUNAR_MISSING = (
    "黄历依赖 lunar-python 历法库，当前环境未安装，无法推算通书数据"
)

# 事项 key -> 定义，供路由层做 O(1) 校验
ACTIVITIES_BY_KEY: dict[str, dict[str, Any]] = {
    item["key"]: item for item in ALMANAC_ACTIVITIES
}


# ---------------------------------------------------------------- 历法取值
def _lunar(date: _dt.date):
    """取农历对象；缺依赖时抛错，不静默降级成近似值。"""
    if Solar is None:
        raise RuntimeError(_LUNAR_MISSING)
    return Solar.fromYmd(date.year, date.month, date.day).getLunar()


def _safe(fn, default=None):
    """历法字段取值容错：个别日期在某些版本上可能缺字段，缺失就返回默认值。"""
    try:
        return fn()
    except Exception:  # pragma: no cover - 历法库字段差异
        return default


def _clean_terms(raw: Optional[Iterable[str]]) -> list[str]:
    """清洗宜忌词条。

    ``lunar-python`` 在「当日无事可为」时会给一个字面量 ``无``；把它当词条
    展示毫无意义，这里剔除，真正的「诸事不宜」由 ``all_avoid`` 单独标记。
    """
    if not raw:
        return []
    return [term for term in raw if term and term != "无"]


def parse_date(text: Optional[str]) -> Optional[_dt.date]:
    """把 ``YYYY-MM-DD`` 解析成日期；空串与 None 返回 None。

    刻意用 ``strptime`` 而不是 ``date.fromisoformat``：后者从 Python 3.11 起
    还接受 ``20261014``（基本格式）与 ``2026-W01-1``（ISO 周格式），
    接口对外只承诺 ``YYYY-MM-DD``，宽松解析会让非预期输入静默变成另一个日期。
    """
    if not text or not text.strip():
        return None
    value = text.strip()
    try:
        return _dt.datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"日期格式应为 YYYY-MM-DD，收到：{value}") from exc


def resolve_day(date: Optional[str]) -> _dt.date:
    """请求日期；未提供则取今天。"""
    return parse_date(date) or _dt.date.today()


# ---------------------------------------------------------------- 单日通书
def _hours_of(lunar) -> list[dict[str, Any]]:
    """十三时辰的黄黑道与宜忌。

    ``lunar-python`` 把子时拆成「早子时」（00:00-00:59）与「晚子时」
    （23:00-23:59），两者干支与吉凶并不相同（夜子时换日流派差异）。
    这里**保留 13 项并显式标注早 / 晚**，不合并——合并必须二选一，
    等于替用户决定流派，不如把事实摊开。
    """
    hours: list[dict[str, Any]] = []
    for index, hour in enumerate(_safe(lunar.getTimes) or []):
        branch = hour.getZhi()
        slot_label = f"{branch}时"
        if branch == "子":
            slot_label = "子时（早）" if index == 0 else "子时（晚）"
        hour_type = _safe(hour.getTianShenType, "")
        hours.append(
            {
                "index": index,
                "branch": branch,
                "label": f"{branch}时",
                "slot_label": slot_label,
                "range": f"{_safe(hour.getMinHm, '')}–{_safe(hour.getMaxHm, '')}",
                "gan_zhi": _safe(hour.getGanZhi, ""),
                "na_yin": _safe(hour.getNaYin, ""),
                "tian_shen": _safe(hour.getTianShen, ""),
                "tian_shen_type": hour_type,
                "luck": _safe(hour.getTianShenLuck, ""),
                "is_lucky": hour_type == "黄道",
                "chong": {
                    "zodiac": _safe(hour.getChongShengXiao, ""),
                    "desc": _safe(hour.getChongDesc, ""),
                },
                "cai_direction": _safe(hour.getPositionCaiDesc, ""),
                "yi": _clean_terms(_safe(hour.getYi, [])),
                "ji": _clean_terms(_safe(hour.getJi, [])),
            }
        )
    return hours


def _jian_chu(name: str) -> dict[str, Any]:
    info = JIANCHU_INFO.get(name)
    if info is None:
        # 建除为固定十二循环，出现未知值说明历法库口径变了，如实暴露而非编造
        return {
            "name": name,
            "label": f"{name}日",
            "tone": "",
            "meaning": "",
            "good": "",
            "bad": "",
            "motto": JIANCHU_MNEMONIC,
        }
    return {
        "name": name,
        "label": f"{name}日",
        "tone": info["tone"],
        "meaning": info["meaning"],
        "good": info["good"],
        "bad": info["bad"],
        "motto": JIANCHU_MNEMONIC,
    }


def _tian_shen(name: str, fallback_type: str, fallback_luck: str) -> dict[str, Any]:
    info = TIAN_SHEN_INFO.get(name) or {}
    return {
        "name": name,
        # 历法库的判定优先，常量表仅作缺失时的兜底
        "type": fallback_type or info.get("type", ""),
        "luck": fallback_luck or info.get("luck", ""),
        "meaning": info.get("meaning", ""),
    }


def _xiu(name: str, fallback_luck: str) -> dict[str, Any]:
    info = XIU_INFO.get(name) or {}
    return {
        "name": name,
        "full": info.get("full", ""),
        "animal": info.get("animal", ""),
        "mansion": info.get("mansion", ""),
        "luck": fallback_luck or info.get("luck", ""),
    }


def _five_gods(lunar) -> list[dict[str, str]]:
    """五神方位：喜神 / 福神 / 财神 / 阳贵 / 阴贵（由日干推得）。"""
    getters = {
        "xi": lunar.getDayPositionXiDesc,
        "fu": lunar.getDayPositionFuDesc,
        "cai": lunar.getDayPositionCaiDesc,
        "yang_gui": lunar.getDayPositionYangGuiDesc,
        "yin_gui": lunar.getDayPositionYinGuiDesc,
    }
    return [
        {"key": key, "name": label, "direction": _safe(getters[key], "")}
        for key, label in FIVE_GOD_KEYS
    ]


def day_almanac(date: _dt.date) -> dict[str, Any]:
    """一日的通书内容：历法、建除、天神、宿曜、冲煞、宜忌、时辰、紫白。"""
    lunar = _lunar(date)
    yi = _clean_terms(_safe(lunar.getDayYi, []))
    ji = _clean_terms(_safe(lunar.getDayJi, []))
    all_avoid = "诸事不宜" in (_safe(lunar.getDayJi, []) or [])

    hours = _hours_of(lunar)
    lucky_hours = [h for h in hours if h["is_lucky"]]

    # 日家紫白复用既有引擎：入中星与今日吉位 / 忌方
    chart = daily_chart(date)
    purple_white = {
        "center_star": chart["center_star"],
        "center_star_name": chart["center_star_name"],
        "escape": chart["escape"],
        "escape_desc": chart["escape_desc"],
        "yuan": chart["yuan"],
        "best": chart["best"],
        "worst": chart["worst"],
        "calendar_exact": chart["calendar_exact"],
    }

    jian_chu = _jian_chu(_safe(lunar.getZhiXing, ""))
    tian_shen = _tian_shen(
        _safe(lunar.getDayTianShen, ""),
        _safe(lunar.getDayTianShenType, ""),
        _safe(lunar.getDayTianShenLuck, ""),
    )
    xiu = _xiu(_safe(lunar.getXiu, ""), _safe(lunar.getXiuLuck, ""))

    almanac = {
        "date": date.isoformat(),
        "weekday": WEEKDAY_NAMES[date.weekday()],
        "weekday_index": date.weekday(),
        "lunar": {
            "text": _safe(lunar.toString, ""),
            "year": _safe(lunar.getYearInChinese, ""),
            "month": f"{_safe(lunar.getMonthInChinese, '')}月",
            "day": _safe(lunar.getDayInChinese, ""),
            "is_leap": bool(_safe(lunar.getMonth, 0) < 0),
        },
        "gan_zhi": {
            "year": _safe(lunar.getYearInGanZhi, ""),
            "month": _safe(lunar.getMonthInGanZhi, ""),
            "day": _safe(lunar.getDayInGanZhi, ""),
            "year_animal": _safe(lunar.getYearShengXiao, ""),
            "month_animal": _safe(lunar.getMonthShengXiao, ""),
            "day_animal": _safe(lunar.getDayShengXiao, ""),
        },
        "xun": {
            "name": _safe(lunar.getDayXun, ""),
            "kong": _safe(lunar.getDayXunKong, ""),
        },
        "solar_term": _safe(lunar.getJieQi, "") or "",
        "solar_term_range": solar_term_range_of(date),
        "jian_chu": jian_chu,
        "tian_shen": tian_shen,
        "xiu": xiu,
        "chong": {
            "zodiac": _safe(lunar.getDayChongShengXiao, ""),
            "desc": _safe(lunar.getDayChongDesc, ""),
            "sha": _safe(lunar.getDaySha, ""),
        },
        "na_yin": _safe(lunar.getDayNaYin, ""),
        "yi": yi,
        "ji": ji,
        "all_avoid": all_avoid,
        "ji_shen": _safe(lunar.getDayJiShen, []) or [],
        "xiong_sha": _safe(lunar.getDayXiongSha, []) or [],
        "peng_zu": {
            "gan": _safe(lunar.getPengZuGan, "") or "",
            "zhi": _safe(lunar.getPengZuZhi, "") or "",
        },
        "five_gods": _five_gods(lunar),
        "hours": hours,
        "lucky_hours": lucky_hours,
        "unlucky_hours": [h for h in hours if not h["is_lucky"]],
        "purple_white": purple_white,
        "rules_version": ALMANAC_RULES_VERSION,
    }

    # 不带事项的「当日总体」评分：只看建除 / 天神 / 宿曜 / 吉时 / 诸事不宜
    scored = day_score(almanac)
    almanac["score"] = scored["value"]
    almanac["level"] = scored["level"]
    almanac["tone"] = scored["tone"]
    almanac["score_reasons"] = scored["reasons"]
    return almanac


# ---------------------------------------------------------------- 打分
def _level_of(value: int) -> tuple[str, str]:
    for threshold, label, tone in ALMANAC_LEVELS:
        if value >= threshold:
            return label, tone
    return ALMANAC_LEVELS[-1][1], ALMANAC_LEVELS[-1][2]


def day_score(
    almanac: dict[str, Any],
    activity: Optional[dict[str, Any]] = None,
    zodiac: str = "",
) -> dict[str, Any]:
    """给一日打分。

    ``activity`` 为空表示「当日总体吉凶」，只看通用项；给了事项则额外按
    该事项的宜忌词表命中加减分。返回的 ``reasons`` 是逐条依据，前端直接
    展示——用户看不到理由的分数没有意义。
    """
    cfg = ALMANAC_SCORE
    value = cfg["base"]
    reasons: list[str] = []
    hits: list[str] = []
    misses: list[str] = []

    if activity:
        terms = activity["terms"]
        # 命中的宜项在词表中出现顺序即优先级，保持稳定不依赖集合顺序
        hits = [term for term in terms if term in (almanac["yi"] or [])]
        misses = [term for term in terms if term in (almanac["ji"] or [])]

        if hits:
            # 按词表位置加权：核心工序（靠前）比辅助工序更能定性
            raw = 0
            for term in hits:
                weight = cfg["hit_head"] - cfg["hit_decay"] * terms.index(term)
                raw += max(cfg["hit_floor"], weight)
            bonus = min(raw, cfg["hit_cap"])
            value += bonus
            reasons.append(f"宜「{'、'.join(hits)}」，与「{activity['name']}」相符（+{bonus}）")
        else:
            # 择日的硬要求是「事项入宜」：仅仅「不忌」不足以定吉日，
            # 否则建除 / 宿曜吉的日子会被误报成该事项的专宜之日。
            value += cfg["no_hit"]
            reasons.append(
                f"当日宜项未含「{activity['name']}」所需事项，非专宜之日（{cfg['no_hit']}）"
            )

        if misses:
            penalty = cfg["miss_first"] + cfg["miss_more"] * (len(misses) - 1)
            penalty = max(penalty, cfg["miss_cap"])
            value += penalty
            reasons.append(f"忌「{'、'.join(misses)}」，与「{activity['name']}」相冲（{penalty}）")

    jian_chu = almanac.get("jian_chu") or {}
    tone = jian_chu.get("tone", "")
    delta = cfg["jianchu"].get(tone, 0)
    if tone and delta != 0:
        value += delta
        sign = "+" if delta > 0 else ""
        reasons.append(f"值{jian_chu.get('label', '')}（{tone}，{sign}{delta}）")

    tian_shen = almanac.get("tian_shen") or {}
    ts_luck = tian_shen.get("luck", "")
    ts_delta = cfg["tian_shen"].get(ts_luck, 0)
    if ts_luck and ts_delta != 0:
        value += ts_delta
        sign = "+" if ts_delta > 0 else ""
        reasons.append(
            f"日值{tian_shen.get('name', '')}（{tian_shen.get('type', '')}·{ts_luck}，{sign}{ts_delta}）"
        )

    xiu = almanac.get("xiu") or {}
    xiu_luck = xiu.get("luck", "")
    xiu_delta = cfg["xiu"].get(xiu_luck, 0)
    if xiu_luck and xiu_delta != 0:
        value += xiu_delta
        sign = "+" if xiu_delta > 0 else ""
        reasons.append(f"二十八宿{xiu.get('name', '')}（{xiu_luck}，{sign}{xiu_delta}）")

    lucky_count = len(almanac.get("lucky_hours") or [])
    if lucky_count:
        hour_delta = (lucky_count - cfg["lucky_hour_base"]) * cfg["lucky_hour"]
        hour_delta = max(-cfg["lucky_hour_cap"], min(cfg["lucky_hour_cap"], hour_delta))
        value += int(round(hour_delta))
        reasons.append(f"黄道吉时 {lucky_count} 个（{hour_delta:+.0f}）")

    if almanac.get("all_avoid"):
        value += cfg["all_avoid"]
        reasons.append(f"当日忌「诸事不宜」（{cfg['all_avoid']}）")

    clash = bool(zodiac) and almanac.get("chong", {}).get("zodiac") == zodiac
    if clash:
        value += cfg["clash"]
        reasons.append(
            f"当日的日支与你生肖「{zodiac}」相冲（{cfg['clash']}），传统上不用此日"
        )

    value = max(cfg["min"], min(cfg["max"], value))
    level, level_tone = _level_of(value)
    return {
        "value": value,
        "level": level,
        "tone": level_tone,
        "reasons": reasons,
        "hits": hits,
        "misses": misses,
        "clash": clash,
        "lucky_hour_count": lucky_count,
    }


# ---------------------------------------------------------------- 择日
def activity_of(key: str) -> dict[str, Any]:
    """按 key 取事项定义；未知 key 抛 ValueError 由路由转 400。"""
    activity = ACTIVITIES_BY_KEY.get((key or "").strip())
    if activity is None:
        raise ValueError(f"未知的择日事项：{key}")
    return activity


def list_activities() -> list[dict[str, Any]]:
    """可选事项清单（供前端渲染筛选项）。"""
    return [
        {
            "key": item["key"],
            "name": item["name"],
            "terms": list(item["terms"]),
            "note": item["note"],
        }
        for item in ALMANAC_ACTIVITIES
    ]


def _pick_payload(
    date: _dt.date,
    scored: dict[str, Any],
    almanac: dict[str, Any],
) -> dict[str, Any]:
    """择日结果的一条：日期 + 分数 + 理由 + 可用吉时。"""
    lucky_hours = almanac.get("lucky_hours") or []
    return {
        "date": date.isoformat(),
        "weekday": almanac["weekday"],
        "lunar": almanac["lunar"]["text"],
        "gan_zhi": almanac["gan_zhi"]["day"],
        "jian_chu": almanac["jian_chu"]["name"],
        "jian_chu_label": almanac["jian_chu"]["label"],
        "jian_chu_tone": almanac["jian_chu"]["tone"],
        "tian_shen": almanac["tian_shen"]["name"],
        "tian_shen_type": almanac["tian_shen"]["type"],
        "xiu": almanac["xiu"]["name"],
        "xiu_luck": almanac["xiu"]["luck"],
        "chong": almanac["chong"],
        "score": scored["value"],
        "level": scored["level"],
        "tone": scored["tone"],
        "hits": scored["hits"],
        "misses": scored["misses"],
        "reasons": scored["reasons"],
        "clash": scored["clash"],
        "lucky_hour_count": scored["lucky_hour_count"],
        "lucky_hours": [
            {
                "label": hour["slot_label"],
                "range": hour["range"],
                "tian_shen": hour["tian_shen"],
                "gan_zhi": hour["gan_zhi"],
            }
            for hour in lucky_hours
        ],
        "best_hour": (
            f"{lucky_hours[0]['slot_label']} {lucky_hours[0]['range']}"
            if lucky_hours
            else ""
        ),
    }


def select_dates(
    activity_key: str,
    start: _dt.date,
    days: int = 30,
    zodiac: str = "",
    limit: int = 8,
    min_score: int = 0,
) -> dict[str, Any]:
    """在给定区间内为该事项挑吉日。

    返回按分数降序（同分则日期靠前）排列的候选，每条都带逐项理由。
    ``zodiac`` 传入用户生肖时，冲该生肖的日子会被扣分并标记 ``clash``，
    但仍然展示——完全剔除会让用户困惑「为什么这天不在列表里」。
    """
    activity = activity_of(activity_key)
    zodiac = (zodiac or "").strip()
    if zodiac and zodiac not in ZODIACS:
        raise ValueError(f"生肖应是{ZODIACS}之一，收到：{zodiac}")

    days = max(1, min(int(days), ALMANAC_SELECT_MAX_DAYS))
    limit = max(1, min(int(limit), 60))
    min_score = max(0, min(int(min_score), 100))

    picks: list[dict[str, Any]] = []
    for offset in range(days):
        date = start + _dt.timedelta(days=offset)
        almanac = day_almanac(date)
        scored = day_score(almanac, activity, zodiac)
        picks.append(_pick_payload(date, scored, almanac))

    # 分数优先、日期次之：同分时越早越值得推荐
    picks.sort(key=lambda item: (-item["score"], item["date"]))
    recommended = [item for item in picks if item["score"] >= min_score][:limit]

    best = picks[0] if picks else None
    return {
        "activity": {
            "key": activity["key"],
            "name": activity["name"],
            "terms": list(activity["terms"]),
            "note": activity["note"],
        },
        "range": {
            "start": start.isoformat(),
            "end": (start + _dt.timedelta(days=days - 1)).isoformat(),
            "days": days,
        },
        "zodiac": zodiac,
        "min_score": min_score,
        "scanned": len(picks),
        "recommended_count": len(recommended),
        "items": recommended,
        "best": best,
        "rules_version": ALMANAC_RULES_VERSION,
    }


def month_overview(
    year: int,
    month: int,
    activity_key: str = "",
    zodiac: str = "",
) -> dict[str, Any]:
    """整月每日吉凶：给前端渲染月历热力用。

    不带事项时返回「当日总体」分数；带事项则按事项评分，便于用户一眼扫出
    本月哪几天适合动工。
    """
    if not 1 <= month <= 12:
        raise ValueError(f"月份应在 1-12 之间，收到：{month}")
    activity = activity_of(activity_key) if activity_key else None

    first = _dt.date(year, month, 1)
    next_month = _dt.date(year + (month == 12), (month % 12) + 1, 1)
    span = (next_month - first).days

    items: list[dict[str, Any]] = []
    for offset in range(span):
        date = first + _dt.timedelta(days=offset)
        almanac = day_almanac(date)
        scored = day_score(almanac, activity, zodiac)
        items.append(
            {
                "date": date.isoformat(),
                "day": date.day,
                "weekday": almanac["weekday"],
                "lunar_day": almanac["lunar"]["day"],
                "score": scored["value"],
                "level": scored["level"],
                "tone": scored["tone"],
                "jian_chu": almanac["jian_chu"]["name"],
                "xiu": almanac["xiu"]["name"],
                "xiu_luck": almanac["xiu"]["luck"],
                "chong": almanac["chong"]["desc"],
                "clash": scored["clash"],
                "lucky_hour_count": scored["lucky_hour_count"],
            }
        )

    best = max(items, key=lambda item: item["score"]) if items else None
    return {
        "year": year,
        "month": month,
        "activity": (
            {"key": activity["key"], "name": activity["name"]} if activity else None
        ),
        "zodiac": zodiac,
        "first_weekday": first.weekday(),
        "days": items,
        "best": best,
        "rules_version": ALMANAC_RULES_VERSION,
    }
