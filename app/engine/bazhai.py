# -*- coding: utf-8 -*-
"""八宅游年引擎（确定性计算层）。

与玄空飞星的分工
----------------
* 玄空飞星（:mod:`.flying_star` / :mod:`.daily_star`）算的是「某个方位此刻的星曜
  吉凶」，回答的是「今年财位在哪、今日忌哪个方向」；
* 八宅游年算的是「人（命卦）与宅（宅卦）合不合、各房间该落在哪一宫」，
  回答的是「床该朝哪、灶安哪、门开哪」——装修落地时最直接可用的一套。

两者互补而非替代：本模块只做八宅，玄空结论仍由原链路给出。

三个确定性环节
--------------
1. :func:`ming_gua_of`  —— 本命卦。按出生年与性别取洛书数，**以立春为界**
   （立春前出生按上一年计），余 5 者男寄坤、女寄艮。
2. :func:`you_nian_of`  —— 以某卦为伏位，依大游年歌诀飞布八星（生气、五鬼……）。
3. :func:`build_bazhai` —— 宅命匹配、房间选位与调和建议。

定位口径
--------
* **命卦定「人」**：床位、书桌、办公位的朝向应按本命卦的四吉方。
* **宅卦定「宅」**：大门、灶位、卫生间该落在宅内哪一宫，按坐山卦的游年。
* 宅命同组（东四命居东四宅）时两者天然协同；不同组时以「人向吉方」补宅之不足。

本模块不调用任何大模型，输出可复现、可单元测试。
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

from .compass import orient
from .constants import (
    BAZHAI_AUSPICIOUS,
    BAZHAI_EAST_FOUR,
    BAZHAI_INAUSPICIOUS,
    BAZHAI_MISMATCH_ADVICE,
    BAZHAI_RING,
    BAZHAI_ROOM_RULES,
    BAZHAI_STAR_INFO,
    BAZHAI_WEST_FOUR,
    BAZHAI_YOU_NIAN,
    HOUSE_TYPE_DESC,
    MING_GUA_BY_LUOSHU,
    RULES_VERSION,
    TRIGRAM_INFO,
)

__all__ = [
    "build_bazhai",
    "lichun_year",
    "ming_gua_number",
    "ming_gua_of",
    "you_nian_of",
    "zhai_gua_of",
]

# 八宅可用的八卦（不含中宫「太极」）
_VALID_TRIGRAMS = tuple(BAZHAI_YOU_NIAN.keys())


# ---------------------------------------------------------------- 基础工具
def _require_solar() -> Any:
    """返回 lunar-python 的 Solar 类，未安装时给出明确的安装提示。"""
    if Solar is None:  # pragma: no cover
        raise RuntimeError(
            "缺少排盘依赖 lunar-python，请执行：pip install lunar-python"
        ) from _IMPORT_ERROR
    return Solar


def _group_of(trigram: str) -> str:
    """卦 -> 东西四分组（不带「命 / 宅」后缀）。"""
    if trigram in BAZHAI_EAST_FOUR:
        return "东四"
    if trigram in BAZHAI_WEST_FOUR:
        return "西四"
    raise ValueError(f"未知卦名：{trigram}")


def _check_trigram(trigram: str) -> str:
    if trigram not in _VALID_TRIGRAMS:
        raise ValueError(
            f"宅卦只能是 {'、'.join(_VALID_TRIGRAMS)} 之一，收到：{trigram}"
        )
    return trigram


# ---------------------------------------------------------------- 命卦
def lichun_year(
    year: int,
    month: int = 0,
    day: int = 0,
    hour: int = 0,
    minute: int = 0,
) -> tuple[int, bool]:
    """求命卦归属年份（以立春为界）。

    八宅命卦与八字年柱同口径：立春前出生算上一年，否则年初出生的人会被
    按错年份定命卦。未给月日时不做修正，直接用公历年。

    Returns:
        (归属年份, 是否发生了回退)
    """
    if month <= 0 or day <= 0:
        return year, False
    try:
        solar_cls = _require_solar()
        birth = solar_cls.fromYmdHms(year, month, day, hour, minute, 0)
        # 固定取该公历年 6 月 1 日的节气表：农历年的首个节气即当年 2 月的立春，
        # 而 1 月 / 12 月出生者落在相邻农历年，直接取表会拿到上一年的立春。
        lichun = (
            solar_cls.fromYmd(year, 6, 1).getLunar().getJieQiTable().get("立春")
        )
    except Exception:  # noqa: BLE001 - 缺历法库时退化为近似分界
        lichun = None
    if lichun is None:
        # 无历法库时的近似口径：以 2 月 4 日为界
        return (year - 1, True) if (month, day) < (2, 4) else (year, False)
    if birth.getJulianDay() < lichun.getJulianDay():
        return year - 1, True
    return year, False


def ming_gua_number(year: int, gender: str) -> int:
    """本命卦的洛书数。

    传统公式（按年份后两位推算）：

    * 1900-1999：男 ``(100 - yy) % 9``，女 ``(yy - 4) % 9``
    * 2000-2099：男 ``(99 - yy) % 9``， 女 ``(yy + 6) % 9``

    余 0 作 9；余 5 者中宫无卦可寄，男寄坤(2)、女寄艮(8)。
    """
    if gender not in ("男", "女"):
        raise ValueError("gender 只能是「男」或「女」")
    if not 1900 <= year <= 2100:
        raise ValueError("year 应在 1900 ~ 2100 之间")
    yy = year % 100
    if year >= 2000:
        num = (99 - yy) % 9 if gender == "男" else (yy + 6) % 9
    else:
        num = (100 - yy) % 9 if gender == "男" else (yy - 4) % 9
    if num == 0:
        num = 9
    if num == 5:
        # 五黄居中无卦，男女各寄坤、艮
        num = 2 if gender == "男" else 8
    return num


def ming_gua_of(
    year: int,
    gender: str = "男",
    month: int = 0,
    day: int = 0,
    hour: int = 0,
    minute: int = 0,
) -> dict[str, Any]:
    """本命卦：出生年 + 性别 -> 命卦与东西四属性。"""
    solar_year, adjusted = lichun_year(year, month, day, hour, minute)
    number = ming_gua_number(solar_year, gender)
    trigram = MING_GUA_BY_LUOSHU[number]
    info = TRIGRAM_INFO[trigram]
    group = _group_of(trigram)

    summary = f"{solar_year} 年生{gender}命，属{trigram}命"
    summary += f"（{group}命）。" if not adjusted else f"（{group}命，立春前按上一年计）。"

    return {
        "number": number,
        "trigram": trigram,
        "name": f"{trigram}命",
        "luoshu": info["luoshu"],
        "direction": info["direction"],
        "group": f"{group}命",
        "group_key": group,
        "label": f"{trigram}命 · {group}命",
        "solar_year": solar_year,
        "lichun_adjusted": adjusted,
        "name_input": "",
        "summary": summary,
        "note": (
            f"{group}命宜居{group}宅"
            f"（{'、'.join(BAZHAI_EAST_FOUR if group == '东四' else BAZHAI_WEST_FOUR)}）。"
            "宅不同组时不必换房，把床、书桌、办公位朝向本命四吉方即可调和。"
        ),
    }


# ---------------------------------------------------------------- 宅卦与游年
def zhai_gua_of(trigram: str, orientation: dict[str, Any] | None = None) -> dict[str, Any]:
    """宅卦：坐山卦 + 东西四属性（可选带上坐向明细）。"""
    _check_trigram(trigram)
    info = TRIGRAM_INFO[trigram]
    group = _group_of(trigram)
    out = {
        "trigram": trigram,
        "name": f"{trigram}宅",
        "luoshu": info["luoshu"],
        "direction": info["direction"],
        "group": f"{group}宅",
        "group_key": group,
        "label": f"{trigram}宅 · {group}宅",
        "description": HOUSE_TYPE_DESC.get(trigram, ""),
        # 未提供坐向明细时以下字段留空，前端按「仅知宅卦」展示
        "mountain": "",
        "facing": "",
        "title": "",
        "readable": "",
        "facing_trigram": "",
        "facing_direction": "",
        "degree": None,
    }
    if orientation:
        out.update(
            {
                "mountain": orientation.get("mountain", ""),
                "facing": orientation.get("facing", ""),
                "title": orientation.get("title", ""),
                "readable": orientation.get("readable", ""),
                "facing_trigram": orientation.get("facing_trigram", ""),
                "facing_direction": orientation.get("facing_direction", ""),
                "degree": orientation.get("degree"),
            }
        )
    return out


def you_nian_of(trigram: str) -> list[dict[str, Any]]:
    """游年八星：以 [trigram] 为伏位，依大游年歌诀飞布八宫。

    返回 8 项，顺序固定为「自乾起顺时针」一圈（与 :data:`BAZHAI_RING` 一致），
    每项带方位与洛书数，前端可直接映射到九宫格。吉凶分组另见
    :func:`_split_stars`。

    Raises:
        ValueError: 卦名不在八卦之内。
    """
    _check_trigram(trigram)
    codes = BAZHAI_YOU_NIAN[trigram]
    start = BAZHAI_RING.index(trigram)
    out: list[dict[str, Any]] = []
    for i, code in enumerate(codes):
        gua = BAZHAI_RING[(start + i) % 8]
        meta = BAZHAI_STAR_INFO[code]
        info = TRIGRAM_INFO[gua]
        out.append(
            {
                "code": code,
                "star": meta["name"],
                "alias": meta["alias"],
                "element": meta["element"],
                "level": meta["level"],
                "trigram": gua,
                "direction": info["direction"],
                "luoshu": info["luoshu"],
                "meaning": meta["meaning"],
                "suitable": list(meta["suitable"]),
                "avoid": list(meta["avoid"]),
                # 伏位即本卦宫（宅卦时是坐山宫、命卦时是本命宫）
                "is_base": gua == trigram,
            }
        )
    return out


def _split_stars(stars: list[dict[str, Any]]) -> tuple[list, list]:
    """把八星压成（四吉, 四凶）两组，组内按优先级排序。"""
    by_code = {s["code"]: s for s in stars}
    good = [by_code[c] for c in BAZHAI_AUSPICIOUS if c in by_code]
    bad = [by_code[c] for c in BAZHAI_INAUSPICIOUS if c in by_code]
    return good, bad


def _compact(star: dict[str, Any]) -> dict[str, Any]:
    """列表展示用的精简结构（去掉宜忌长文案，九宫格里放不下）。"""
    return {
        "code": star["code"],
        "star": star["star"],
        "trigram": star["trigram"],
        "direction": star["direction"],
        "level": star["level"],
        "element": star["element"],
    }


# ---------------------------------------------------------------- 房间选位
def _room_plan(stars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按宅卦游年给出各功能房间的选位建议。"""
    by_code = {s["code"]: s for s in stars}
    plans: list[dict[str, Any]] = []
    for rule in BAZHAI_ROOM_RULES:
        recommend = [_compact(by_code[c]) for c in rule["best"] if c in by_code]
        avoid = [_compact(by_code[c]) for c in rule["avoid"] if c in by_code]
        if not recommend:
            continue
        top = recommend[0]
        plans.append(
            {
                "key": rule["key"],
                "name": rule["name"],
                "recommend": recommend,
                "avoid": avoid,
                "headline": f"{top['direction']} · {top['star']}",
                "note": rule["note"],
            }
        )
    return plans


