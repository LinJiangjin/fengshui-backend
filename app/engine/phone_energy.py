# -*- coding: utf-8 -*-
"""号码八星（数字能量）——确定性计算层。

⚠ 性质说明（这一段必须原样传达给用户，不要淡化）
------------------------------------------------
数字能量是**近现代民间民俗说法**，没有《紫白诀》《玄空秘旨》这类术数典籍支撑，
学术与流派共识度远低于玄空 / 八字 / 六爻。本模块只做两件事：

1. **数组映射与统计**——哪两个数字属于哪一星，这是唯一站得住的部分，
   且有严格的自洽性可验证（八星各 8 组 = 64 = {1,2,3,4,6,7,8,9} 的全部有序对）。
2. **把统计结果翻成人话**——文案一律停留在「性格与倾向」，
   **不断具体事件**（不断「几月破财」「哪年离婚」）。

结果里必须显式标注它是民俗参考，不允许与玄空 / 八字同等权威地呈现。

隐私
----
号码属个人信息。本模块**默认不回显完整号码**：结果里只给脱敏后的
``masked``，错误文案也只报脱敏形式，避免号码进日志与错误回显。

算法
----
* 相邻两位**重叠**拆分：``13812345678`` -> 13、38、81、12、23、34、45、56、67、78。
* 0 与 5 不参与分组：0 主削弱 / 隐藏，5 主加强 / 显化，另按修饰规则计分。
* 末尾若干对（默认 3）权重加倍——通行说法是尾号影响最重。
"""

from __future__ import annotations

from typing import Any

from .constants import (
    EIGHT_STARS,
    PHONE_KINDS,
    PHONE_LEVELS,
    PHONE_RULES_VERSION,
    PHONE_SCORE,
)

__all__ = [
    "analyze_number",
    "mask_number",
    "split_pairs",
    "star_of_pair",
]

# 星曜展示顺序：吉在前、凶在后，用于分布表与「主导星」同票时的取舍
_STAR_ORDER = ("天医", "生气", "延年", "伏位", "六煞", "祸害", "五鬼", "绝命")

_PAIR_TO_STAR: dict[str, str] = {
    pair: star
    for star, info in EIGHT_STARS.items()
    for pair in info["pairs"]
}


def star_of_pair(pair: str) -> str | None:
    """两位数字 -> 星名；含 0 / 5 或非两位时返回 None。"""
    if len(pair) != 2 or not pair.isdigit():
        return None
    return _PAIR_TO_STAR.get(pair)


def split_pairs(digits: str) -> list[str]:
    """相邻两位重叠拆分：``138`` -> ``['13', '38']``。"""
    return [digits[i:i + 2] for i in range(len(digits) - 1)]


def mask_number(raw: str, kind: str = "general") -> str:
    """脱敏：手机号保留前 3 后 4，其余保留首尾各 2 位。

    返回的字符串只用于展示与错误提示，**绝不**是原始号码。
    """
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) <= 4:
        return "*" * len(digits)
    if kind == "mobile" and len(digits) >= 7:
        return f"{digits[:3]}****{digits[-4:]}"
    keep = 2
    return f"{digits[:keep]}{'*' * (len(digits) - keep * 2)}{digits[-keep:]}"


def _clean(raw: str) -> str:
    return "".join(ch for ch in str(raw) if ch.isdigit())


def _level_of(score: int) -> tuple[str, str]:
    for threshold, name, level in PHONE_LEVELS:
        if score >= threshold:
            return name, level
    last = PHONE_LEVELS[-1]
    return last[1], last[2]


