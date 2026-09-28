# -*- coding: utf-8 -*-
"""玄空飞星 · 流年盘。

年星入中：以 2024 年（甲辰）三碧入中为锚点，逐年逆退一位，九年一循环。
入中之后按洛书轨迹顺飞，得到九宫星曜。
"""

from .constants import (
    FLYING_ORDER,
    PALACE_BY_LUOSHU,
    STAR_INFO,
    SCORE_BASE,
    SCORE_WEIGHT,
)

ANCHOR_YEAR = 2024
ANCHOR_STAR = 3  # 2024 甲辰年 · 三碧入中


def center_star_of_year(year: int) -> int:
    """某年的入中星（1-9）。"""
    delta = (year - ANCHOR_YEAR) % 9
    star = (ANCHOR_STAR - delta) % 9
    return 9 if star == 0 else star


def build_palaces(year: int) -> list:
    """生成流年九宫飞星盘。"""
    center = center_star_of_year(year)
    palaces = []
    for step, luoshu in enumerate(FLYING_ORDER):
        number = (center + step - 1) % 9 + 1
        trigram, direction = PALACE_BY_LUOSHU[luoshu]
        star = STAR_INFO[number]
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
        })
    return palaces


def score_of(palaces: list) -> int:
    """依据各宫吉凶加权得到综合评分。"""
    total = SCORE_BASE
    for p in palaces:
        if p["is_center"]:
            continue
        total += SCORE_WEIGHT.get(p["level"], 0)
    return max(0, min(100, total))


def pick_extremes(palaces: list) -> dict:
    """挑出最旺与最凶之宫，用于首页「今日吉位 / 今日忌方」。"""
    outer = [p for p in palaces if not p["is_center"]]
    best_rank = {8: 0, 9: 1, 1: 2, 6: 3, 4: 4, 3: 5}
    worst_rank = {5: 0, 2: 1, 7: 2, 3: 3}

    best = sorted(outer, key=lambda p: best_rank.get(p["star"], 9))[0]
    worst = sorted(outer, key=lambda p: worst_rank.get(p["star"], 9))[0]

    return {
        "best": {
            "direction": best["direction"],
            "trigram": best["trigram"],
            "star_name": best["star_name"],
            "label": best["label"],
            "level": best["level"],
            "note": best["note"],
            "title": f"{best['direction']} · {best['label']}",
        },
        "worst": {
            "direction": worst["direction"],
            "trigram": worst["trigram"],
            "star_name": worst["star_name"],
            "label": worst["label"],
            "level": worst["level"],
            "note": worst["note"],
            "title": f"{worst['direction']} · {worst['star_name']}",
        },
    }
