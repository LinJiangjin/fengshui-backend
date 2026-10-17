# -*- coding: utf-8 -*-
"""规则引擎单元测试。

这些断言是「大模型不可介入」的底线：算法一旦改动就会红。
运行：python -m unittest discover -s tests -v
"""

import unittest

from app.engine import (
    orient,
    degree_to_mountain,
    build_palaces,
    center_star_of_year,
    pick_extremes,
    score_of,
)


class TestCompass(unittest.TestCase):
    def test_due_north_is_zi(self):
        self.assertEqual(degree_to_mountain(0), "子")
        self.assertEqual(degree_to_mountain(358), "子")   # 子山 352.5 ~ 7.5
        self.assertEqual(degree_to_mountain(353), "子")

    def test_mountain_boundary(self):
        # 壬山居中 345 度，区间 337.5 ~ 352.5
        self.assertEqual(degree_to_mountain(345), "壬")
        self.assertEqual(degree_to_mountain(352), "壬")
        self.assertEqual(degree_to_mountain(353), "子")

    def test_cardinal_mountains(self):
        self.assertEqual(degree_to_mountain(90), "卯")    # 正东
        self.assertEqual(degree_to_mountain(180), "午")   # 正南
        self.assertEqual(degree_to_mountain(270), "酉")   # 正西

    def test_design_case_358(self):
        """设计稿 S2 场景：358 度、磁偏角 -5.2 -> 子山午向。"""
        r = orient(358.0, -5.2)
        self.assertEqual(r["title"], "子山午向")
        self.assertEqual(r["house_type"], "坎宅")
        self.assertEqual(r["readable"], "坐北朝南")
        self.assertEqual(r["facing"], "午")

    def test_opposite_direction(self):
        r = orient(180.0, 0.0)
        self.assertEqual(r["title"], "午山子向")
        self.assertEqual(r["house_type"], "离宅")

    def test_declination_applied(self):
        a = orient(0.0, 0.0)
        b = orient(0.0, 20.0)
        self.assertNotEqual(a["title"], b["title"])


class TestFlyingStar(unittest.TestCase):
    def test_center_star_anchor(self):
        self.assertEqual(center_star_of_year(2024), 3)
        self.assertEqual(center_star_of_year(2025), 2)
        self.assertEqual(center_star_of_year(2026), 1)
        self.assertEqual(center_star_of_year(2027), 9)

    def test_nine_palaces_unique(self):
        palaces = build_palaces(2026)
        self.assertEqual(len(palaces), 9)
        stars = sorted(p["star"] for p in palaces)
        self.assertEqual(stars, [1, 2, 3, 4, 5, 6, 7, 8, 9])

    def test_luoshu_mapping_stable(self):
        palaces = {p["luoshu"]: p for p in build_palaces(2026)}
        self.assertEqual(palaces[5]["direction"], "中宫")
        self.assertEqual(palaces[9]["direction"], "正南")
        self.assertEqual(palaces[1]["direction"], "正北")
        self.assertEqual(palaces[3]["direction"], "正东")
        self.assertEqual(palaces[7]["direction"], "正西")

    def test_score_bounded(self):
        for year in range(2020, 2040):
            s = score_of(build_palaces(year))
            self.assertTrue(0 <= s <= 100, f"{year} -> {s}")

    def test_extremes(self):
        palaces = build_palaces(2026)
        ex = pick_extremes(palaces)
        self.assertIn(ex["worst"]["level"], ("大凶", "煞"))
        self.assertEqual(ex["best"]["level"], "旺")


if __name__ == "__main__":
    unittest.main()


class TestNoMarkdownInOutput(unittest.TestCase):
    """所有下发到客户端的文案都不得含 markdown 标记。

    后端文案是给 Flutter 纯文本渲染的，``**`` 之类的标记会原样露出。
    这条护栏曾经连续踩了四次，所以这里**跨引擎统一扫一遍**：
    取各引擎的一份代表性输出，递归遍历所有字符串，发现标记即红。
    """

    def _walk(self, node, path="root"):
        if isinstance(node, str):
            for mark in ("**", "__", "## ", "`"):
                self.assertNotIn(mark, node, f"{path} 含 {mark!r}: {node[:60]}")
        elif isinstance(node, dict):
            for k, v in node.items():
                self._walk(v, f"{path}.{k}")
        elif isinstance(node, (list, tuple)):
            for i, v in enumerate(node):
                self._walk(v, f"{path}[{i}]")

    def test_all_engines(self):
        import datetime as dt

        from app.engine import (
            build_bazi,
            build_bazi_fortune,
            build_bazhai,
            build_divination,
            build_match,
            build_ziwei,
            build_ziwei_reading,
            build_ziwei_years,
            day_almanac,
            house_chart,
            meihua_chart,
            month_chart,
            true_solar_time,
        )

        when = dt.datetime(2026, 10, 17, 9, 30)
        bazi = build_bazi(1991, 9, 10, 7, 35, gender="男", longitude=113.26)
        true_dt, _ = true_solar_time(1991, 9, 10, 7, 35, 113.26)
        ziwei = build_ziwei(1991, 9, 10, 7, 35, gender="男", longitude=113.26)

        samples = {
            "bazi": bazi,
            "bazi_fortune": build_bazi_fortune(bazi, true_dt, 1991),
            "bazhai": build_bazhai(1991, gender="男", degree=0.0),
            "day_almanac": day_almanac(dt.date(2026, 10, 17)),
            "month_chart": month_chart(dt.date(2026, 10, 17)),
            "house_chart": house_chart(degree=0.0, yun=8),
            "ziwei": ziwei,
            "ziwei_reading": build_ziwei_reading(ziwei),
            "ziwei_years": build_ziwei_years(ziwei, birth_year=1991, count=3),
            "liuyao": build_divination("liuyao", lines=[7, 9, 8, 6, 7, 8],
                                       when=when, topic="财运"),
            "meihua": meihua_chart(when=when, topic="出行"),
            "marriage_zodiac": build_match("zodiac", a_year=1990, b_year=1991),
            "marriage_bazi": build_match(
                "bazi",
                a={"year": 1991, "month": 9, "day": 10, "hour": 7,
                   "gender": "男", "longitude": 113.26},
                b={"year": 1993, "month": 3, "day": 5, "hour": 14,
                   "gender": "女", "longitude": 116.4},
            ),
        }
        for name, chart in samples.items():
            self._walk(chart, name)
