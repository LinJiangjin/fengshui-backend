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