def analyze_number(raw: str, kind: str = "general") -> dict[str, Any]:
    """算一组号码的八星结构。

    Args:
        raw: 号码原文（可含分隔符与字母，只取数字部分）。
        kind: ``mobile`` / ``plate`` / ``address`` / ``general``，
            只影响脱敏方式与位数校验，算法不分家。

    Returns:
        可直接序列化的结果；**不含原始号码**，只含 ``masked``。

    Raises:
        ValueError: 数字位数不足或超出上限。
    """
    if kind not in PHONE_KINDS:
        raise ValueError(f"kind 只能是 {'、'.join(PHONE_KINDS)} 之一，收到：{kind}")

    digits = _clean(raw)
    if len(digits) < 2:
        raise ValueError("至少需要两位数字才能看数组")
    if len(digits) > 20:
        raise ValueError("号码太长，最多支持 20 位数字")

    cfg = PHONE_SCORE
    pairs = split_pairs(digits)
    tail_from = max(0, len(pairs) - cfg["tail_pairs"])

    items: list[dict[str, Any]] = []
    counts: dict[str, int] = {star: 0 for star in _STAR_ORDER}
    zeros = digits.count("0")
    fives = digits.count("5")

    delta = 0
    for i, pair in enumerate(pairs):
        star = star_of_pair(pair)
        if star is None:
            items.append({
                "pair": pair, "star": None, "level": "平",
                "is_tail": i >= tail_from, "score": 0,
                "plain": "含 0 或 5，不归入八星，按修饰规则另行计分",
            })
            continue
        weight = cfg["star"][star]
        is_tail = i >= tail_from
        score = weight * cfg["tail_factor"] if is_tail else weight
        delta += score
        counts[star] += 1
        items.append({
            "pair": pair, "star": star,
            "level": EIGHT_STARS[star]["level"],
            "kind": EIGHT_STARS[star]["kind"],
            "is_tail": is_tail,
            "score": score,
            "plain": EIGHT_STARS[star]["plain"],
        })

    zero_delta = cfg["zero"] * zeros
    five_delta = cfg["five"] * fives
    delta += zero_delta + five_delta

    score = max(cfg["min"], min(cfg["max"], cfg["base"] + delta))
    name, level = _level_of(score)

    # 主导星：出现最多；同票按「吉在前」的顺序取，并且吉凶不同的同票取吉的
    ranked = sorted(_STAR_ORDER, key=lambda s: (-counts[s], _STAR_ORDER.index(s)))
    dominant = ranked[0] if counts[ranked[0]] > 0 else None

    # 尾部有效组合（最后三对里能归入八星的）
    tail_stars = [it["star"] for it in items
                  if it["is_tail"] and it["star"] is not None]

    good = sum(counts[s] for s in ("天医", "生气", "延年", "伏位"))
    bad = sum(counts[s] for s in ("绝命", "五鬼", "祸害", "六煞"))

    points = [
        f"相邻两位重叠拆分，共 {len(pairs)} 组：{'、'.join(pairs)}。",
        f"八星分布：吉星 {good} 组、凶星 {bad} 组"
        + (f"，其中出现最多的是「{dominant}」（{counts[dominant]} 组）。"
           if dominant else "。"),
    ]
    if tail_stars:
        points.append(
            f"末尾三组是 {'、'.join(tail_stars)}——通行说法认为尾号影响最重，"
            f"所以这几组的权重按双倍计。"
        )
    if zeros:
        points.append(
            f"含 {zeros} 个 0：0 主削弱与隐藏，会削弱相邻数组的能量（{zero_delta} 分）。"
        )
    if fives:
        points.append(
            f"含 {fives} 个 5：5 主加强与显化，会放大前后数字的链接（+{five_delta} 分）。"
        )
    # 这一句必须跟**分数档位**一致，不能只看原始数量——
    # 尾号是双倍权重，数量各半但尾部偏吉时总分仍会偏高，两边打架用户就看不懂了
    if good > bad:
        points.append("吉星多于凶星，整体偏向稳顺；底子不错，剩下的看怎么用。")
    elif bad > good:
        points.append("凶星多于吉星，整体波动偏大；重大决定上多留一步余地。")
    elif tail_stars:
        points.append(
            f"吉凶数量各半，但末尾三组是{'、'.join(tail_stars)}——"
            f"尾号权重加倍后整体仍偏{name}，属于「看自己怎么把握」的号码，"
            f"不宜过度依赖。"
        )
    else:
        points.append("吉凶各半，属于「看自己怎么把握」的号码，不宜过度依赖。")

    plain = (
        f"这组号码共 {len(pairs)} 组，吉星 {good} 组、凶星 {bad} 组"
        + (f"，主导是「{dominant}」" if dominant else "")
        + f"，综合{name}。"
    )

    return {
        "kind": kind,
        "masked": mask_number(digits, kind),
        "length": len(digits),
        "pairs": pairs,
        "items": items,
        "distribution": {s: counts[s] for s in _STAR_ORDER},
        "dominant": dominant,
        "dominant_plain": EIGHT_STARS[dominant]["plain"] if dominant else "",
        "tail_stars": tail_stars,
        "zeros": zeros,
        "fives": fives,
        "good": good,
        "bad": bad,
        "score": score,
        "level": name,
        "level_key": level,
        "plain": plain,
        "points": points,
        "advice": _advice_of(dominant, good, bad, name),
        # 性质声明：前端必须原样展示，不能淡化
        "nature_note": (
            "数字能量属近现代民间民俗说法，没有术数典籍支撑，"
            "仅供参考娱乐，不宜据以做重大决定。"
        ),
        "rules_version": PHONE_RULES_VERSION,
    }


def _advice_of(
    dominant: str | None, good: int, bad: int, level_name: str
) -> str:
    """一句落到「怎么用」上的建议。"""
    if dominant == "天医":
        return "财气组占主导，适合拿来做长期用的主号；但财来得顺也去得快，宜主动做储蓄安排。"
    if dominant == "生气":
        return "贵人组占主导，适合需要对外联络、靠人脉推进的用途；别把人脉只当人情用。"
    if dominant == "延年":
        return "事业组占主导，适合长期投入的事；压力也会跟着来，注意别把弦绷太紧。"
    if dominant == "伏位":
        return "守成组占主导，平稳但机会不多；想要突破的话，得主动制造变化，别只等。"
    if dominant == "绝命":
        return "起伏组占主导，敢拼但也容易冲过头；投资与情绪上都宜给自己留一条退路。"
    if dominant == "五鬼":
        return "变动组占主导，想法多、变动也多；重要的事宜提前锁定，别拖到最后。"
    if dominant == "祸害":
        return "口舌组占主导，说话容易惹误会；沟通上多确认一遍，比事后解释省力。"
    if dominant == "六煞":
        return "桃花组占主导，人缘旺但劳心；感情与钱财上都宜划清界限。"
    if good > bad:
        return "吉星占优，底子不错；号码只是加分项，真正起作用的还是怎么用。"
    if bad > good:
        return "凶星占优，波动偏大；不宜把它当成决定性因素，重大决定请以其专业判断为准。"
    return "吉凶各半，属中性号码；参考价值有限，不必为换号而换号。"
