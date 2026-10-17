# -*- coding: utf-8 -*-
"""六爻纳甲 + 梅花易数（确定性计算层）。

与项目其它引擎同一条铁律：**数值由代码算，文案是确定性映射**，不调大模型。

职责边界（很重要）
------------------
* **起卦**由前端负责：铜钱摇哪一面、随手取什么数字，本质是随机事件，
  不是后端该掺和的东西。后端收的是**结果**（六个爻值 / 两三个数），
  只做**装卦与解读**——这一半是完全确定的，可复现、可单测。
* 因此后端**不产生随机数**，「铜钱背面算阳还是字面算阳」这种流派分歧
  也留在前端的起卦交互里说明，不进引擎。

规则出处
--------
* 纳甲歌：「乾金甲子外壬午，坎水戊寅外戊申，震木庚子外庚午，艮土丙辰外丙戌，
  坤土乙未外癸丑，巽木辛丑外辛未，离火己卯外己酉，兑金丁巳外丁亥。」
  阳卦（乾震坎艮）顺行纳阳支，阴卦（坤巽离兑）逆行纳阴支。
* 八宫与世应：按「初爻起逐爻变 → 五世 → 四爻回本宫（游魂）→ 下卦回本宫（归魂）」
  **程序生成** 64 个爻型，宫与世位随之确定；应爻「世隔两爻」。
  生成结果与 ``constants.GUA64`` 卦名表互为校验（见 test_divination）。
* 六神：「甲乙起青龙，丙丁起朱雀，戊日起勾陈，己日起腾蛇，庚辛起白虎，壬癸起玄武。」
* 六亲：以**卦宫五行**为「我」，看爻支五行的生克。
* 梅花：先天数乾一兑二离三震四巽五坎六艮七坤八；无动爻者为体、有动爻者为用；
  互卦取中四爻，变卦由动爻阴阳互变。

能做什么 / 不做什么
--------------------
* **能**：装出每爻的干支 / 六亲 / 六神 / 世应 / 动爻，给出旺衰与倾向。
* **不做**：不断具体事件（如「下周三签约成功」），不下卦辞爻辞
  （64 卦辞 + 384 爻辞数据量大，且版本歧异，宁缺毋滥）。
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
    DIVINATION_RULES_VERSION,
    DIVINATION_TOPICS,
    EARTHLY_BRANCHES,
    GENERATES,
    GUA64,
    LIU_QIN_BY_RELATION,
    LIU_QIN_NOTE,
    LIU_SHEN_NOTE,
    LIU_SHEN_ORDER,
    LIU_SHEN_START,
    NA_JIA_GAN,
    NA_JIA_ZHI,
    NUM_TO_TRIGRAM,
    TRIGRAM_BITS,
    TRIGRAM_GUA_INFO,
    XIAN_TIAN_NUM,
)

__all__ = [
    "build_divination",
    "hexagram_of",
    "liuyao_chart",
    "meihua_chart",
]

# 爻值约定（前端起卦产出，后端只认这四个数）
# 6 老阴（阴，动）  7 少阳（阳，静）  8 少阴（阴，静）  9 老阳（阳，动）
YAO_VALUES = (6, 7, 8, 9)
YAO_IS_YANG = {6: False, 7: True, 8: False, 9: True}
YAO_IS_MOVING = {6: True, 7: False, 8: False, 9: True}
YAO_NAME = {6: "老阴", 7: "少阳", 8: "少阴", 9: "老阳"}

# 五行旺相休囚死：以**月支五行**为「令」
# 同令=旺、令生=相、我生令=休、我克令=囚、令克我=死
WANG_XIANG = {"旺": "与月令同气，最得力", "相": "得月令相生，有力",
              "休": "生月令而泄气", "囚": "克月令而受制",
              "死": "被月令所克，最不得力"}
# 月令 -> 当旺五行
SEASON_ELEMENT = {
    "寅": "木", "卯": "木", "巳": "火", "午": "火",
    "申": "金", "酉": "金", "亥": "水", "子": "水",
    "辰": "土", "戌": "土", "丑": "土", "未": "土",
}

# 六神的倾向权重（用于把「六神压在哪一爻」折算成吉凶倾向）
LIU_SHEN_WEIGHT = {
    "青龙": 2, "朱雀": -1, "勾陈": -1, "腾蛇": -2, "白虎": -3, "玄武": -2,
}

# 体用生克 -> 吉凶（梅花易数）
MEIHUA_VERDICT = {
    "用生体": ("大吉", "事情本身在帮你，外力相助，顺水推舟即可。"),
    "比和": ("大吉", "你与这件事气场相合，阻力小，按原计划推进。"),
    "体克用": ("小吉", "你能压得住这件事，但要自己出力，不是白得的好处。"),
    "体生用": ("小凶", "你在为这件事付出、消耗，容易费力不讨好，量力而行。"),
    "用克体": ("凶", "事情反过来压着你，阻力大，宜守不宜进，先避其锋。"),
}


def _require_solar() -> Any:
    if Solar is None:  # pragma: no cover
        raise RuntimeError(
            "缺少历法依赖 lunar-python，请执行：pip install lunar-python"
        ) from _IMPORT_ERROR
    return Solar


# ---------------------------------------------------------------- 八宫 / 世应
def _build_gua_table() -> dict[tuple[int, ...], dict[str, Any]]:
    """程序生成 64 个爻型的「卦名 / 宫 / 世爻 / 应爻」。

    八宫卦序：本宫（八纯）→ 初爻起逐爻变（一世…五世）→ 四爻回本宫（游魂）
    → 下卦全部回本宫（归魂）。世爻随序而定，应爻「世隔两爻」。
    """
    table: dict[tuple[int, ...], dict[str, Any]] = {}
    inv = {bits: name for name, bits in TRIGRAM_BITS.items()}
    seq_names = ("本宫", "一世", "二世", "三世", "四世", "五世", "游魂", "归魂")
    # 各序的世爻所在（0-based，自下而上）；应爻 = 世 + 3
    shi_index = (5, 0, 1, 2, 3, 4, 3, 2)

    for palace, bits in TRIGRAM_BITS.items():
        lines = list(bits) + list(bits)  # 下卦占 0,1,2；上卦占 3,4,5
        variants: list[list[int]] = [list(lines)]
        for i in range(5):  # 一世…五世：逐爻变
            lines[i] = 1 - lines[i]
            variants.append(list(lines))
        lines[3] = bits[0]  # 游魂：四爻回到本宫之爻
        variants.append(list(lines))
        lines[0], lines[1], lines[2] = bits  # 归魂：下卦全部回到本宫
        variants.append(list(lines))

        for order, cur in enumerate(variants):
            lower = inv[tuple(cur[0:3])]
            upper = inv[tuple(cur[3:6])]
            shi = shi_index[order]
            table[tuple(cur)] = {
                "name": GUA64[(upper, lower)],
                "upper": upper,
                "lower": lower,
                "palace": palace,
                "element": TRIGRAM_GUA_INFO[palace]["element"],
                "order": seq_names[order],
                "shi": shi,
                "ying": (shi + 3) % 6,
            }
    return table


GUA_TABLE = _build_gua_table()


def hexagram_of(lines: list[int]) -> dict[str, Any]:
    """六个爻的阴阳（1 阳 / 0 阴，自下而上）-> 卦名、宫、世应。"""
    if len(lines) != 6:
        raise ValueError("卦必须有六爻")
    key = tuple(1 if x else 0 for x in lines)
    meta = GUA_TABLE.get(key)
    if meta is None:  # pragma: no cover - 二值化后必然命中
        raise ValueError(f"未知卦象：{lines}")
    return dict(meta)


def _trigram_of(bits: tuple[int, int, int]) -> str:
    for name, value in TRIGRAM_BITS.items():
        if value == bits:
            return name
    raise ValueError(f"非法卦型：{bits}")  # pragma: no cover


# ---------------------------------------------------------------- 装卦
def _relation_of(element: str, me: str) -> str:
    """``element`` 相对 ``me`` 的生克，返回 同我/生我/我生/克我/我克。"""
    if element == me:
        return "同我"
    if GENERATES[element] == me:
        return "生我"
    if GENERATES[me] == element:
        return "我生"
    if CONTROLS[element] == me:
        return "克我"
    return "我克"


def _wang_xiang_of(element: str, month_zhi: str) -> tuple[str, str]:
    """爻支五行相对**月令**的旺相休囚死。"""
    ling = SEASON_ELEMENT.get(month_zhi, "土")
    if element == ling:
        key = "旺"
    elif GENERATES[ling] == element:
        key = "相"
    elif GENERATES[element] == ling:
        key = "休"
    elif CONTROLS[element] == ling:
        key = "囚"
    else:
        key = "死"
    return key, WANG_XIANG[key]


def _day_context(when: _dt.datetime) -> dict[str, str]:
    """起卦时刻的日干支与月支（排六神、论旺衰都要用）。"""
    solar_cls = _require_solar()
    lunar = solar_cls.fromYmdHms(
        when.year, when.month, when.day, when.hour, when.minute, 0
    ).getLunar()
    day_gan_zhi = lunar.getDayInGanZhi()
    return {
        "day_gan_zhi": day_gan_zhi,
        "day_gan": day_gan_zhi[0],
        "day_zhi": day_gan_zhi[-1],
        "month_zhi": lunar.getMonthZhi(),
        "lunar": f"{lunar.getYearInGanZhi()}年{lunar.getMonthInChinese()}月"
                 f"{lunar.getDayInChinese()}",
    }


def _yao_rows(
    lines: list[int], meta: dict[str, Any], ctx: dict[str, str]
) -> list[dict[str, Any]]:
    """给本卦六爻装纳甲、六亲、六神、世应、动爻。"""
    lower_zhi = NA_JIA_ZHI[meta["lower"]]
    upper_zhi = NA_JIA_ZHI[meta["upper"]]
    lower_gan = NA_JIA_GAN[meta["lower"]]
    upper_gan = NA_JIA_GAN[meta["upper"]]
    palace_element = meta["element"]
    start_god = LIU_SHEN_START[ctx["day_gan"]]
    start_at = LIU_SHEN_ORDER.index(start_god)
    gods = [LIU_SHEN_ORDER[(start_at + i) % 6] for i in range(6)]

    rows: list[dict[str, Any]] = []
    for i, value in enumerate(lines):
        is_upper = i >= 3
        trigram = meta["upper"] if is_upper else meta["lower"]
        gan = upper_gan[1] if is_upper else lower_gan[0]
        zhi = (upper_zhi[1] if is_upper else lower_zhi[0])[i % 3]
        element = BRANCH_ELEMENT[zhi]
        relation = _relation_of(element, palace_element)
        liu_qin = LIU_QIN_BY_RELATION[relation]
        god = LIU_SHEN_ORDER[(start_at + i) % 6]
        wx, wx_note = _wang_xiang_of(element, ctx["month_zhi"])
        moving = YAO_IS_MOVING[value]

        rows.append({
            "index": i,
            "position": ("初", "二", "三", "四", "五", "上")[i] + "爻",
            "value": value,
            "value_name": YAO_NAME[value],
            "is_yang": YAO_IS_YANG[value],
            "symbol": "▅▅▅▅▅" if YAO_IS_YANG[value] else "▅▅ ▅▅",
            "is_moving": moving,
            "part": "外卦" if is_upper else "内卦",
            "trigram": trigram,
            "gan": gan,
            "zhi": zhi,
            "pillar": gan + zhi,
            "element": element,
            "liu_qin": liu_qin,
            "liu_qin_note": LIU_QIN_NOTE[liu_qin],
            "liu_shen": god,
            "liu_shen_note": LIU_SHEN_NOTE[god],
            "wang_xiang": wx,
            "wang_xiang_note": wx_note,
            "is_shi": i == meta["shi"],
            "is_ying": i == meta["ying"],
        })
    return rows, gods


def liuyao_chart(
    lines: list[int],
    when: _dt.datetime | None = None,
    topic: str = "决策",
    gender: str = "男",
    question: str = "",
) -> dict[str, Any]:
    """六爻纳甲装卦 + 解读。

    Args:
        lines: 六个爻值（6 老阴 / 7 少阳 / 8 少阴 / 9 老阳），自初爻到上爻。
        when: 起卦时刻，用于排六神（日干）与论旺衰（月支）；默认此刻。
        topic: 所问之事，决定用神取哪一亲（见 ``DIVINATION_TOPICS``）。
        gender: 男 / 女，仅影响「感情」一类取用。
        question: 用户的问题原文，仅作回显。

    Returns:
        可直接序列化的卦例字典。
    """
    if len(lines) != 6:
        raise ValueError("六爻必须是 6 个爻值")
    bad = [v for v in lines if v not in YAO_VALUES]
    if bad:
        raise ValueError(f"爻值只能是 6/7/8/9，收到：{bad}")
    if gender not in ("男", "女"):
        raise ValueError("gender 只能是「男」或「女」")

    when = when or _dt.datetime.now()
    ctx = _day_context(when)
    start_god = LIU_SHEN_START[ctx["day_gan"]]

    ben_lines = [1 if YAO_IS_YANG[v] else 0 for v in lines]
    bian_lines = [
        (0 if v == 9 else 1) if YAO_IS_MOVING[v] else (1 if YAO_IS_YANG[v] else 0)
        for v in lines
    ]
    ben = hexagram_of(ben_lines)
    bian = hexagram_of(bian_lines) if any(YAO_IS_MOVING[v] for v in lines) else None
    # 装卦要的是**原始爻值**（定动爻与老少），不是二值化后的爻型
    rows, gods = _yao_rows(lines, ben, ctx)

    # 动爻：阳动变阴、阴动变阳
    moving = [r for r in rows if r["is_moving"]]

    # 用神：按所问之事取一亲；「感情」女命取官鬼
    spec = DIVINATION_TOPICS.get(topic, DIVINATION_TOPICS["决策"])
    yong_name = spec["yong"]
    if topic == "感情" and gender == "女":
        yong_name = spec.get("yong_female", spec["yong"])
    yong_rows = [r for r in rows if r["liu_qin"] == yong_name]
    shi_row = rows[ben["shi"]]
    ying_row = rows[ben["ying"]]

    points: list[str] = []
    points.append(
        f"本卦「{ben['name']}」，属{ben['palace']}宫（{ben['element']}），"
        f"{ben['order']}卦；世爻在{shi_row['position']}、"
        f"应爻在{ying_row['position']}——世爻代表你自己，应爻代表对方或所问之事。"
    )
    points.append(
        f"起卦日 {ctx['day_gan_zhi']}日、月建{ctx['month_zhi']}月。"
        f"六神按日干「{ctx['day_gan']}」起「{start_god}」，自初爻往上顺排"
        f"（{'、'.join(gods)}）——"
        f"六神是古人给每爻加的一层「旁注」，看它落在哪一爻，"
        f"就知道那一爻带的是什么味道。"
    )
    if moving:
        where = "、".join(r["position"] for r in moving)
        points.append(
            f"动爻在{where}（共 {len(moving)} 个）——动爻是事情变化的地方，"
            f"动得越多，这件事变数越大、越不容易按原计划走。"
        )
        if bian is not None:
            points.append(f"动爻变后得变卦「{bian['name']}」，代表事情的最终走向。")
    else:
        points.append(
            "全卦无动爻——这件事眼下没有明显变动，吉凶基本停在现状，宜守不宜躁。"
        )

    # 世爻（我）的处境
    points.append(
        f"世爻{shi_row['pillar']}（{shi_row['element']}）"
        f"{shi_row['wang_xiang']}——{shi_row['wang_xiang_note']}"
        f"；临{shi_row['liu_shen']}（{shi_row['liu_shen_note']}）"
    )
    if shi_row["is_moving"]:
        points.append("世爻发动：你自己这边会主动起变化，事情多由你的动作推动。")

    # 用神（事）的处境
    if yong_rows:
        # 「旺相休囚死」在这个字符串里的下标越小越强，取下标最小的那一个
        best = min(yong_rows, key=lambda r: "旺相休囚死".index(r["wang_xiang"]))
        where = "、".join(r["position"] for r in yong_rows)
        points.append(
            f"用神取「{yong_name}」（{LIU_QIN_NOTE[yong_name]}），"
            f"出现在{where}；其中{best['position']}最得力——"
            f"{best['pillar']}（{best['wang_xiang']}，{best['wang_xiang_note']}）"
            f"，临{best['liu_shen']}（{best['liu_shen_note']}）。{spec['hint']}"
        )
        if any(r["is_moving"] for r in yong_rows):
            points.append(
                "用神发动：事情本身在变化，结果会明显偏离现在的样子。"
            )
    else:
        points.append(
            f"用神「{yong_name}」没有出现在卦里——传统叫「用神不上卦」，"
            f"这一件事的着力点不显，宜缓不宜急，等时机更明朗再定。"
        )

    # 倾向：用神旺相 + 世爻不弱 -> 吉；用神休囚死或世爻受克 -> 守
    score = 0
    if yong_rows:
        score += {"旺": 3, "相": 2, "休": 0, "囚": -1, "死": -2}[
            min(yong_rows, key=lambda r: "旺相休囚死".index(r["wang_xiang"]))["wang_xiang"]
        ]
    score += {"旺": 2, "相": 1, "休": 0, "囚": -1, "死": -2}[shi_row["wang_xiang"]]
    score += LIU_SHEN_WEIGHT.get(shi_row["liu_shen"], 0) // 2
    if len(moving) >= 3:
        score -= 2  # 动爻过多主反复

    if score >= 3:
        stance, level = "宜主动", "旺"
    elif score >= 0:
        stance, level = "稳中求进", "平"
    elif score >= -3:
        stance, level = "宜守成", "煞"
    else:
        stance, level = "宜退守", "大凶"

    plain = (
        f"这一卦本卦「{ben['name']}」，"
        f"{'变卦「' + bian['name'] + '」' if bian else '没有动爻'}"
        f"；你在{shi_row['position']}（{shi_row['wang_xiang']}），"
        f"问的「{topic}」看{yong_name if yong_rows else '用神不显'}，"
        f"整体{stance}。"
    )

    return {
        "mode": "liuyao",
        "question": question.strip(),
        "topic": topic,
        "gender": gender,
        "when": when.strftime("%Y-%m-%d %H:%M"),
        "day": ctx,
        "ben": {
            "name": ben["name"], "upper": ben["upper"], "lower": ben["lower"],
            "palace": ben["palace"], "element": ben["element"],
            "order": ben["order"],
            "symbol": TRIGRAM_GUA_INFO[ben["upper"]]["symbol"]
                     + TRIGRAM_GUA_INFO[ben["lower"]]["symbol"],
        },
        "bian": None if bian is None else {
            "name": bian["name"], "upper": bian["upper"], "lower": bian["lower"],
            "palace": bian["palace"], "element": bian["element"],
            "symbol": TRIGRAM_GUA_INFO[bian["upper"]]["symbol"]
                     + TRIGRAM_GUA_INFO[bian["lower"]]["symbol"],
        },
        "lines": rows,
        "moving": [r["position"] for r in moving],
        "shi": {"position": shi_row["position"], "pillar": shi_row["pillar"],
                "liu_qin": shi_row["liu_qin"], "liu_shen": shi_row["liu_shen"],
                "wang_xiang": shi_row["wang_xiang"], "is_moving": shi_row["is_moving"]},
        "ying": {"position": ying_row["position"], "pillar": ying_row["pillar"],
                 "liu_qin": ying_row["liu_qin"], "liu_shen": ying_row["liu_shen"]},
        "yong": {"name": yong_name, "note": LIU_QIN_NOTE[yong_name],
                 "positions": [r["position"] for r in yong_rows],
                 "on_hexagram": bool(yong_rows)},
        "score": score,
        "stance": stance,
        "level": level,
        "plain": plain,
        "points": points,
        "rules_version": DIVINATION_RULES_VERSION,
    }


# ---------------------------------------------------------------- 梅花易数
def _meihua_lines(upper: str, lower: str) -> list[int]:
    """上卦 + 下卦 -> 六爻阴阳（1 阳 / 0 阴，自下而上）。"""
    return list(TRIGRAM_BITS[lower]) + list(TRIGRAM_BITS[upper])


def _ti_yong(lines: list[int], moving_idx: int) -> tuple[tuple[int, int, int],
                                                         tuple[int, int, int]]:
    """动爻所在的那一个经卦为「用」，另一个为「体」。"""
    if moving_idx < 3:
        return tuple(lines[3:6]), tuple(lines[0:3])  # 体=上卦, 用=下卦
    return tuple(lines[0:3]), tuple(lines[3:6])      # 体=下卦, 用=上卦


def meihua_chart(
    when: _dt.datetime | None = None,
    numbers: list[int] | None = None,
    question: str = "",
    topic: str = "决策",
) -> dict[str, Any]:
    """梅花易数：时间起卦或数字起卦 -> 主 / 互 / 变三卦与体用吉凶。

    Args:
        when: 起卦时刻；给 ``numbers`` 时可省略。
        numbers: 2~3 个正整数。前两个定上卦 / 下卦（除 8 取余），
            第三个定动爻（除 6 取余）；只给两个则按两数之和定动爻。
        question: 问题原文，仅作回显。
        topic: 所问之事，仅作回显。

    Returns:
        可直接序列化的卦例字典。
    """
    when = when or _dt.datetime.now()
    solar_cls = _require_solar()
    lunar = solar_cls.fromYmdHms(
        when.year, when.month, when.day, when.hour, when.minute, 0
    ).getLunar()

    if numbers:
        cleaned = [int(n) for n in numbers if int(n) > 0]
        if len(cleaned) < 2:
            raise ValueError("数字起卦至少需要两个正整数")
        upper_n, lower_n = cleaned[0], cleaned[1]
        moving_n = cleaned[2] if len(cleaned) > 2 else cleaned[0] + cleaned[1]
        source = "数字起卦"
        basis = (
            f"取数 {upper_n}、{lower_n}"
            f"{'' if len(cleaned) > 2 else '（动爻取两数之和）'}"
            f"{'' if len(cleaned) <= 2 else f'、{cleaned[2]}'}："
            f"上卦={upper_n}÷8 余 {upper_n % 8 or 8}，"
            f"下卦={lower_n}÷8 余 {lower_n % 8 or 8}，"
            f"动爻={moving_n}÷6 余 {moving_n % 6 or 6}。"
        )
    else:
        year_num = EARTHLY_BRANCHES.index(lunar.getYearZhi()) + 1
        month_num = abs(lunar.getMonth())
        day_num = lunar.getDay()
        hour_num = EARTHLY_BRANCHES.index(lunar.getTimeZhi()) + 1
        upper_n = year_num + month_num + day_num
        lower_n = upper_n + hour_num
        moving_n = lower_n
        source = "时间起卦"
        basis = (
            f"农历 {lunar.getYearInGanZhi()}年"
            f"{lunar.getMonthInChinese()}月{lunar.getDayInChinese()}日"
            f"{lunar.getTimeZhi()}时："
            f"年支{lunar.getYearZhi()}数{year_num} + 月{month_num} + 日{day_num}"
            f" = {upper_n}，除 8 余 {upper_n % 8 or 8} 得上卦；"
            f"再加时支数 {hour_num} = {lower_n}，除 8 余 {lower_n % 8 or 8} 得下卦；"
            f"总数 {moving_n} 除 6 余 {moving_n % 6 or 6} 得动爻。"
        )

    upper = NUM_TO_TRIGRAM[upper_n % 8 or 8]
    lower = NUM_TO_TRIGRAM[lower_n % 8 or 8]
    moving_idx = (moving_n % 6 or 6) - 1  # 转 0-based

    lines = _meihua_lines(upper, lower)
    # 变卦：动爻阴阳互变
    changed = list(lines)
    changed[moving_idx] = 1 - changed[moving_idx]
    # 互卦：去掉初爻与上爻，234 为下卦、345 为上卦
    hu_lower = tuple(lines[1:4])
    hu_upper = tuple(lines[2:5])

    ti_bits, yong_bits = _ti_yong(lines, moving_idx)
    ti = _trigram_of(ti_bits)
    yong = _trigram_of(yong_bits)
    ti_element = TRIGRAM_GUA_INFO[ti]["element"]
    yong_element = TRIGRAM_GUA_INFO[yong]["element"]

    relation = _relation_of(yong_element, ti_element)  # 用以体为「我」
    if ti_element == yong_element:
        verdict_key = "比和"
    elif relation == "生我":
        verdict_key = "用生体"
    elif relation == "我生":
        verdict_key = "体生用"
    elif relation == "我克":
        verdict_key = "体克用"
    else:
        verdict_key = "用克体"
    verdict, verdict_note = MEIHUA_VERDICT[verdict_key]

    zhu = hexagram_of(lines)
    hu = hexagram_of(list(hu_lower) + list(hu_upper))
    bian = hexagram_of(changed)

    month_zhi = lunar.getMonthZhi()
    ti_wx, ti_wx_note = _wang_xiang_of(ti_element, month_zhi)

    points = [
        f"起卦方式：{source}。{basis}",
        f"主卦「{zhu['name']}」（{zhu['upper']}上{zhu['lower']}下），"
        f"动爻在第 {moving_idx + 1} 爻。",
        f"动爻在{'下卦' if moving_idx < 3 else '上卦'}，"
        f"所以{'下' if moving_idx < 3 else '上'}卦「{yong}」为用（事情），"
        f"{'上' if moving_idx < 3 else '下'}卦「{ti}」为体（你自己）。",
        f"体卦{ti}属{ti_element}、用卦{yong}属{yong_element}，"
        f"是「{verdict_key}」——{verdict_note}",
        f"体卦当月{ti_wx}（{ti_wx_note}）：体宜旺不宜衰，"
        f"体旺则你扛得住，体衰则要先补自己的底气。",
        f"互卦「{hu['name']}」看过程，变卦「{bian['name']}」看结果。",
    ]

    # 档位只由体用生克定，不再拿「体之衰旺」二次降档——
    # 体衰只是说「你当下扛不住」，它已经在 points 里作为解释给出；
    # 若再动档位，会出现「小吉却标成煞档」这种自相矛盾的显示。
    level = {"大吉": "旺", "小吉": "平", "小凶": "煞", "凶": "大凶"}[verdict]

    plain = (
        f"起得主卦「{zhu['name']}」，你在「{ti}」、所问之事在「{yong}」，"
        f"{ti_element}与{yong_element}是「{verdict_key}」——{verdict}；"
        f"过程看「{hu['name']}」、结果看「{bian['name']}」。"
    )

    return {
        "mode": "meihua",
        "question": question.strip(),
        "topic": topic,
        "when": when.strftime("%Y-%m-%d %H:%M"),
        "source": source,
        "basis": basis,
        "numbers": list(numbers) if numbers else None,
        "zhu": {
            "name": zhu["name"], "upper": zhu["upper"], "lower": zhu["lower"],
            "symbol": TRIGRAM_GUA_INFO[zhu["upper"]]["symbol"]
                     + TRIGRAM_GUA_INFO[zhu["lower"]]["symbol"],
        },
        "hu": {
            "name": hu["name"], "upper": _trigram_of(hu_upper),
            "lower": _trigram_of(hu_lower),
            "symbol": TRIGRAM_GUA_INFO[_trigram_of(hu_upper)]["symbol"]
                     + TRIGRAM_GUA_INFO[_trigram_of(hu_lower)]["symbol"],
        },
        "bian": {
            "name": bian["name"], "upper": bian["upper"], "lower": bian["lower"],
            "symbol": TRIGRAM_GUA_INFO[bian["upper"]]["symbol"]
                     + TRIGRAM_GUA_INFO[bian["lower"]]["symbol"],
        },
        "moving_index": moving_idx + 1,
        "ti": {"trigram": ti, "element": ti_element,
               "symbol": TRIGRAM_GUA_INFO[ti]["symbol"], "wang_xiang": ti_wx,
               "wang_xiang_note": ti_wx_note},
        "yong": {"trigram": yong, "element": yong_element,
                 "symbol": TRIGRAM_GUA_INFO[yong]["symbol"]},
        "relation": verdict_key,
        "verdict": verdict,
        "verdict_note": verdict_note,
        "level": level,
        "plain": plain,
        "points": points,
        "rules_version": DIVINATION_RULES_VERSION,
        "xian_tian_num": {k: XIAN_TIAN_NUM[k] for k in
                          ("乾", "兑", "离", "震", "巽", "坎", "艮", "坤")},
    }


def build_divination(
    mode: str,
    lines: list[int] | None = None,
    when: _dt.datetime | None = None,
    numbers: list[int] | None = None,
    topic: str = "决策",
    gender: str = "男",
    question: str = "",
) -> dict[str, Any]:
    """统一入口：按 ``mode`` 分派到六爻或梅花。

    Args:
        mode: ``liuyao``（六爻）或 ``meihua``（梅花易数）。
        lines: 六爻模式必填，六个爻值。
        numbers: 梅花模式的数字起卦入参；不给则按时辰起卦。
        其余参数见 :func:`liuyao_chart` 与 :func:`meihua_chart`。
    """
    if mode == "liuyao":
        if not lines:
            raise ValueError("六爻模式必须给六个爻值（6/7/8/9）")
        return liuyao_chart(lines, when=when, topic=topic,
                            gender=gender, question=question)
    if mode == "meihua":
        return meihua_chart(when=when, numbers=numbers,
                            question=question, topic=topic)
    raise ValueError("mode 只能是 liuyao 或 meihua")