# ---------------------------------------------------------------- 宅命匹配
def _compat(ming_trigram: str, zhai_trigram: str) -> dict[str, Any]:
    ming_group = _group_of(ming_trigram)
    zhai_group = _group_of(zhai_trigram)
    matched = ming_group == zhai_group
    same_gua = ming_trigram == zhai_trigram

    if matched:
        summary = (
            f"{ming_group}命居{zhai_group}宅，宅命相配，人宅相扶。"
            if not same_gua
            else f"{ming_trigram}命居{zhai_trigram}宅，命卦与宅卦同宫，是八宅中最稳的组合。"
        )
        advice = [
            "宅命既配，重点把大门、主卧、灶位落在生气、延年、天医三方即可。",
            "绝命、五鬼两宫改作卫生间、储物间，以浊气镇煞，不作卧室。",
        ]
        score = 100 if same_gua else 90
        level = "同宫" if same_gua else "相配"
    else:
        summary = (
            f"{ming_group}命居{zhai_group}宅，宅命不配；"
            "人宅之气不接，须用床位、桌向与灶口朝向调和，不必为此换房。"
        )
        advice = list(BAZHAI_MISMATCH_ADVICE)
        score = 55
        level = "不配"

    return {
        "matched": matched,
        "same_gua": same_gua,
        "level": level,
        "score": score,
        "ming_group": f"{ming_group}命",
        "zhai_group": f"{zhai_group}宅",
        "summary": summary,
        "advice": advice,
    }


