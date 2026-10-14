# -*- coding: utf-8 -*-
"""八宅游年引擎单元测试。

这些断言是「大模型不可介入」的底线：算法一旦改动就会红。
命卦公式与游年八星都有传统通说可对照，用例直接写死结论，防止被改坏。

运行：python -m unittest tests.test_bazhai -v
"""

import unittest

from app.engine import (
    build_bazhai,
    lichun_year,
    ming_gua_number,
    ming_gua_of,
    you_nian_of,
    zhai_gua_of,
)
from app.engine.constants import MING_GUA_BY_LUOSHU

try:
    from lunar_python import Solar  # noqa: F401
except ImportError:  # pragma: no cover - 依赖缺失时跳过立春分界用例
    Solar = None


class TestMingGuaFormula(unittest.TestCase):
    """命卦公式：年份后两位推洛书数，余 5 男寄坤、女寄艮。"""

    def test_known_cases_before_2000(self):
        # 对照传统命卦表（1900-1999 段）
        cases = [
            (1984, "男", 7),   # 兑
            (1984, "女", 8),   # 艮
            (1990, "男", 1),   # 坎
            (1990, "女", 8),   # 艮
            (1999, "女", 8),   # 艮
            (1900, "男", 1),   # 坎
        ]
        for year, gender, expected in cases:
            with self.subTest(year=year, gender=gender):
                self.assertEqual(ming_gua_number(year, gender), expected)

    def test_known_cases_after_2000(self):
        cases = [
            (2000, "男", 9),   # 离
            (2000, "女", 6),   # 乾
            (2001, "男", 8),   # 艮
            (2001, "女", 7),   # 兑
            (2004, "女", 1),   # 坎
        ]
        for year, gender, expected in cases:
            with self.subTest(year=year, gender=gender):
                self.assertEqual(ming_gua_number(year, gender), expected)

    def test_five_is_hosted_by_kun_or_gen(self):
        """余 5 者中宫无卦：男寄坤(2)、女寄艮(8)。"""
        # 2004 年男命余数为 5
        self.assertEqual(ming_gua_number(2004, "男"), 2)
        self.assertEqual(ming_gua_number(2008, "女"), 8)
        for year in range(1900, 2101):
            for gender in ("男", "女"):
                num = ming_gua_number(year, gender)
                self.assertNotEqual(num, 5, f"{year} {gender} 不应落在中宫五黄")
                self.assertIn(num, MING_GUA_BY_LUOSHU)

    def test_decrements_year_by_year_1900s(self):
        """1900 段男命逐年递减 1（9 为回绕），余 5 寄坤——序列可人工核对。"""
        self.assertEqual(
            [ming_gua_number(y, "男") for y in range(1990, 2000)],
            [1, 9, 8, 7, 6, 2, 4, 3, 2, 1],
        )
        # 女命逐年递增 1，余 5 寄艮
        self.assertEqual(
            [ming_gua_number(y, "女") for y in range(2000, 2010)],
            [6, 7, 8, 9, 1, 2, 3, 4, 8, 6],
        )

    def test_rejects_bad_gender_and_year(self):
        with self.assertRaises(ValueError):
            ming_gua_number(1990, "女女")
        with self.assertRaises(ValueError):
            ming_gua_number(1899, "男")
        with self.assertRaises(ValueError):
            ming_gua_number(2101, "男")

    def test_ming_gua_group(self):
        self.assertEqual(ming_gua_of(1990, "男")["group"], "东四命")
        self.assertEqual(ming_gua_of(1984, "男")["group"], "西四命")
        self.assertEqual(ming_gua_of(2000, "女")["group"], "西四命")
        self.assertEqual(ming_gua_of(2000, "男")["label"], "离命 · 东四命")


