# -*- coding: utf-8 -*-
"""建议生成层。

MVP 阶段使用「规则 + 模板」生成，保证输出稳定可复现。
接入大模型时只需替换 enhance()，让模型改写 reason 文案，
不得改动由本模块算出的数值与宫位（见 README「AI 接入」章节）。
"""

import re

from .constants import STAR_INFO

# 向方（朝向所在宫）的吉凶决定采光与动线评价
LEVEL_GRADE = {"旺": "优", "平": "良", "煞": "弱", "大凶": "凶"}


def build_metrics(orientation: dict, palaces: list) -> list:
    """首页三项指标：藏风聚气 / 采光纳阳 / 动线生旺。"""
    facing_dir = orientation["facing_direction"]
    facing = next((p for p in palaces if p["direction"] == facing_dir), None)
    sitting_dir = orientation["direction"]
    sitting = next((p for p in palaces if p["direction"] == sitting_dir), None)

    facing_level = facing["level"] if facing else "平"
    sitting_level = sitting["level"] if sitting else "平"

    return [
        {
            "name": "藏风聚气",
            "grade": "优" if sitting_level == "旺" else ("良" if sitting_level == "平" else "弱"),
            "desc": "背有实墙，气流回旋" if sitting_level in ("旺", "平") else "坐山受煞，宜设屏风遮挡",
            "level": sitting_level,
        },
        {
            "name": "采光纳阳",
            "grade": LEVEL_GRADE.get(facing_level, "良"),
            "desc": "向方开阔，宜保持通透" if facing_level == "旺" else "向方受制，宜增镜面与暖光",
            "level": facing_level,
        },
        {
            "name": "动线生旺",
            "grade": "优" if facing_level in ("旺", "平") else "弱",
            "desc": "曲则有情，忌直冲" if facing_level in ("旺", "平") else "直冲气散，宜设玄关缓冲区",
            "level": facing_level,
        },
    ]


def build_daily_advice(daily: dict) -> list:
    """当日紫白提示：先说今日忌方，再说今日吉位。"""
    if not daily:
        return []
    worst = daily["worst"]
    best = daily["best"]
    return [
        {
            "type": "warn",
            "title": f"今日{worst['direction']}见{worst['star_name']}，宜静不宜动",
            "desc": f"{daily['date']}（{daily['day_pillar']}日）{worst['star_name']}临{worst['direction']}；{worst['note']}",
        },
        {
            "type": "good",
            "title": f"今日吉位在{best['direction']}，宜重点利用",
            "desc": f"{best['star_name']}临{best['direction']}，{best['note']}",
        },
    ]


def build_advice(orientation: dict, palaces: list, extremes: dict) -> list:
    """重点提示：先说煞位，再说旺位，最后说坐向格局。"""
    advice = []
    worst = extremes["worst"]
    best = extremes["best"]

    advice.append({
        "type": "warn",
        "title": f"{worst['direction']}见{worst['star_name']}，忌动土",
        "desc": f"建议该方位减少活动与修造；{STAR_INFO[_star_of(worst['star_name'])]['note']}",
    })

    advice.append({
        "type": "good",
        "title": f"{best['direction']}为{best['label']}，宜重点利用",
        "desc": best["note"],
    })

    advice.append({
        "type": "info",
        "title": f"{orientation['title']} · {orientation['house_type']}",
        "desc": orientation["description"] or "格局方正，保持明堂开阔即可。",
    })
    return advice


def _star_of(star_name: str) -> int:
    for number, info in STAR_INFO.items():
        if info["name"] == star_name:
            return number
    return 5


def _direction_of_star(palaces: list, star_name: str) -> str:
    """在流年盘里找某颗星所在的方位；找不到返回空串。"""
    for p in palaces:
        if p.get("star_name") == star_name:
            return p.get("direction", "")
    return ""


def _sha_direction(palaces: list, exclude=()) -> str:
    """找可「以凶压凶」的煞位：大凶优先，其次煞；跳过 exclude 中的方位。"""
    for level in ("大凶", "煞"):
        for p in palaces:
            if p.get("level") == level and p.get("direction") not in exclude:
                return p.get("direction", "")
    return ""


def _star_of_direction(palaces: list, direction: str) -> str:
    """某方位上的星曜名。"""
    for p in palaces:
        if p.get("direction") == direction:
            return p.get("star_name", "")
    return ""


def _bedroom_count(layout: str) -> int:
    """从户型串（如「3室2厅」）解析卧室数；解析不到按 1 室处理。"""
    m = re.search(r"(\d+)\s*室", layout or "")
    if m:
        n = int(m.group(1))
        if n > 0:
            return n
    return 1


