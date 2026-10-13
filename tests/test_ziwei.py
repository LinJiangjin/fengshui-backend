# -*- coding: utf-8 -*-
"""紫微斗数排盘与解读的测试。

排盘部分校验的是**安星法的不变量**（十四主星不重不漏、紫府轴对称、
身宫只居六宫、大限连续），以及起例口诀的直接映射；
解读部分校验结构完整与空宫兜底。
"""

import datetime as _dt
import unittest

from app.engine.ziwei import (
    TIANFU_SERIES,
    ZIWEI_PALACES,
    ZIWEI_SERIES,
    SI_HUA,
    build_ziwei,
    palace_gan,
    wu_xing_ju,
    ziwei_palace,
)
from app.engine.ziwei_reading import build_ziwei_reading
from app.engine.ziwei_year import build_ziwei_years, gan_zhi_of_year

MAIN14 = [
    "紫微", "天机", "太阳", "武曲", "天同", "廉贞",
    "天府", "太阴", "贪狼", "巨门", "天相", "天梁", "七杀", "破军",
]
# 传统结论：身宫只落在命 / 夫 / 财 / 迁 / 官 / 福 六宫
SHEN_OK = {"命宫", "夫妻", "财帛", "迁移", "官禄", "福德"}

CASES = [
    (1991, 9, 10, 7, 35, "男", 113.26),
    (1988, 3, 12, 9, 0, "女", 116.41),
    (2000, 1, 1, 0, 10, "男", 120.0),
    (1975, 12, 31, 23, 30, "女", 121.47),
    (1962, 6, 6, 12, 0, "男", 91.14),
    (2003, 7, 20, 15, 45, "女", 103.83),
]