@unittest.skipIf(Solar is None, "缺少 lunar-python，跳过立春分界用例")
class TestLichunBoundary(unittest.TestCase):
    """命卦以立春为界：立春前出生算上一年。"""

    def test_1990_before_and_after_lichun(self):
        # 1990 年立春交节于 02-04 10:14
        self.assertEqual(lichun_year(1990, 1, 20), (1989, True))
        self.assertEqual(lichun_year(1990, 2, 3), (1989, True))
        self.assertEqual(lichun_year(1990, 2, 4, 9, 0), (1989, True))
        self.assertEqual(lichun_year(1990, 2, 4, 16, 0), (1990, False))
        self.assertEqual(lichun_year(1990, 3, 1), (1990, False))
        self.assertEqual(lichun_year(1990, 12, 31), (1990, False))

    def test_january_birth_uses_previous_year(self):
        """1 月出生落在上一年的农历年内，命卦也必须按上一年定。"""
        ming = ming_gua_of(1990, "男", 1, 20)
        self.assertEqual(ming["solar_year"], 1989)
        self.assertTrue(ming["lichun_adjusted"])
        # 1989 年男命为坤，1990 年男命为坎——两者必须能区分开
        self.assertEqual(ming["trigram"], "坤")
        self.assertEqual(ming_gua_of(1990, "男", 3, 1)["trigram"], "坎")

    def test_without_month_day_no_adjust(self):
        self.assertEqual(lichun_year(1990), (1990, False))
        self.assertEqual(lichun_year(1990, 0, 0), (1990, False))


class TestYouNian(unittest.TestCase):
    """大游年歌诀：以宅卦为伏位飞布八星。结论直接对照传统通说。"""

    # 宅卦 -> {星: (宫, 方位)}，取自八宅游年通行表
    KNOWN = {
        "乾": {"生": ("兑", "正西"), "延": ("坤", "西南"), "天": ("艮", "东北"),
               "伏": ("乾", "西北"), "祸": ("巽", "东南"), "五": ("震", "正东"),
               "六": ("坎", "正北"), "绝": ("离", "正南")},
        "坎": {"生": ("巽", "东南"), "延": ("离", "正南"), "天": ("震", "正东"),
               "伏": ("坎", "正北"), "祸": ("兑", "正西"), "五": ("艮", "东北"),
               "六": ("乾", "西北"), "绝": ("坤", "西南")},
        "艮": {"生": ("坤", "西南"), "延": ("兑", "正西"), "天": ("乾", "西北"),
               "伏": ("艮", "东北"), "祸": ("离", "正南"), "五": ("坎", "正北"),
               "六": ("震", "正东"), "绝": ("巽", "东南")},
        "震": {"生": ("离", "正南"), "延": ("巽", "东南"), "天": ("坎", "正北"),
               "伏": ("震", "正东"), "祸": ("坤", "西南"), "五": ("乾", "西北"),
               "六": ("艮", "东北"), "绝": ("兑", "正西")},
        "巽": {"生": ("坎", "正北"), "延": ("震", "正东"), "天": ("离", "正南"),
               "伏": ("巽", "东南"), "祸": ("乾", "西北"), "五": ("坤", "西南"),
               "六": ("兑", "正西"), "绝": ("艮", "东北")},
        "离": {"生": ("震", "正东"), "延": ("坎", "正北"), "天": ("巽", "东南"),
               "伏": ("离", "正南"), "祸": ("艮", "东北"), "五": ("兑", "正西"),
               "六": ("坤", "西南"), "绝": ("乾", "西北")},
        "坤": {"生": ("艮", "东北"), "延": ("乾", "西北"), "天": ("兑", "正西"),
               "伏": ("坤", "西南"), "祸": ("震", "正东"), "五": ("巽", "东南"),
               "六": ("离", "正南"), "绝": ("坎", "正北")},
        "兑": {"生": ("乾", "西北"), "延": ("艮", "东北"), "天": ("坤", "西南"),
               "伏": ("兑", "正西"), "祸": ("坎", "正北"), "五": ("离", "正南"),
               "六": ("巽", "东南"), "绝": ("震", "正东")},
    }

    def test_all_gua_match_traditional_table(self):
        for zhai, expected in self.KNOWN.items():
            stars = {s["code"]: s for s in you_nian_of(zhai)}
            for code, (gua, direction) in expected.items():
                with self.subTest(zhai=zhai, star=code):
                    self.assertEqual(stars[code]["trigram"], gua)
                    self.assertEqual(stars[code]["direction"], direction)

    def test_eight_unique_palaces(self):
        """八卦各占一宫，不重不漏。"""
        for zhai in self.KNOWN:
            stars = you_nian_of(zhai)
            self.assertEqual(len(stars), 8)
            self.assertEqual(len({s["trigram"] for s in stars}), 8)
            self.assertEqual(len({s["code"] for s in stars}), 8)

    def test_base_palace_is_the_zhai_gua(self):
        for zhai in self.KNOWN:
            base = [s for s in you_nian_of(zhai) if s["is_base"]]
            self.assertEqual(len(base), 1)
            self.assertEqual(base[0]["code"], "伏")
            self.assertEqual(base[0]["star"], "伏位")
            self.assertEqual(base[0]["trigram"], zhai)

    def test_levels_follow_auspicious_split(self):
        """四吉星与四凶星的等级分档：吉者旺/平，凶者煞/大凶。"""
        for zhai in self.KNOWN:
            by_code = {s["code"]: s for s in you_nian_of(zhai)}
            for code in ("生", "天", "延"):
                self.assertEqual(by_code[code]["level"], "旺")
            self.assertEqual(by_code["伏"]["level"], "平")
            for code in ("祸", "六"):
                self.assertEqual(by_code[code]["level"], "煞")
            for code in ("五", "绝"):
                self.assertEqual(by_code[code]["level"], "大凶")

    def test_rejects_unknown_trigram(self):
        with self.assertRaises(ValueError):
            you_nian_of("太极")
        with self.assertRaises(ValueError):
            zhai_gua_of("中宫")


