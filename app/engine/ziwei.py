# -*- coding: utf-8 -*-
"""紫微斗数排盘引擎（确定性安星，不依赖大模型）。

与 :mod:`app.engine.bazi` 一样，本模块只做数值 / 星曜布局计算，文案解读
放在 :mod:`app.engine.ziwei_reading`。

采用的起例（通行中州派规则，可复现、可单测）
--------------------------------------------
1. **命宫 / 身宫**：生月起子时，逆行至生时为命宫；生月起午时，顺行至生时为身宫。
   （可验证：按此式算出的身宫必落在命 / 夫 / 财 / 迁 / 官 / 福 六宫之一，
   与传统「身宫只居六宫」的结论一致。）
2. **五行局**：由命宫干支的**纳音五行**决定 —— 水二局、木三局、金四局、
   土五局、火六局（不是出生年的纳音）。
3. **紫微星**：按口诀「六五四三二，酉午亥辰丑」定该局初一所在宫
   （火六局起酉、土五局起午、金四局起亥、木三局起辰、水二局起丑），
   再以「局数除农历生日」顺行定宫。
4. **紫微星系（逆行，地支递减）**：紫微 0、天机 -1、太阳 -3、武曲 -4、
   天同 -5、廉贞 -8。
5. **天府星系（顺行，地支递增）**：天府与紫微以「寅—申」轴对称
   （天府 = 4 - 紫微，子为 0）；太阴 +1、贪狼 +2、巨门 +3、天相 +4、
   天梁 +5、七杀 +6、破军 +10。
6. **十二宫**：自命宫起逆行（地支递减）—— 命、兄、夫、子、财、疾、迁、
   友、官、田、福、父。
7. **大限**：按局数起运（水二局 2 岁起…），阳男阴女顺行、阴男阳女逆行，
   每宫十年。

已知取舍（在代码里显式标注，避免后来者误以为是 bug）
----------------------------------------------------
* 闰月按当月月数取绝对值（各派对闰月归属有分歧，这里取最通行做法）。
* 只安主星与规则明确的主要辅星；火星 / 铃星等分歧较大的星曜不排。
* 时辰以**真太阳时**为准（与八字模块一致），保证同一份出生信息两处自洽。
* 五行局取**命宫干支的纳音**。网上流传的「按命宫地支速查五行局」表与纳音法
  并不总是一致（同一地支在不同年干下纳音不同），此处采用命宫干支纳音这一派。
* 大限年龄按**周岁**推算（虚岁 / 周岁起运各派不同），``da_xian.age`` 即周岁。
* 未排星曜庙旺（亮度）与其余杂曜，解读只基于主星 + 主要辅星 + 四化。
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

from .bazi import hour_branch_of, na_yin_of, true_solar_time
from .constants import EARTHLY_BRANCHES, HEAVENLY_STEMS, STEM_YIN_YANG

__all__ = ["build_ziwei", "ZIWEI_PALACES"]

# 地支序号：子 0 … 亥 11
BRANCHES = EARTHLY_BRANCHES

# 十二宫（自命宫起逆行排列）
ZIWEI_PALACES = [
    "命宫", "兄弟", "夫妻", "子女", "财帛", "疾厄",
    "迁移", "交友", "官禄", "田宅", "福德", "父母",
]

# 五虎遁：年干 -> 寅宫天干（甲己之岁丙作首……）
WU_HU_DUN = {
    "甲": "丙", "己": "丙",
    "乙": "戊", "庚": "戊",
    "丙": "庚", "辛": "庚",
    "丁": "壬", "壬": "壬",
    "戊": "甲", "癸": "甲",
}

# 纳音五行 -> (局名, 局数, 紫微基准宫)
WU_XING_JU = {
    "水": ("水二局", 2, "丑"),
    "木": ("木三局", 3, "辰"),
    "金": ("金四局", 4, "亥"),
    "土": ("土五局", 5, "午"),
    "火": ("火六局", 6, "酉"),
}

# 紫微星系（相对紫微的宫位偏移，负 = 逆行）
ZIWEI_SERIES = {
    "紫微": 0, "天机": -1, "太阳": -3, "武曲": -4, "天同": -5, "廉贞": -8,
}
# 天府星系（相对天府的宫位偏移，正 = 顺行）
TIANFU_SERIES = {
    "天府": 0, "太阴": 1, "贪狼": 2, "巨门": 3,
    "天相": 4, "天梁": 5, "七杀": 6, "破军": 10,
}

# 天魁 / 天钺（天乙贵人）：甲戊庚牛羊，乙己鼠猴乡，丙丁猪鸡位，壬癸兔蛇藏，六辛逢马虎
TIAN_KUI = {
    "甲": "丑", "戊": "丑", "庚": "丑", "乙": "子", "己": "子",
    "丙": "亥", "丁": "亥", "壬": "卯", "癸": "卯", "辛": "午",
}
TIAN_YUE = {
    "甲": "未", "戊": "未", "庚": "未", "乙": "申", "己": "申",
    "丙": "酉", "丁": "酉", "壬": "巳", "癸": "巳", "辛": "寅",
}

# 禄存：甲禄在寅、乙禄在卯、丙戊禄在巳、丁己禄在午、庚禄在申、辛禄在酉、壬禄在亥、癸禄在子
LU_CUN = {
    "甲": "寅", "乙": "卯", "丙": "巳", "戊": "巳", "丁": "午", "己": "午",
    "庚": "申", "辛": "酉", "壬": "亥", "癸": "子",
}

# 四化：年干 -> {化象: 星曜}
SI_HUA = {
    "甲": {"化禄": "廉贞", "化权": "破军", "化科": "武曲", "化忌": "太阳"},
    "乙": {"化禄": "天机", "化权": "天梁", "化科": "紫微", "化忌": "太阴"},
    "丙": {"化禄": "天同", "化权": "天机", "化科": "文昌", "化忌": "廉贞"},
    "丁": {"化禄": "太阴", "化权": "天同", "化科": "天机", "化忌": "巨门"},
    "戊": {"化禄": "贪狼", "化权": "太阴", "化科": "右弼", "化忌": "天机"},
    "己": {"化禄": "武曲", "化权": "贪狼", "化科": "天梁", "化忌": "文曲"},
    "庚": {"化禄": "太阳", "化权": "武曲", "化科": "太阴", "化忌": "天同"},
    "辛": {"化禄": "巨门", "化权": "太阳", "化科": "文曲", "化忌": "文昌"},
    "壬": {"化禄": "天梁", "化权": "紫微", "化科": "左辅", "化忌": "武曲"},
    "癸": {"化禄": "破军", "化权": "巨门", "化科": "太阴", "化忌": "贪狼"},
}

# 常用吉星 / 煞星归类，供解读层加权
AUSPICIOUS = {"左辅", "右弼", "天魁", "天钺", "文昌", "文曲", "禄存"}
MALIFIC = {"擎羊", "陀罗", "地空", "地劫"}


def _require_solar() -> Any:
    if Solar is None:  # pragma: no cover
        raise RuntimeError(
            "缺少排盘依赖 lunar-python，请执行：pip install lunar-python"
        ) from _IMPORT_ERROR
    return Solar


def _branch_index(zhi: str) -> int:
    return BRANCHES.index(zhi)


def palace_gan(year_gan: str, zhi_index: int) -> str:
    """宫位天干：五虎遁起寅，按地支顺推到目标宫。"""
    start = HEAVENLY_STEMS.index(WU_HU_DUN[year_gan])
    return HEAVENLY_STEMS[(start + (zhi_index - _branch_index("寅"))) % 10]


def wu_xing_ju(ming_gan: str, ming_zhi: str) -> tuple[str, int, str]:
    """命宫干支 -> (局名, 局数, 紫微基准宫)。"""
    element = na_yin_of(ming_gan, ming_zhi)[-1]
    if element not in WU_XING_JU:  # pragma: no cover - 纳音表固定，兜底防脏数据
        element = "土"
    return WU_XING_JU[element]


def ziwei_palace(ju_number: int, base_zhi: str, lunar_day: int) -> int:
    """局数 + 农历生日 -> 紫微所在宫（地支序号）。

    口诀：「局数除日数，商数宫前走；若见数无余，便要起虎口；日数小于局，还直宫中守。」
    等价于「基准宫起初一，每宫局数日、顺行」：
    整除时落在第 ``商-1`` 格，否则落在第 ``商`` 格。
    """
    q, r = divmod(lunar_day, ju_number)
    offset = q if r else q - 1
    return (_branch_index(base_zhi) + offset) % 12


def _age_of(birth: _dt.date, today: _dt.date) -> int:
    return today.year - birth.year - (
        (today.month, today.day) < (birth.month, birth.day)
    )


def build_ziwei(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int = 0,
    gender: str = "男",
    longitude: float = 120.0,
    name: str = "",
    today: _dt.date | None = None,
) -> dict[str, Any]:
    """排紫微斗数命盘。

    Args:
        year/month/day: 出生公历日期。
        hour/minute: 出生时的北京时间（钟表时间）。
        gender: 男 / 女（决定大限顺逆）。
        longitude: 出生地东经度数，用于真太阳时校正。
        name: 姓名，仅作回显。
        today: 参考日期，用于推算当前大限（默认取今天，仅测试会传）。

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
        birth_day = _dt.date(year, month, day)
    except ValueError as exc:
        raise ValueError(f"非法出生日期：{year}-{month}-{day}") from exc

    solar_cls = _require_solar()

    # 1) 真太阳时校正（与八字模块共用同一算法，保证两处自洽）
    true_dt, offset_minutes = true_solar_time(year, month, day, hour, minute, longitude)
    solar = solar_cls.fromYmdHms(
        true_dt.year, true_dt.month, true_dt.day,
        true_dt.hour, true_dt.minute, 0,
    )
    lunar = solar.getLunar()

    # 2) 农历月日（闰月取绝对值）与年干支（紫微以农历正月初一换年）
    lunar_month = abs(lunar.getMonth())
    lunar_day = lunar.getDay()
    year_gan = lunar.getYearGan()
    year_zhi = lunar.getYearZhi()

    # 3) 命宫 / 身宫
    hour_zhi = hour_branch_of(true_dt.hour)
    h = _branch_index(hour_zhi)
    ming_index = (_branch_index("寅") + (lunar_month - 1) - h) % 12
    shen_index = (_branch_index("寅") + (lunar_month - 1) + h - _branch_index("午")) % 12

    # 4) 五行局 + 紫微星
    ming_gan = palace_gan(year_gan, ming_index)
    ming_zhi = BRANCHES[ming_index]
    ju_name, ju_number, base_zhi = wu_xing_ju(ming_gan, ming_zhi)
    ziwei_index = ziwei_palace(ju_number, base_zhi, lunar_day)

    # 5) 十四主星
    star_slots: dict[str, int] = {}
    for star, offset in ZIWEI_SERIES.items():
        star_slots[star] = (ziwei_index + offset) % 12
    tianfu_index = (4 - ziwei_index) % 12  # 与紫微以寅—申轴对称
    for star, offset in TIANFU_SERIES.items():
        star_slots[star] = (tianfu_index + offset) % 12

    # 6) 辅星：文昌 / 文曲（按时支）、左右（按月）、魁钺禄羊陀（按年干）、空劫（按时支）
    aux_slots: dict[str, int] = {
        "文昌": (_branch_index("戌") - h) % 12,
        "文曲": (_branch_index("辰") + h) % 12,
        "左辅": (_branch_index("辰") + lunar_month - 1) % 12,
        "右弼": (_branch_index("戌") - (lunar_month - 1)) % 12,
        "地空": (_branch_index("亥") - h) % 12,
        "地劫": (_branch_index("亥") + h) % 12,
        "天魁": _branch_index(TIAN_KUI[year_gan]),
        "天钺": _branch_index(TIAN_YUE[year_gan]),
        "禄存": _branch_index(LU_CUN[year_gan]),
    }
    lu_index = aux_slots["禄存"]
    aux_slots["擎羊"] = (lu_index + 1) % 12
    aux_slots["陀罗"] = (lu_index - 1) % 12

    # 7) 四化（按年干，落到星曜上）
    si_hua_by_star = {star: hua for hua, star in SI_HUA[year_gan].items()}

    # 8) 十二宫（自命宫起逆行）
    palaces = []
    for i, palace_name in enumerate(ZIWEI_PALACES):
        zhi_index = (ming_index - i) % 12
        zhi = BRANCHES[zhi_index]
        gan = palace_gan(year_gan, zhi_index)
        main = [s for s, idx in star_slots.items() if idx == zhi_index]
        aux = [s for s, idx in aux_slots.items() if idx == zhi_index]
        hua_list = [
            {"star": s, "hua": si_hua_by_star[s]}
            for s in main + aux
            if s in si_hua_by_star
        ]
        palaces.append(
            {
                "name": palace_name,
                "zhi": zhi,
                "gan": gan,
                "pillar": gan + zhi,
                "main": main,
                "aux": aux,
                "si_hua": hua_list,
                "is_ming": i == 0,
                "is_shen": zhi_index == shen_index,
                "is_empty": not main,
            }
        )

    # 9) 大限：局数起运，阳男阴女顺行、阴男阳女逆行，每宫十年
    yang = STEM_YIN_YANG[year_gan] == "阳"
    forward = (gender == "男" and yang) or (gender == "女" and not yang)

    # palaces[i] 的地支 = 命宫 - i，因此「顺行 k 宫」= palaces[-k]
    def da_xian_palace(k: int) -> dict[str, Any]:
        return palaces[(-k) % 12] if forward else palaces[k]

    for k in range(12):
        start_age = ju_number + 10 * k
        da_xian_palace(k)["da_xian"] = {"from": start_age, "to": start_age + 9}

    ref_day = today or _dt.date.today()
    age = _age_of(birth_day, ref_day)
    da_xian_index = 0
    if age >= ju_number:
        da_xian_index = min((age - ju_number) // 10, 11)
    da_xian = da_xian_palace(da_xian_index)

    # 10) 三方四正：命宫 + 财帛 + 官禄，对宫为迁移（宫位序号固定，与命宫无关）
    san_fang = {
        "ming": palaces[0],
        "wealth": palaces[4],
        "career": palaces[8],
        "opposite": palaces[6],
    }

    return {
        "birth": {
            "name": name,
            "gender": gender,
            "longitude": round(float(longitude), 4),
            "solar": f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}",
            "true_solar": true_dt.strftime("%Y-%m-%d %H:%M"),
            "offset_minutes": offset_minutes,
            "hour_zhi": hour_zhi,
            "lunar": f"农历{lunar_month}月{lunar_day}日",
            "summary": f"{year_gan}{year_zhi}年 · {hour_zhi}时 · {gender}",
        },
        "basic": {
            "year_gan": year_gan,
            "year_zhi": year_zhi,
            "ming_gan": ming_gan,
            "ming_zhi": ming_zhi,
            "ming_pillar": ming_gan + ming_zhi,
            "shen_zhi": BRANCHES[shen_index],
            "shen_palace": next(
                (p["name"] for p in palaces if p["is_shen"]), "命宫"
            ),
            "ju": ju_name,
            "ju_number": ju_number,
            "ziwei_zhi": BRANCHES[ziwei_index],
            "da_xian_forward": forward,
        },
        "palaces": palaces,
        "da_xian": {
            "index": da_xian_index,
            "age": age,
            "from": da_xian["da_xian"]["from"],
            "to": da_xian["da_xian"]["to"],
            "palace": da_xian["name"],
            "zhi": da_xian["zhi"],
            "main": da_xian["main"],
            "aux": da_xian["aux"],
        },
        "san_fang": {
            key: {"name": p["name"], "zhi": p["zhi"], "main": p["main"], "aux": p["aux"]}
            for key, p in san_fang.items()
        },
    }