class ZiweiPalaceTest(unittest.TestCase):
    def test_ziwei_base_by_ju(self):
        """「六五四三二，酉午亥辰丑」：各局初一落宫。"""
        self.assertEqual(ziwei_palace(6, "酉", 1), 9)   # 火六局初一 -> 酉
        self.assertEqual(ziwei_palace(5, "午", 1), 6)   # 土五局初一 -> 午
        self.assertEqual(ziwei_palace(4, "亥", 1), 11)  # 金四局初一 -> 亥
        self.assertEqual(ziwei_palace(3, "辰", 1), 4)   # 木三局初一 -> 辰
        self.assertEqual(ziwei_palace(2, "丑", 1), 1)   # 水二局初一 -> 丑

    def test_ziwei_advances_every_ju_days(self):
        """每宫局数日：水二局初一初二同宫，初三进一宫；整除时落前一格。"""
        self.assertEqual(ziwei_palace(2, "丑", 2), 1)   # 初二仍在丑（整除）
        self.assertEqual(ziwei_palace(2, "丑", 3), 2)   # 初三进到寅
        self.assertEqual(ziwei_palace(2, "丑", 25), 1)  # 二十四天走完一圈，回到丑
        self.assertEqual(ziwei_palace(3, "辰", 4), 5)   # 木三局初四进一宫

    def test_wu_xing_ju_by_ming_pillar(self):
        """命宫干支的纳音 -> 局数（水二 / 木三 / 金四 / 土五 / 火六）。"""
        expected = {
            4: "金四局", 6: "火六局", 3: "木三局", 5: "土五局", 2: "水二局",
        }
        for gan_zhi, ju in (
            ("甲子", 4),  # 海中金
            ("丙寅", 6),  # 炉中火
            ("戊辰", 3),  # 大林木
            ("庚午", 5),  # 路旁土
            ("丙子", 2),  # 涧下水
        ):
            name, number, base = wu_xing_ju(gan_zhi[0], gan_zhi[1])
            self.assertEqual(number, ju, gan_zhi)
            self.assertEqual(name, expected[ju], gan_zhi)

    def test_ziwei_partner_matches_classic_table(self):
        """紫微在十二宫的同宫星：紫府寅申、紫贪卯酉、紫相辰戌、紫杀巳亥、
        紫破丑未、子午独坐。（外部口诀，用来反向校验两套星系的偏移表）"""
        branches = ["子", "丑", "寅", "卯", "辰", "巳",
                    "午", "未", "申", "酉", "戌", "亥"]
        expect = {
            "子": [], "丑": ["破军"], "寅": ["天府"], "卯": ["贪狼"],
            "辰": ["天相"], "巳": ["七杀"], "午": [], "未": ["破军"],
            "申": ["天府"], "酉": ["贪狼"], "戌": ["天相"], "亥": ["七杀"],
        }
        for idx, zhi in enumerate(branches):
            slots: dict[int, list[str]] = {}
            for star, off in ZIWEI_SERIES.items():
                slots.setdefault((idx + off) % 12, []).append(star)
            tianfu = (4 - idx) % 12
            for star, off in TIANFU_SERIES.items():
                slots.setdefault((tianfu + off) % 12, []).append(star)
            partners = [s for s in slots.get(idx, []) if s != "紫微"]
            self.assertEqual(partners, expect[zhi], f"紫微在{zhi}")

    def test_palace_oppositions_and_trinities(self):
        """六组对宫各差 6 宫；命 / 财帛 / 官禄三合，两两差 4 宫。"""
        branches = ["子", "丑", "寅", "卯", "辰", "巳",
                    "午", "未", "申", "酉", "戌", "亥"]
        chart = build_ziwei(1991, 9, 10, 7, 35, "男", 113.26)
        palaces = chart["palaces"]
        for i, j in ((0, 6), (1, 7), (2, 8), (3, 9), (4, 10), (5, 11)):
            diff = (
                branches.index(palaces[i]["zhi"])
                - branches.index(palaces[j]["zhi"])
            ) % 12
            self.assertEqual(
                diff, 6, f"{palaces[i]['name']} 与 {palaces[j]['name']} 应为对宫"
            )
        ming = branches.index(palaces[0]["zhi"])
        wealth = branches.index(palaces[4]["zhi"])
        career = branches.index(palaces[8]["zhi"])
        # 沿同一方向（命 -> 财帛 -> 官禄 -> 命）每步应走 4 宫
        self.assertEqual(
            {(ming - wealth) % 12, (wealth - career) % 12, (career - ming) % 12},
            {4},
            "命 / 财帛 / 官禄 应成三合",
        )

    def test_palace_gan_uses_wu_hu_dun(self):
        """五虎遁：甲己年寅宫起丙；乙庚年起戊。"""
        self.assertEqual(palace_gan("甲", 2), "丙")
        self.assertEqual(palace_gan("己", 2), "丙")
        self.assertEqual(palace_gan("乙", 2), "戊")
        self.assertEqual(palace_gan("庚", 2), "戊")


class ZiweiChartTest(unittest.TestCase):
    def test_fourteen_main_stars_placed_exactly_once(self):
        for case in CASES:
            chart = build_ziwei(*case)
            placed = {}
            for palace in chart["palaces"]:
                for star in palace["main"]:
                    placed[star] = palace["name"]
            self.assertEqual(len(placed), 14, case)
            self.assertEqual(set(placed), set(MAIN14), case)

    def test_tianfu_mirrors_ziwei_on_yin_shen_axis(self):
        """天府 = 4 - 紫微（子为 0），与紫微以寅—申轴对称。"""
        for case in CASES:
            chart = build_ziwei(*case)
            branches = ["子", "丑", "寅", "卯", "辰", "巳",
                        "午", "未", "申", "酉", "戌", "亥"]
            ziwei_zhi = chart["basic"]["ziwei_zhi"]
            tianfu_zhi = next(
                p["zhi"] for p in chart["palaces"] if "天府" in p["main"]
            )
            self.assertEqual(
                (branches.index(ziwei_zhi) + branches.index(tianfu_zhi)) % 12, 4, case
            )

    def test_shen_palace_lands_in_six_palaces(self):
        for case in CASES:
            chart = build_ziwei(*case)
            shen = [p["name"] for p in chart["palaces"] if p["is_shen"]]
            self.assertEqual(len(shen), 1, case)
            self.assertIn(shen[0], SHEN_OK, case)

    def test_da_xian_covers_continuous_ten_year_blocks(self):
        for case in CASES:
            chart = build_ziwei(*case)
            blocks = sorted(
                (p["da_xian"]["from"], p["da_xian"]["to"]) for p in chart["palaces"]
            )
            self.assertEqual(blocks[0][0], chart["basic"]["ju_number"], case)
            for i in range(11):
                self.assertEqual(blocks[i][1] + 1, blocks[i + 1][0], case)

    def test_san_fang_is_ming_wealth_career_and_opposite(self):
        chart = build_ziwei(1991, 9, 10, 7, 35, "男", 113.26)
        self.assertEqual(chart["san_fang"]["ming"]["name"], "命宫")
        self.assertEqual(chart["san_fang"]["wealth"]["name"], "财帛")
        self.assertEqual(chart["san_fang"]["career"]["name"], "官禄")
        self.assertEqual(chart["san_fang"]["opposite"]["name"], "迁移")

    def test_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            build_ziwei(1991, 2, 30, 8, 0)
        with self.assertRaises(ValueError):
            build_ziwei(1991, 9, 10, 24, 0)
        with self.assertRaises(ValueError):
            build_ziwei(1991, 9, 10, 8, 0, gender="未知")