class TestBuildBazhai(unittest.TestCase):
    """主入口：命卦 + 宅卦 + 匹配 + 房间选位。"""

    def test_matched_when_same_gua(self):
        """1990 年男为坎命（东四），子山午向为坎宅（东四）-> 同宫。"""
        r = build_bazhai(1990, "男", 6, 15, degree=0.0)
        self.assertEqual(r["ming_gua"]["trigram"], "坎")
        self.assertEqual(r["zhai_gua"]["trigram"], "坎")
        self.assertEqual(r["zhai_gua"]["title"], "子山午向")
        self.assertEqual(r["compat"]["level"], "同宫")
        self.assertEqual(r["compat"]["score"], 100)
        self.assertTrue(r["compat"]["matched"])
        self.assertTrue(r["compat"]["same_gua"])

    def test_matched_but_different_gua_within_east_four(self):
        """震命（2000 年后某年）居坎宅：同属东四 -> 相配但非同一卦。"""
        # 坎宅：坐子（0 度）；找一位东四命但非坎命者
        ming = ming_gua_of(2000, "男")           # 离命（东四）
        self.assertEqual(ming["group"], "东四命")
        r = build_bazhai(2000, "男", 6, 15, degree=0.0)
        self.assertEqual(r["zhai_gua"]["trigram"], "坎")
        self.assertEqual(r["compat"]["level"], "相配")
        self.assertFalse(r["compat"]["same_gua"])
        self.assertEqual(r["compat"]["score"], 90)

    def test_mismatch_gives_advice(self):
        """1990 年男（坎命·东四）住乾宅（西四）-> 不配，须给调和路径。"""
        r = build_bazhai(1990, "男", 6, 15, degree=315.0)
        self.assertEqual(r["zhai_gua"]["trigram"], "乾")
        self.assertEqual(r["compat"]["level"], "不配")
        self.assertFalse(r["compat"]["matched"])
        self.assertGreaterEqual(len(r["compat"]["advice"]), 2)
        self.assertTrue(
            any("本命" in a for a in r["compat"]["advice"]),
            "不配时应给出「以人向吉方补宅」的调和建议",
        )

    def test_auspicious_and_inauspicious_are_four_each(self):
        r = build_bazhai(1990, "男", degree=0.0)
        self.assertEqual(len(r["auspicious"]), 4)
        self.assertEqual(len(r["inauspicious"]), 4)
        self.assertEqual(
            [s["code"] for s in r["auspicious"]], ["生", "天", "延", "伏"]
        )
        self.assertEqual(
            [s["code"] for s in r["inauspicious"]], ["绝", "五", "六", "祸"]
        )
        # 坎宅生气在东南、绝命在西南
        self.assertEqual(r["auspicious"][0]["direction"], "东南")
        self.assertEqual(r["inauspicious"][0]["direction"], "西南")

    def test_ming_directions_come_from_ming_gua(self):
        """本命吉方按命卦起游年，与宅卦无关。"""
        r = build_bazhai(1990, "男", degree=315.0)   # 坎命住乾宅
        self.assertEqual(
            [s["direction"] for s in r["ming_directions"]["lucky"]],
            ["东南", "正东", "正南", "正北"],
        )
        self.assertIn("东南", r["ming_directions"]["bed"])
        self.assertIn("西南", r["ming_directions"]["bed"])   # 忌朝绝命方

    def test_rooms_plan_covers_key_functions(self):
        r = build_bazhai(1990, "男", degree=0.0)
        keys = [p["key"] for p in r["rooms"]]
        for expected in ("door", "bedroom", "kitchen", "bath"):
            self.assertIn(expected, keys)
        door = next(p for p in r["rooms"] if p["key"] == "door")
        self.assertEqual(door["recommend"][0]["direction"], "东南")
        self.assertEqual(door["headline"], "东南 · 生气")
        bath = next(p for p in r["rooms"] if p["key"] == "bath")
        # 卫生间宜压凶方：坎宅的凶方为 正西(祸害)、西北(六煞)、东北(五鬼)、西南(绝命)
        self.assertIn(
            bath["recommend"][0]["direction"], ("正西", "西北", "东北", "西南")
        )

    def test_trigram_only_has_no_orientation_detail(self):
        r = build_bazhai(2000, "女", trigram="坤")
        self.assertEqual(r["zhai_gua"]["trigram"], "坤")
        self.assertEqual(r["zhai_gua"]["title"], "")
        self.assertEqual(r["zhai_gua"]["mountain"], "")
        self.assertIsNone(r["zhai_gua"]["degree"])
        # 2000 年女为乾命（西四），坤宅亦西四 -> 相配
        self.assertEqual(r["compat"]["level"], "相配")

    def test_requires_degree_or_trigram(self):
        with self.assertRaises(ValueError) as ctx:
            build_bazhai(1990, "男")
        self.assertIn("degree", str(ctx.exception))

    def test_rejects_bad_inputs(self):
        with self.assertRaises(ValueError):
            build_bazhai(1990, "未知", degree=0.0)
        with self.assertRaises(ValueError):
            build_bazhai(1990, "男", month=2, day=30, degree=0.0)
        with self.assertRaises(ValueError):
            build_bazhai(1990, "男", hour=24, degree=0.0)
        with self.assertRaises(ValueError):
            build_bazhai(1990, "男", trigram="太极")

    def test_key_points_are_actionable(self):
        r = build_bazhai(1990, "男", degree=0.0)
        self.assertGreaterEqual(len(r["key_points"]), 4)
        joined = "".join(r["key_points"])
        self.assertIn("生气", joined)
        self.assertIn("本命吉方", joined)

    def test_rules_version_is_exposed(self):
        r = build_bazhai(1990, "男", degree=0.0)
        self.assertTrue(r["rules_version"])


