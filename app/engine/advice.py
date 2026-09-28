# -*- coding: utf-8 -*-
"""建议生成层。

MVP 阶段使用「规则 + 模板」生成，保证输出稳定可复现。
接入大模型时只需替换 enhance()，让模型改写 reason 文案，
不得改动由本模块算出的数值与宫位（见 README「AI 接入」章节）。
"""

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


def enhance(advice: list, context: dict) -> list:
    """大模型增强钩子（MVP 未启用）。

    接入方式：
        1. 用 context（坐向 + 九宫 + RAG 检索到的典籍片段）构造 prompt；
        2. 以 JSON mode 强制模型只输出 {title, desc} 文案列表；
        3. 校验 schema 后再返回，任何数值/宫位字段一律以入参为准，不采信模型输出。
    未配置模型时直接返回规则生成的文案，保证链路可用。
    """
    return advice