class ZiweiReadingTest(unittest.TestCase):
    def test_reading_has_love_career_fortune(self):
        chart = build_ziwei(1991, 9, 10, 7, 35, "男", 113.26)
        reading = build_ziwei_reading(chart)

        self.assertTrue(reading["headline"])
        for key in ("love", "career", "fortune"):
            block = reading[key]
            self.assertEqual(block["palace"],
                             {"love": "夫妻", "career": "官禄", "fortune": "命宫"}[key])
            self.assertTrue(block["summary"], key)
            self.assertTrue(block["points"], key)

        self.assertEqual(reading["career"]["wealth"]["palace"], "财帛")
        self.assertTrue(reading["career"]["wealth"]["points"])
        self.assertIn("岁", reading["fortune"]["da_xian"]["range"])

    def test_empty_palace_borrows_opposite(self):
        """空宫（无主星）时借对宫解读，并明确标注 borrowed。"""
        chart = build_ziwei(2000, 1, 1, 0, 10, "男", 120.0)
        reading = build_ziwei_reading(chart)
        for key in ("love", "career", "fortune"):
            block = reading[key]
            palace = next(
                p for p in chart["palaces"] if p["name"] == block["palace"]
            )
            if not palace["main"]:
                self.assertTrue(block["borrowed"], key)
                self.assertIn("空宫", block["points"][0], key)
            else:
                self.assertFalse(block["borrowed"], key)
                self.assertTrue(block["stars"], key)

    def test_si_hua_notes_appear_when_present(self):
        chart = build_ziwei(1991, 9, 10, 7, 35, "男", 113.26)
        reading = build_ziwei_reading(chart)
        ming = next(p for p in chart["palaces"] if p["name"] == "命宫")
        if ming["si_hua"]:
            joined = " ".join(reading["fortune"]["points"])
            self.assertIn(ming["si_hua"][0]["star"], joined)