class TestBazhaiApi(unittest.TestCase):
    """接口层：参数校验与统一响应格式。"""

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        import main

        cls.client = TestClient(main.app)
        cls.url = "/api/v1/bazhai"

    def test_success_with_degree(self):
        res = self.client.post(
            self.url,
            json={"year": 1990, "gender": "男", "month": 6, "day": 15, "degree": 0.0},
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["code"], 0)
        self.assertEqual(body["status"], "ok")
        data = body["data"]
        self.assertEqual(data["ming_gua"]["trigram"], "坎")
        self.assertEqual(data["zhai_gua"]["title"], "子山午向")
        self.assertEqual(len(data["stars"]), 8)
        self.assertEqual(data["compat"]["level"], "同宫")

    def test_success_with_trigram(self):
        res = self.client.post(
            self.url, json={"year": 1990, "gender": "男", "trigram": "離"}
        )
        # 「離」是异体字，不在八卦表内 -> 应被拒
        self.assertEqual(res.status_code, 400)

        res = self.client.post(
            self.url, json={"year": 1990, "gender": "男", "trigram": "离"}
        )
        self.assertEqual(res.status_code, 200)

    def test_missing_orientation_returns_400(self):
        res = self.client.post(self.url, json={"year": 1990, "gender": "男"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("degree", res.json()["detail"])

    def test_invalid_trigram_returns_400(self):
        res = self.client.post(
            self.url, json={"year": 1990, "gender": "男", "trigram": "太极"}
        )
        self.assertEqual(res.status_code, 400)

    def test_invalid_payload_returns_422(self):
        for payload in (
            {"year": 1990, "gender": "X", "degree": 0},
            {"year": 1800, "gender": "男", "degree": 0},
            {"year": 1990, "gender": "男", "degree": 400},
            {"gender": "男", "degree": 0},           # 缺 year
            {"year": 1990, "degree": 0},             # 缺 gender
        ):
            with self.subTest(payload=payload):
                res = self.client.post(self.url, json=payload)
                self.assertEqual(res.status_code, 422)

    def test_is_public_without_token(self):
        """计算类接口不需要登录：与 /api/v1/bazi 口径一致。"""
        res = self.client.post(
            self.url, json={"year": 1990, "gender": "男", "degree": 0.0}
        )
        self.assertEqual(res.status_code, 200)


if __name__ == "__main__":
    unittest.main()
