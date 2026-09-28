# -*- coding: utf-8 -*-
"""二十四山定向：把罗盘度数换算成坐山 / 向山 / 宅卦。"""

from .constants import (
    MOUNTAINS,
    TRIGRAM_BY_MOUNTAIN,
    TRIGRAM_INFO,
    HOUSE_TYPE_DESC,
)

MOUNTAIN_SPAN = 15.0  # 每山 15 度


def normalize_degree(degree: float) -> float:
    """归一化到 [0, 360)。"""
    return degree % 360.0


def degree_to_mountain(degree: float) -> str:
    """度数 -> 山名。子山居中 0 度，每山 15 度。"""
    d = normalize_degree(degree)
    index = int(round(d / MOUNTAIN_SPAN)) % 24
    return MOUNTAINS[index]


def opposite_mountain(mountain: str) -> str:
    """对冲之山（相隔 12 位 = 180 度）。"""
    i = MOUNTAINS.index(mountain)
    return MOUNTAINS[(i + 12) % 24]


def mountain_offset(degree: float) -> float:
    """当前度数偏离所在山中心线的角度（度），用于判断是否需要校正。"""
    d = normalize_degree(degree)
    center = (int(round(d / MOUNTAIN_SPAN)) % 24) * MOUNTAIN_SPAN
    diff = d - center
    if diff > 180:
        diff -= 360
    if diff < -180:
        diff += 360
    return diff


def orient(degree: float, declination: float = 0.0) -> dict:
    """定向主入口。

    :param degree:        手机罗盘读到的磁方位角（度）
    :param declination:   当地磁偏角，真北 = 磁北 + declination
    :return: 坐向信息字典
    """
    raw = normalize_degree(degree)
    true_north = normalize_degree(raw + declination)

    sitting = degree_to_mountain(true_north)
    facing = opposite_mountain(sitting)
    trigram = TRIGRAM_BY_MOUNTAIN[sitting]
    info = TRIGRAM_INFO[trigram]
    facing_trigram = TRIGRAM_BY_MOUNTAIN[facing]

    return {
        "raw_degree": round(raw, 1),
        "degree": round(true_north, 1),
        "declination": round(declination, 1),
        "offset": round(mountain_offset(true_north), 1),
        "mountain": sitting,
        "facing": facing,
        # 例：子山午向
        "title": f"{sitting}山{facing}向",
        "trigram": trigram,
        "facing_trigram": facing_trigram,
        "direction": info["direction"],
        "facing_direction": TRIGRAM_INFO[facing_trigram]["direction"],
        "house_type": f"{trigram}宅",
        "readable": f"坐{info['direction'][1:]}朝{TRIGRAM_INFO[facing_trigram]['direction'][1:]}",
        "description": HOUSE_TYPE_DESC.get(trigram, ""),
    }