def build_layout_guide(
    layout: str, orientation: dict, palaces: list, best: dict, worst: dict
) -> list:
    """按户型生成「功能区布局建议表」。

    原本这套规则写在客户端，导致方位与吉凶标签可能与后端不一致。
    现在改由后端统一下发，前端只负责渲染。
    """
    bedrooms = _bedroom_count(layout)
    facing = orientation.get("facing_direction") or "向方"
    sitting = orientation.get("direction") or "坐山方"
    best_dir = best.get("direction") or ""
    worst_dir = worst.get("direction") or ""

    wen_chang = _direction_of_star(palaces, "四绿") or best_dir
    sha = _sha_direction(palaces, exclude=("西北", best_dir)) or worst_dir

    rows = [
        {"type": "客厅", "good": f"{facing}（大门/阳台朝向）", "bad": f"中宫、{worst_dir}"},
        {"type": "主卧", "good": f"{sitting}（背对大门的里侧）", "bad": f"{worst_dir}、二黑位"},
        {"type": "厨房", "good": f"{sha}（以火压煞）", "bad": "西北、正南"},
        {"type": "卫生间", "good": f"{worst_dir}（以污化煞）", "bad": f"中宫、{best_dir}"},
        {"type": "入户门", "good": f"{facing}（纳气口）", "bad": "东北鬼门、绝命方"},
    ]
    if bedrooms >= 2:
        rows.insert(
            2,
            {"type": "次卧", "good": "进门左手边（青龙方）", "bad": f"进门右手边、{worst_dir}"},
        )
    if bedrooms >= 3:
        rows.insert(
            3,
            {"type": "书房/小卧", "good": f"{wen_chang}（文昌位）", "bad": f"{worst_dir}、二黑位"},
        )
    if bedrooms >= 4:
        rows.insert(
            4,
            {"type": "客房", "good": "宅后方或侧方", "bad": f"中宫、{worst_dir}"},
        )
    return rows


def build_furniture_tips(orientation: dict, palaces: list, best: dict, worst: dict) -> list:
    """家具摆放建议：按坐向 + 流年 / 日家星曜动态生成。

    与 build_advice 的区别：
        - build_advice 面向「重点提示」，先煞后旺；
        - 本函数面向「怎么摆家具」，逐件给出方位与理由。
    """
    best_dir = best.get("direction") or ""
    worst_dir = worst.get("direction") or ""
    best_star = best.get("star_name") or ""
    worst_star = worst.get("star_name") or ""
    best_label = best.get("label") or "旺位"
    sitting_dir = orientation.get("direction") or ""

    # 文昌位（四绿）与财位（八白）取自流年盘，取不到时退回当日旺位
    wen_chang = _direction_of_star(palaces, "四绿") or best_dir
    cai_wei = _direction_of_star(palaces, "八白") or best_dir

    # 灶台要压煞位：优先压当日忌方；但西北（乾位，火烧天门）不可用，
    # 也不该压在当日旺位上，这两种情况改取流年盘的煞位。
    if worst_dir and worst_dir not in ("西北", best_dir):
        zao_dir = worst_dir
        zao_star = worst_star
    else:
        zao_dir = _sha_direction(palaces, exclude=("西北", best_dir))
        zao_star = _star_of_direction(palaces, zao_dir) or worst_star

    return [
        {
            "type": "good",
            "title": f"沙发宜背靠实墙，朝向{best_dir}",
            "desc": (
                f"{best_dir}见{best_star}（{best_label}），沙发背靠实墙、面朝此方主事业稳固；"
                "忌背门而坐，可在沙发侧加矮柜挡煞。"
            ),
        },
        {
            "type": "good",
            "title": f"床头宜靠{sitting_dir}实墙，避开{worst_dir}",
            "desc": (
                f"床头靠{sitting_dir}（坐山方）有靠山之意，助眠安神；"
                f"{worst_dir}见{worst_star}，该方今日不宜久卧。"
            ),
        },
        {
            "type": "warn",
            "title": f"灶台宜压{zao_dir}，灶口朝{best_dir}"
            if zao_dir
            else f"灶口宜朝{best_dir}",
            "desc": (
                f"灶坐凶向吉：炉灶压{zao_dir}（{zao_star}）以火制煞，灶口朝{best_dir}纳吉；"
                if zao_dir
                else f"灶口朝{best_dir}（{best_label}）纳吉；"
            )
            + "忌设在西北（乾位，火烧天门），也忌与水池正对，"
            "两者间隔 60cm 以上，可用中岛或绿植作缓冲。",
        },
        {
            "type": "good",
            "title": f"书桌 / 办公位宜设{wen_chang}",
            "desc": (
                f"{wen_chang}为四绿文昌位，宜设书桌或办公位，利学业事业；"
                "忌背门而坐或正对卫生间门。"
            ),
        },
        {
            "type": "good",
            "title": f"水景 / 鱼缸宜放{cai_wei}",
            "desc": (
                f"{cai_wei}为八白财位，宜设鱼缸、流水摆件催财；"
                f"忌放在{worst_dir}（{worst_star}），以免动煞。"
            ),
        },
    ]


def enhance(advice: list, context: dict) -> list:
    """大模型增强钩子（MVP 未启用）。

    接入方式：
        1. 用 context（坐向 + 九宫 + RAG 检索到的典籍片段）构造 prompt；
        2. 以 JSON mode 强制模型只输出 {title, desc} 文案列表；
        3. 校验 schema 后再返回，任何数值/宫位字段一律以入参为准，不采信模型输出。
    未配置模型时直接返回规则生成的文案，保证链路可用。
    """
    return advice