# ---------------------------------------------------------------- 主入口
def build_bazhai(
    year: int,
    gender: str = "男",
    month: int = 0,
    day: int = 0,
    hour: int = 0,
    minute: int = 0,
    degree: float | None = None,
    declination: float = 0.0,
    trigram: str = "",
    name: str = "",
) -> dict[str, Any]:
    """排出八宅盘：命卦 + 宅卦 + 游年八星 + 宅命匹配 + 房间选位。

    Args:
        year: 出生年（公历）。
        gender: 男 / 女。命卦由年份与性别共同决定，两者缺一不可。
        month/day/hour/minute: 出生时刻，用于立春分界；传 0 表示不做分界。
        degree: 罗盘读到的磁方位角。与 ``trigram`` 二选一。
        declination: 当地磁偏角，仅在被 ``degree`` 时有效。
        trigram: 直接指定宅卦（坐山卦），用于「只知卦不知度数」的场景。
        name: 姓名，仅作回显。

    Returns:
        可直接序列化的八宅盘字典。

    Raises:
        ValueError: 参数越界、日期非法，或既未给 degree 也未给 trigram。
    """
    if gender not in ("男", "女"):
        raise ValueError("gender 只能是「男」或「女」")
    if not 1900 <= year <= 2100:
        raise ValueError("year 应在 1900 ~ 2100 之间")
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("hour/minute 超出合法范围")
    if month and day:
        try:
            _dt.date(year, month, day)
        except ValueError as exc:
            raise ValueError(f"非法出生日期：{year}-{month}-{day}") from exc

    # 宅卦来源：优先用罗盘实测度数（顺带给出坐向明细），否则用显式卦名
    orientation: dict[str, Any] | None = None
    if degree is not None:
        orientation = orient(degree, declination)
        zhai_trigram = orientation["trigram"]
    elif trigram:
        zhai_trigram = _check_trigram(trigram)
    else:
        raise ValueError("请至少提供 degree（罗盘读数）或 trigram（宅卦）之一")

    zhai_trigram = _check_trigram(zhai_trigram)

    ming = ming_gua_of(year, gender, month, day, hour, minute)
    ming["name_input"] = name.strip()
    zhai = zhai_gua_of(zhai_trigram, orientation)
    compat = _compat(ming["trigram"], zhai_trigram)

    zhai_stars = you_nian_of(zhai_trigram)
    ming_stars = you_nian_of(ming["trigram"])
    good, bad = _split_stars(zhai_stars)
    ming_good, ming_bad = _split_stars(ming_stars)

    # 本命吉方：床位、书桌、办公位的朝向依据
    lucky_text = "、".join(f"{s['direction']}（{s['star']}）" for s in ming_good)
    ming_directions = {
        "lucky": [_compact(s) for s in ming_good],
        "unlucky": [_compact(s) for s in ming_bad],
        "summary": f"本命吉方：{lucky_text}。",
        "bed": (
            f"床头宜朝{ming_good[0]['direction']}（{ming_good[0]['star']}）、"
            f"{ming_good[1]['direction']}（{ming_good[1]['star']}）等本命吉方，"
            f"忌朝{ming_bad[0]['direction']}（{ming_bad[0]['star']}）方；"
            "床头不宜靠窗、不宜正对房门。"
        ),
        "desk": (
            f"书桌宜坐{ming_good[0]['direction']}（{ming_good[0]['star']}）方、"
            f"面向{ming_good[1]['direction'] if len(ming_good) > 1 else ming_good[0]['direction']}，"
            "主思路清明、贵人相助。"
        ),
    }

    rooms = _room_plan(zhai_stars)

    # 行动要点：把结论压成可执行的三五条
    top_good = good[0]
    top_bad = bad[0]
    key_points = [
        compat["summary"],
        f"宅内最吉之宫在{top_good['direction']}（{top_good['star']}），"
        f"宜作{'、'.join(top_good['suitable'][:3])}。",
        f"最凶之宫在{top_bad['direction']}（{top_bad['star']}），"
        f"宜作{'、'.join(top_bad['suitable'][:2])}，不作卧室与大门。",
        ming_directions["summary"],
    ]
    if not compat["matched"]:
        key_points.append(
            f"宅命不配时，{ming['group']}的床位与桌向务必落在{ming_good[0]['direction']}一侧。"
        )

    return {
        "birth": {
            "year": year,
            "month": month,
            "day": day,
            "gender": gender,
            "name": name.strip(),
            "solar_year": ming["solar_year"],
            "lichun_adjusted": ming["lichun_adjusted"],
            "summary": f"{ming['solar_year']} 年生 · {gender} · {ming['group']}",
        },
        "ming_gua": ming,
        "zhai_gua": zhai,
        "compat": compat,
        # 宅卦游年：定「房子」各宫吉凶，房间选位据此
        "stars": zhai_stars,
        "auspicious": good,
        "inauspicious": bad,
        # 命卦游年：定「人」的吉方，床位与桌向据此
        "ming_stars": ming_stars,
        "ming_directions": ming_directions,
        "rooms": rooms,
        "key_points": key_points,
        "rules_version": RULES_VERSION,
    }