class ZiweiYearTest(unittest.TestCase):
    def setUp(self):
        self.chart = build_ziwei(1991, 9, 10, 7, 35, "男", 113.26)
        self.star_palace = {}
        for palace in self.chart["palaces"]:
            for star in palace["main"] + palace["aux"]:
                self.star_palace.setdefault(star, palace["name"])

    def test_gan_zhi_anchor(self):
        self.assertEqual(gan_zhi_of_year(1984), "甲子")
        self.assertEqual(gan_zhi_of_year(2024), "甲辰")
        self.assertEqual(gan_zhi_of_year(2026), "丙午")

    def test_tai_sui_and_po_palace(self):
        """太岁宫地支 = 流年地支；岁破宫在对宫，且大耗正落岁破宫。"""
        years = build_ziwei_years(self.chart, 1991, 2026, 10)
        self.assertEqual(len(years), 10)
        palaces = self.chart["palaces"]
        for item in years:
            gan_zhi = gan_zhi_of_year(item["year"])
            self.assertEqual(item["gan_zhi"], gan_zhi)
            self.assertEqual(item["tai_sui"]["zhi"], gan_zhi[1])

            names = [p["name"] for p in palaces]
            tai_idx = names.index(item["tai_sui"]["palace"])
            po_idx = names.index(item["po"]["palace"])
            self.assertEqual((tai_idx + 6) % 12, po_idx, item["year"])

            da_hao = [s for s in item["stars"] if s["star"] == "大耗"]
            self.assertEqual(da_hao[0]["palace"], item["po"]["palace"])

    def test_si_hua_comes_from_year_gan(self):
        """流年四化按流年天干起，落点是该星在本命盘所在的宫。"""
        for item in build_ziwei_years(self.chart, 1991, 2026, 5):
            gan = item["gan_zhi"][0]
            expect = {star: hua for hua, star in SI_HUA[gan].items()}
            self.assertTrue(item["si_hua"])
            for entry in item["si_hua"]:
                self.assertEqual(expect[entry["star"]], entry["hua"])
                self.assertEqual(self.star_palace[entry["star"]], entry["palace"])

    def test_year_rows_are_consistent(self):
        years = build_ziwei_years(self.chart, 1991, 2026, 10)
        for i, item in enumerate(years):
            self.assertEqual(item["year"], 2026 + i)
            self.assertEqual(item["age"], 2026 + i - 1991)
            self.assertIn(item["stance"], ("宜主动", "宜守成", "稳中求进"))
            self.assertTrue(item["focus"])
            self.assertTrue(item["points"])
            self.assertTrue(item["da_xian"]["palace"])

    def test_da_xian_advances_every_ten_years(self):
        """跨二十年的大限应从一段换到下一段。"""
        years = build_ziwei_years(self.chart, 1991, 2026, 20)
        palaces_first = years[0]["da_xian"]["from"]
        palaces_later = years[19]["da_xian"]["from"]
        self.assertGreater(palaces_later, palaces_first)


try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover
    TestClient = None  # type: ignore[assignment]

import main


@unittest.skipIf(TestClient is None, "需要 httpx：pip install httpx")
class ZiweiApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)

    def test_post_ziwei_returns_chart_and_reading(self):
        resp = self.client.post(
            "/api/v1/ziwei",
            json={
                "year": 1991, "month": 9, "day": 10, "hour": 7, "minute": 35,
                "gender": "男", "longitude": 113.26,
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["code"], 0)

        data = body["data"]
        self.assertEqual(len(data["palaces"]), 12)
        self.assertEqual(data["palaces"][0]["name"], "命宫")
        self.assertTrue(data["basic"]["ju"].endswith("局"))

        reading = data["reading"]
        for key in ("love", "career", "fortune"):
            self.assertTrue(reading[key]["summary"], key)
            self.assertTrue(reading[key]["points"], key)
        self.assertTrue(reading["career"]["wealth"]["points"])
        self.assertIn("岁", reading["fortune"]["da_xian"]["range"])

    def test_longitude_is_required(self):
        """经度决定真太阳时，缺了不能排盘。"""
        resp = self.client.post(
            "/api/v1/ziwei",
            json={"year": 1991, "month": 9, "day": 10, "hour": 7, "gender": "男"},
        )
        self.assertEqual(resp.status_code, 422, resp.text)

    def test_response_includes_ten_years(self):
        """响应默认带回自今年起 10 年的流年。"""
        resp = self.client.post(
            "/api/v1/ziwei",
            json={
                "year": 1991, "month": 9, "day": 10, "hour": 7,
                "gender": "男", "longitude": 113.26,
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        years = resp.json()["data"]["years"]
        self.assertEqual(len(years), 10)
        self.assertEqual(years[0]["year"], _dt.date.today().year)
        for item in years:
            self.assertEqual(len(item["gan_zhi"]), 2)
            self.assertTrue(item["points"])
            self.assertTrue(item["tai_sui"]["palace"])

    def test_bad_gender_is_rejected(self):
        resp = self.client.post(
            "/api/v1/ziwei",
            json={
                "year": 1991, "month": 9, "day": 10, "hour": 7,
                "gender": "未知", "longitude": 113.26,
            },
        )
        self.assertEqual(resp.status_code, 422, resp.text)


if __name__ == "__main__":
    unittest.main()
