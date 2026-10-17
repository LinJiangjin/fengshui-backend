# -*- coding: utf-8 -*-
"""玄空飞星进阶盘（月盘 + 宅运盘）引擎测试。

玄空是流派分歧较大的体系，所以这里的断言分四层，重心在「与主流资料对拍」：

1. **旺山旺向全表对拍**：三元九运 216 局里共有 48 局旺山旺向
   （二运 6、三运 6、四运 6、五运 12、六运 6、七运 6、八运 6，一运九运无）。
   这张表是玄空的硬标准，多个独立来源一致；能整表复现，说明下卦起星的
   入中与顺逆两处都没做错。
2. **八运 24 山四类分类对拍**：旺山旺向 / 双星会坐 / 双星会向 / 上山下水
   各 6 局，逐山核对。
3. **常量表自检**：二十四山阴阳 12:12、三元龙每龙 8 山、每卦三山恰各占一元，
   以及「同卦天元龙与人元龙同阴阳、地元龙相反」这条内部规律。
4. **月盘与元运**：元运换算、月白口诀、节气月分界（立春起正月）。

顺逆判据是本次最容易做错的一步，单列一组测试锁住：
判顺逆看的**不是坐山自身的阴阳**，而是「入中之数在元旦盘所对应之宫」里
**与坐山同一元龙**的那一山的阴阳。

运行：python -m unittest tests.test_xuankong -v
"""

import datetime as dt
import unittest

from app.engine import (
    center_star_of_month,
    double_star_of,
    dragon_mountain_of,
    dragon_of,
    forward_of,
    house_chart,
    jieqi_month_of,
    judge_pattern,
    month_chart,
    star_state,
    tianyuan_of_trigram,
    year_branch_of,
    yin_yang_of,
    yun_of_year,
)
from app.engine.compass import opposite_mountain
from app.engine.constants import (
    DOUBLE_STAR_CLASSIC,
    DRAGON_MOUNTAINS,
    EARTHLY_BRANCHES,
    MOUNTAIN_DRAGON,
    MOUNTAIN_YIN_YANG,
    MOUNTAINS,
    MONTH_WHITE_BASE,
    PATTERN_INFO,
    TRIGRAM_BY_MOUNTAIN,
    TRIGRAM_INFO,
    XUANKONG_SCORE,
    YUN_INFO,
)
from app.engine.xuankong import _fly

# ---------------------------------------------------------------- 权威对照表
# 四十八局旺山旺向（多个独立站点一致；章易真整理的版本最全）
WSWX_TABLE = {
    1: [],
    2: ["丑山未向", "乾山巽向", "巳山亥向", "未山丑向", "巽山乾向", "亥山巳向"],
    3: ["卯山酉向", "辰山戌向", "辛山乙向", "酉山卯向", "戌山辰向", "乙山辛向"],
    4: ["艮山坤向", "寅山申向", "甲山庚向", "坤山艮向", "申山寅向", "庚山甲向"],
    5: ["子山午向", "丑山未向", "卯山酉向", "午山子向", "未山丑向", "酉山卯向",
        "戌山辰向", "辛山乙向", "癸山丁向", "辰山戌向", "乙山辛向", "丁山癸向"],
    6: ["艮山坤向", "寅山申向", "甲山庚向", "坤山艮向", "申山寅向", "庚山甲向"],
    7: ["卯山酉向", "辰山戌向", "辛山乙向", "酉山卯向", "戌山辰向", "乙山辛向"],
    8: ["丑山未向", "乾山巽向", "巳山亥向", "未山丑向", "巽山乾向", "亥山巳向"],
    9: [],
}

# 八运 24 山的四类格局（两个独立来源一致）
YUN8_TABLE = {
    "旺山旺向": ["未山丑向", "丑山未向", "巽山乾向", "乾山巽向", "巳山亥向", "亥山巳向"],
    "双星会坐": ["壬山丙向", "甲山庚向", "午山子向", "丁山癸向", "酉山卯向", "辛山乙向"],
    "双星会向": ["癸山丁向", "子山午向", "卯山酉向", "乙山辛向", "丙山壬向", "庚山甲向"],
    "上山下水": ["辰山戌向", "戌山辰向", "申山寅向", "寅山申向", "坤山艮向", "艮山坤向"],
}


def _pattern_of(sit: str, yun: int) -> str:
    """按坐山与元运算格局（与 house_chart 同路径，但不走坐向解析）。"""
    face = opposite_mountain(sit)
    yun_stars = _fly(yun, True)
    sit_luoshu = TRIGRAM_INFO[TRIGRAM_BY_MOUNTAIN[sit]]["luoshu"]
    face_luoshu = TRIGRAM_INFO[TRIGRAM_BY_MOUNTAIN[face]]["luoshu"]
    shan_center = yun_stars[sit_luoshu]
    xiang_center = yun_stars[face_luoshu]
    shan = _fly(shan_center, forward_of(shan_center, dragon_of(sit), sit))
    xiang = _fly(xiang_center, forward_of(xiang_center, dragon_of(face), face))
    return judge_pattern(shan, xiang, sit_luoshu, face_luoshu, yun)["key"]


def _title_of(sit: str) -> str:
    return f"{sit}山{opposite_mountain(sit)}向"


# ================================================================ 1. 三元九运
class YunCase(unittest.TestCase):
    """元运换算：1864 年（甲子）为一运之始，每运 20 年。"""

    def test_known_yun(self):
        for year, want in ((1864, 1), (1884, 2), (1904, 3), (1924, 4),
                           (1944, 5), (1964, 6), (1984, 7), (2004, 8), (2024, 9)):
            with self.subTest(year=year):
                self.assertEqual(yun_of_year(year)["number"], want)

    def test_yun_spans_twenty_years(self):
        """每运恰 20 年，边界年归属正确。"""
        self.assertEqual(yun_of_year(2003)["number"], 7)   # 七运末年
        self.assertEqual(yun_of_year(2004)["number"], 8)   # 八运首年
        self.assertEqual(yun_of_year(2023)["number"], 8)   # 八运末年
        self.assertEqual(yun_of_year(2024)["number"], 9)   # 九运首年
        self.assertEqual(yun_of_year(2043)["number"], 9)
        self.assertEqual(yun_of_year(2044)["number"], 1)   # 三轮循环回一运

    def test_yun_payload(self):
        y = yun_of_year(2026)
        self.assertEqual(y["name"], "九运")
        self.assertEqual(y["yuan"], "下元")
        self.assertEqual(y["star"], 9)
        self.assertEqual(y["star_name"], "九紫")
        self.assertEqual((y["start_year"], y["end_year"]), (2024, 2043))
        self.assertTrue(y["summary"])

    def test_before_start_year_raises(self):
        with self.assertRaises(ValueError):
            yun_of_year(1800)

    def test_each_yun_covers_exactly_one_yuan_block(self):
        """上元 1-3、中元 4-6、下元 7-9。"""
        for n in range(1, 10):
            want = "上元" if n <= 3 else ("中元" if n <= 6 else "下元")
            self.assertEqual(YUN_INFO[n]["yuan"], want)


# ================================================================ 2. 三元龙与阴阳
class DragonCase(unittest.TestCase):
    """二十四山的三元龙与阴阳，以及两者之间的内部规律。"""

    def test_every_mountain_classified(self):
        self.assertEqual(len(MOUNTAIN_DRAGON), 24)
        self.assertEqual(set(MOUNTAIN_DRAGON), set(MOUNTAINS))
        for dragon, members in DRAGON_MOUNTAINS.items():
            self.assertEqual(len(members), 8, f"{dragon}龙应恰有 8 山")

    def test_each_trigram_holds_one_of_each_dragon(self):
        """每卦三山恰好各占一元——这是 dragon_mountain_of 唯一性的前提。"""
        for trigram in TRIGRAM_INFO:
            dragons = sorted(
                MOUNTAIN_DRAGON[m] for m in MOUNTAINS
                if TRIGRAM_BY_MOUNTAIN[m] == trigram
            )
            self.assertEqual(dragons, ["人元", "地元", "天元"], trigram)

    def test_yin_yang_twelve_each(self):
        counts = {}
        for m in MOUNTAINS:
            counts[yin_yang_of(m)] = counts.get(yin_yang_of(m), 0) + 1
        self.assertEqual(counts, {"阴": 12, "阳": 12})

    def test_yin_yang_follows_mnemonic(self):
        """口诀：子午卯酉、辰戌丑未、乙辛丁癸属阴；其余十二山属阳。"""
        yin = set("子午卯酉辰戌丑未乙辛丁癸")
        for m in MOUNTAINS:
            want = "阴" if m in yin else "阳"
            self.assertEqual(MOUNTAIN_YIN_YANG[m], want, m)

    def test_same_trigram_dragon_relation(self):
        """同卦三山中：天元龙与人元龙同阴阳，地元龙相反。"""
        for trigram in TRIGRAM_INFO:
            tian = dragon_mountain_of(trigram, "天元")
            di = dragon_mountain_of(trigram, "地元")
            ren = dragon_mountain_of(trigram, "人元")
            self.assertEqual(
                yin_yang_of(tian), yin_yang_of(ren),
                f"{trigram}卦天元/人元阴阳应相同",
            )
            self.assertNotEqual(
                yin_yang_of(tian), yin_yang_of(di),
                f"{trigram}卦地元阴阳应与之相反",
            )

    def test_tianyuan_is_the_middle_mountain(self):
        """天元龙恒居每卦正中，只知卦时用它作正针默认解。"""
        cases = {"坎": "子", "坤": "坤", "震": "卯", "巽": "巽",
                 "乾": "乾", "兑": "酉", "艮": "艮", "离": "午"}
        for trigram, want in cases.items():
            self.assertEqual(tianyuan_of_trigram(trigram), want)

    def test_unknown_mountain_raises(self):
        for bad in ("X", "", "子午"):
            with self.assertRaises(ValueError):
                dragon_of(bad)
            with self.assertRaises(ValueError):
                yin_yang_of(bad)


# ================================================================ 3. 顺逆判据
class ForwardCase(unittest.TestCase):
    """顺逆判据——本次最容易做错的一步，逐案锁死。"""

    def test_uses_same_dragon_mountain_not_the_sit_mountain(self):
        """八运子山午向：山星入中 4 -> 元旦盘巽宫 -> 子为天元故取巽（阳）-> 顺飞。

        若误用坐山自身的阴阳（子属阴）会得到逆飞，整张盘全错。
        """
        self.assertTrue(forward_of(4, dragon_of("子"), "子"))

    def test_uses_same_dragon_mountain_reverse_case(self):
        """八运午山子向：山星入中 3 -> 震宫 -> 午为天元故取卯（阴）-> 逆飞。"""
        self.assertFalse(forward_of(3, dragon_of("午"), "午"))

    def test_di_yuan_differs_from_tian_yuan(self):
        """地元龙取的是该宫地元之山，与天元龙结论可能相反。"""
        # 4 属巽宫：天元为巽（阳）、地元为辰（阴）
        self.assertTrue(forward_of(4, "天元", "子"))
        self.assertFalse(forward_of(4, "地元", "壬"))
        # 3 属震宫：天元为卯（阴）、地元为甲（阳）
        self.assertFalse(forward_of(3, "天元", "午"))
        self.assertTrue(forward_of(3, "地元", "丙"))

    def test_center_five_falls_back_to_own_yin_yang(self):
        """入中为 5 时中宫无卦，改取本山自身的阴阳。

        另有一派主张五黄前十年寄坤、后十年寄艮，本模块不采；这里锁住
        所选口径，避免日后被无声改掉。
        """
        self.assertTrue(forward_of(5, "地元", "壬"))    # 壬属阳
        self.assertFalse(forward_of(5, "天元", "子"))   # 子属阴
        self.assertFalse(forward_of(5, "人元", "癸"))   # 癸属阴
        self.assertTrue(forward_of(5, "地元", "丙"))    # 丙属阳

    def test_older_wrong_rule_would_break_the_table(self):
        """反证：若按「坐山阴阳」定顺逆，子山午向会变成旺山旺向（八运实为双星会向）。"""
        yun = 8
        yun_stars = _fly(yun, True)
        sit_luoshu = TRIGRAM_INFO["坎"]["luoshu"]
        face_luoshu = TRIGRAM_INFO["离"]["luoshu"]
        shan_center = yun_stars[sit_luoshu]
        xiang_center = yun_stars[face_luoshu]
        wrong = _fly(shan_center, MOUNTAIN_YIN_YANG["子"] == "阳")
        right = _fly(shan_center, forward_of(shan_center, dragon_of("子"), "子"))
        self.assertNotEqual(wrong, right, "错误规则应与正确规则给出不同的山盘")
        self.assertEqual(_pattern_of("子", 8), "双星会向")


# ================================================================ 4. 飞布
class FlyCase(unittest.TestCase):
    def test_forward_sequence(self):
        got = _fly(1, True)
        self.assertEqual(got[5], 1)   # 中宫
        self.assertEqual(got[6], 2)   # 乾
        self.assertEqual(got[4], 9)   # 巽
        # 一白入中顺飞，坎宫得六白——通书的标准结论
        self.assertEqual(got[1], 6)

    def test_backward_is_the_mirror(self):
        got = _fly(1, False)
        self.assertEqual(got[5], 1)
        self.assertEqual(got[6], 9)
        self.assertEqual(got[1], 5)

    def test_every_palace_gets_one_star(self):
        for center in range(1, 10):
            for forward in (True, False):
                stars = _fly(center, forward)
                self.assertEqual(len(stars), 9)
                self.assertEqual(sorted(stars.values()), list(range(1, 10)))

    def test_center_palace_always_holds_the_center_star(self):
        for center in range(1, 10):
            self.assertEqual(_fly(center, True)[5], center)
            self.assertEqual(_fly(center, False)[5], center)


# ================================================================ 5. 格局判定
class PatternCase(unittest.TestCase):
    def test_judge_pattern_branches(self):
        yun = 8
        # 山逆则到山、向逆则到向
        sit, face = 3, 6
        shan_hit = {5: 1, 6: 2, 7: 3, 8: 4, 9: 5, 1: 6, 2: 7, 3: 8, 4: 9}
        shan_miss = {i: (yun if i == sit else 1) for i in range(1, 10)}
        xiang_hit = {i: (yun if i in (sit, face) else 1) for i in range(1, 10)}
        self.assertEqual(shan_hit[sit], yun)
        # 两旺星齐到坐山
        p = judge_pattern({**shan_miss, sit: yun}, {**{k: 1 for k in range(1, 10)},
                                                    sit: yun}, sit, face, yun)
        self.assertEqual(p["key"], "双星会坐")
        self.assertEqual(p["level"], PATTERN_INFO["双星会坐"]["level"])
        self.assertTrue(p["advice"])

    def test_pattern_info_covers_all_keys(self):
        from app.engine.constants import PATTERN_RULES
        self.assertEqual(set(PATTERN_RULES), set(PATTERN_INFO))
        for key, info in PATTERN_INFO.items():
            self.assertIn(info["level"], ("旺", "平", "煞", "大凶"), key)
            self.assertTrue(info["summary"] and info["advice"], key)

    def test_score_weights_cover_all_patterns(self):
        for key in PATTERN_INFO:
            self.assertIn(key, XUANKONG_SCORE["pattern"], key)


# ================================================================ 6. 全表对拍
class StandardTableCase(unittest.TestCase):
    """与主流资料整表对拍——玄空流派分歧大，这是最强的回归锚点。"""

    def test_forty_eight_ju_wang_shan_wang_xiang(self):
        """三元九运 216 局共 48 局旺山旺向，逐运逐山核对。"""
        total = 0
        for yun in range(1, 10):
            got = sorted(_title_of(m) for m in MOUNTAINS
                         if _pattern_of(m, yun) == "旺山旺向")
            want = sorted(WSWX_TABLE[yun])
            with self.subTest(yun=yun):
                self.assertEqual(got, want, f"{yun}运旺山旺向不符")
            total += len(got)
        self.assertEqual(total, 48, "四十八局总数应为 48")

    def test_yun_one_and_nine_have_no_wang_shan_wang_xiang(self):
        """一运与九运无旺山旺向（另有「全局合十」补救）。"""
        for yun in (1, 9):
            with self.subTest(yun=yun):
                self.assertEqual(WSWX_TABLE[yun], [])
                self.assertEqual(
                    [m for m in MOUNTAINS if _pattern_of(m, yun) == "旺山旺向"], []
                )

    def test_yun_eight_twenty_four_mountains(self):
        """八运 24 山：四类格局各 6 局，无一遗漏、无一重复。"""
        got = {}
        for m in MOUNTAINS:
            got.setdefault(_pattern_of(m, 8), []).append(_title_of(m))
        for key, want in YUN8_TABLE.items():
            with self.subTest(pattern=key):
                self.assertEqual(sorted(got.get(key, [])), sorted(want))
        self.assertEqual(sum(len(v) for v in got.values()), 24)

    def test_yun_nine_is_all_double_star(self):
        """九运（2024-2043，当下）24 山全为双星会向 / 双星会坐，各 12 局。"""
        got = {}
        for m in MOUNTAINS:
            got.setdefault(_pattern_of(m, 9), []).append(_title_of(m))
        self.assertNotIn("旺山旺向", got)
        self.assertEqual(len(got.get("双星会向", [])), 12)
        self.assertEqual(len(got.get("双星会坐", [])), 12)

    def test_pattern_covers_all_mountains_every_yun(self):
        """任一运下 24 山都被分到某一类，不会有「未判定」。"""
        for yun in range(1, 10):
            keys = {_pattern_of(m, yun) for m in MOUNTAINS}
            with self.subTest(yun=yun):
                self.assertTrue(keys <= set(PATTERN_INFO), keys)


# ================================================================ 7. 星曜旺衰
class StarStateCase(unittest.TestCase):
    def test_states_relative_to_yun(self):
        cur = star_state(8, 8)
        self.assertEqual(cur["state"], "旺")
        self.assertTrue(cur["is_wang"])
        self.assertEqual(star_state(9, 8)["state"], "生")   # 未来之运
        self.assertEqual(star_state(7, 8)["state"], "退")   # 刚过之运
        self.assertEqual(star_state(6, 8)["state"], "死")
        self.assertEqual(star_state(1, 8)["state"], "煞")

    def test_delta_wraps_around(self):
        """九运子山午向盘里，一白是生气星（本轮已过）。"""
        self.assertEqual(star_state(1, 9)["state"], "生")
        self.assertEqual(star_state(9, 9)["state"], "旺")
        self.assertEqual(star_state(8, 9)["state"], "退")
        self.assertEqual(star_state(7, 9)["state"], "死")

    def test_wuhuang_is_doomed_unless_it_is_the_current_yun(self):
        """五黄是唯一例外：不当运时不论偏移皆主灾。"""
        lost = star_state(5, 9)
        self.assertEqual(lost["level"], "大凶")
        self.assertFalse(lost["is_wang"])
        # 五运当元时五黄为旺星
        ruled = star_state(5, 5)
        self.assertTrue(ruled["is_wang"])
        self.assertEqual(ruled["level"], "旺")

    def test_level_in_four_tier_domain(self):
        """level 复用前端的四档配色值域，不另起一套。"""
        for star in range(1, 10):
            for yun in range(1, 10):
                self.assertIn(star_state(star, yun)["level"],
                              ("旺", "平", "煞", "大凶"))


# ================================================================ 8. 宅运盘
class HouseChartCase(unittest.TestCase):
    def test_degree_path_returns_orientation(self):
        """给度数时要一并返回坐向明细，并按度数定坐山。"""
        chart = house_chart(degree=0.0, yun=9)
        self.assertEqual(chart["sit"]["mountain"], "子")
        self.assertEqual(chart["face"]["mountain"], "午")
        self.assertEqual(chart["title"], "子山午向 · 九运宅运盘")
        self.assertEqual(chart["orientation"]["title"], "子山午向")

    def test_trigram_path_falls_back_to_tian_yuan(self):
        chart = house_chart(trigram="坎", yun=9)
        self.assertEqual(chart["sit"]["mountain"], "子")
        self.assertEqual(chart["orientation"], {})

    def test_build_year_drives_yun(self):
        self.assertEqual(house_chart(degree=0.0, build_year=2010)["yun"]["number"], 8)
        self.assertEqual(house_chart(degree=0.0, build_year=2010)["yun"]["source"], "build_year")
        self.assertEqual(house_chart(degree=0.0, build_year=2026)["yun"]["number"], 9)

    def test_explicit_yun_wins_over_build_year(self):
        chart = house_chart(degree=0.0, yun=7, build_year=2026)
        self.assertEqual(chart["yun"]["number"], 7)
        self.assertEqual(chart["yun"]["source"], "explicit")

    def test_three_plates_are_permutations(self):
        """三盘各自都是 1-9 的一次排列，且运盘必为当运星入中。"""
        chart = house_chart(degree=137.0, yun=9)
        for key in ("shan_star", "yun_star", "xiang_star"):
            got = sorted(p[key] for p in chart["palaces"])
            self.assertEqual(got, list(range(1, 10)), key)
        center = [p for p in chart["palaces"] if p["is_center"]][0]
        self.assertEqual(center["yun_star"], 9)

    def test_center_plates_land_where_expected(self):
        """山星落坐山宫、向星落向首宫（或据格局落到对宫）。"""
        chart = house_chart(degree=0.0, yun=9)
        sit = [p for p in chart["palaces"] if p["is_sit"]][0]
        face = [p for p in chart["palaces"] if p["is_face"]][0]
        self.assertEqual(sit["direction"], "正北")
        self.assertEqual(face["direction"], "正南")
        # 九运子山午向：九紫双星齐到坐山宫
        self.assertEqual(sit["shan_star"], 9)
        self.assertEqual(sit["xiang_star"], 9)
        self.assertTrue(chart["pattern"]["shan_at_sit"])
        self.assertTrue(chart["pattern"]["xiang_at_sit"])
        self.assertEqual(chart["pattern"]["key"], "双星会坐")

    def test_wang_shan_wang_xiang_details(self):
        """八运丑山未向：八白分到艮（坐山）与坤（向首）——通书的经典盘。"""
        chart = house_chart(degree=30.0, yun=8)
        self.assertEqual(chart["title"], "丑山未向 · 八运宅运盘")
        self.assertEqual(chart["pattern"]["key"], "旺山旺向")
        sit = [p for p in chart["palaces"] if p["is_sit"]][0]
        face = [p for p in chart["palaces"] if p["is_face"]][0]
        self.assertEqual(sit["shan_star"], 8)
        self.assertEqual(face["xiang_star"], 8)
        self.assertGreaterEqual(chart["score"], 80)
        self.assertEqual(chart["level_key"], "旺")

    def test_shang_shan_xia_shui_scores_low(self):
        """八运辰山戌向是上山下水，分数应明显低于旺山旺向。"""
        bad = house_chart(degree=120.0, yun=8)
        good = house_chart(degree=30.0, yun=8)
        self.assertEqual(bad["pattern"]["key"], "上山下水")
        self.assertEqual(bad["level_key"], "大凶")
        self.assertLess(bad["score"], good["score"])
        self.assertLess(bad["score"], 40)

    def test_yun_nine_has_no_wang_shan_wang_xiang(self):
        """九运任何坐向都不应判为旺山旺向。"""
        for m in MOUNTAINS:
            chart = house_chart(degree=MOUNTAINS.index(m) * 15.0, yun=9)
            with self.subTest(mountain=m):
                self.assertNotEqual(chart["pattern"]["key"], "旺山旺向")

    def test_palaces_have_unique_levels_and_roles(self):
        chart = house_chart(degree=45.0, yun=9)
        self.assertEqual(len(chart["palaces"]), 9)
        for p in chart["palaces"]:
            self.assertIn(p["level"], ("旺", "平", "煞", "大凶"))
            self.assertTrue(p["role"])
        self.assertEqual([p for p in chart["palaces"] if p["is_center"]][0]["level"], "平")

    def test_center_palace_never_wuhuang_fatal(self):
        """中宫不以外围吉凶论，即便五黄入中也不打大凶。"""
        for m in MOUNTAINS:
            chart = house_chart(degree=MOUNTAINS.index(m) * 15.0, yun=9)
            center = [p for p in chart["palaces"] if p["is_center"]][0]
            with self.subTest(mountain=m):
                self.assertEqual(center["level"], "平")

    def test_jianxiang_flag(self):
        """偏离该山中心 4.5 度以上标兼向；正针不标。"""
        self.assertFalse(house_chart(degree=0.0, yun=9)["jianxiang"])
        self.assertTrue(house_chart(degree=6.0, yun=9)["jianxiang"])

    def test_score_within_range_and_explainable(self):
        for m in MOUNTAINS:
            chart = house_chart(degree=MOUNTAINS.index(m) * 15.0, yun=9)
            with self.subTest(mountain=m):
                self.assertGreaterEqual(chart["score"], 0)
                self.assertLessEqual(chart["score"], 100)
                self.assertTrue(chart["key_points"])
                self.assertTrue(chart["center"]["shan_basis"])
                self.assertTrue(chart["center"]["xiang_basis"])

    def test_missing_inputs_raise(self):
        with self.assertRaises(ValueError):
            house_chart(yun=9)                       # 无坐向
        with self.assertRaises(ValueError):
            house_chart(degree=0.0)                  # 无元运
        with self.assertRaises(ValueError):
            house_chart(degree=0.0, yun=0)
        with self.assertRaises(ValueError):
            house_chart(degree=0.0, yun=10)
        with self.assertRaises(ValueError):
            house_chart(trigram="X", yun=9)

    def test_roles_explain_the_three_plates(self):
        roles = house_chart(degree=0.0, yun=9)["roles"]
        self.assertEqual(set(roles), {"shan", "xiang", "yun"})
        self.assertIn("人丁", roles["shan"]["duty"])
        self.assertIn("财", roles["xiang"]["duty"])


# ================================================================ 9. 月盘
class MonthCase(unittest.TestCase):
    def test_year_branch_uses_lichun(self):
        """年支以立春为界：2026-02-03 仍是乙巳年，02-06 才是丙午年。"""
        self.assertEqual(year_branch_of(dt.date(2026, 2, 3)), "巳")
        self.assertEqual(year_branch_of(dt.date(2026, 2, 6)), "午")
        self.assertEqual(year_branch_of(dt.date(2026, 10, 15)), "午")

    def test_jieqi_month_boundary(self):
        """节气月以「节」为界：小寒起十二月、立春起正月。"""
        self.assertEqual(jieqi_month_of(dt.date(2026, 1, 3)), (11, "十一月", "大雪"))
        self.assertEqual(jieqi_month_of(dt.date(2026, 1, 6)), (12, "十二月", "小寒"))
        self.assertEqual(jieqi_month_of(dt.date(2026, 2, 3)), (12, "十二月", "小寒"))
        self.assertEqual(jieqi_month_of(dt.date(2026, 2, 6)), (1, "正月", "立春"))
        self.assertEqual(jieqi_month_of(dt.date(2026, 10, 15)), (9, "九月", "寒露"))

    def test_month_white_base_mnemonic(self):
        """子午卯酉年八白起正月，辰戌丑未年五黄，寅申巳亥年二黑。"""
        for branch in "子午卯酉":
            self.assertEqual(center_star_of_month(branch, 1), 8, branch)
        for branch in "辰戌丑未":
            self.assertEqual(center_star_of_month(branch, 1), 5, branch)
        for branch in "寅申巳亥":
            self.assertEqual(center_star_of_month(branch, 1), 2, branch)

    def test_month_white_moves_backward(self):
        """正月起星定后逐月逆退一位，十二月一轮刚好走完九星。"""
        seq = [center_star_of_month("午", i) for i in range(1, 13)]
        self.assertEqual(seq[0], 8)
        self.assertEqual(seq[1], 7)
        self.assertEqual(seq[8], 9)   # 8 - 8 = 0 -> 9
        for a, b in zip(seq, seq[1:]):
            self.assertEqual((a - 1 - 1) % 9 + 1, b)

    def test_month_white_base_covers_twelve_branches(self):
        self.assertEqual(set(MONTH_WHITE_BASE), set(EARTHLY_BRANCHES))

    def test_month_white_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            center_star_of_month("X", 1)
        with self.assertRaises(ValueError):
            center_star_of_month("子", 0)
        with self.assertRaises(ValueError):
            center_star_of_month("子", 13)

    def test_month_chart_shape(self):
        chart = month_chart(dt.date(2026, 10, 15))
        self.assertEqual(chart["month_name"], "九月")
        self.assertEqual(chart["jieqi"], "寒露")
        self.assertEqual(chart["branch"], "午")
        self.assertEqual(chart["center_star"], 9)          # 午年正月 8 -> 九月 9
        self.assertEqual(len(chart["palaces"]), 9)
        stars = sorted(p["star"] for p in chart["palaces"])
        self.assertEqual(stars, list(range(1, 10)))
        self.assertTrue(chart["key_points"])

    def test_month_chart_stacks_year_star(self):
        """每宫带上同宫流年星，二者相同则标记叠临。"""
        chart = month_chart(dt.date(2026, 10, 15))
        for p in chart["palaces"]:
            self.assertTrue(1 <= p["year_star"] <= 9)
            self.assertEqual(p["stacked"], p["star"] == p["year_star"])
        # 2026 丙午年流年紫白一白入中（2024 三碧、2025 二黑、2026 一白），
        # 与本月九紫入中不同，故中宫不叠临
        self.assertEqual(chart["year_center_star"], 1)
        center = [p for p in chart["palaces"] if p["is_center"]][0]
        self.assertEqual(center["star"], chart["center_star"])
        self.assertEqual(center["year_star"], 1)
        self.assertFalse(center["stacked"])

    def test_stacked_only_when_centers_match(self):
        """两盘都是顺飞，故只有入中之数相同时才会同星同宫——那时九宫全叠。"""
        for d in (dt.date(2026, 2, 6), dt.date(2026, 3, 15),
                  dt.date(2026, 7, 1), dt.date(2026, 12, 31)):
            chart = month_chart(d)
            stacked = [p for p in chart["palaces"] if p["stacked"]]
            same = chart["center_star"] == chart["year_center_star"]
            with self.subTest(date=d.isoformat()):
                self.assertEqual(bool(stacked), same)
                if same:
                    self.assertEqual(len(stacked), 9)

    def test_stack_advice_treats_wuhuang_as_hard_constraint(self):
        """同宫有五黄就不论配什么星都得避——这是五黄的硬约束。"""
        from app.engine import stack_advice
        self.assertEqual(stack_advice(5, 8)["level"], "煞")
        self.assertIn("五黄", stack_advice(5, 8)["key"])
        self.assertEqual(stack_advice(5, 5)["level"], "大凶")
        self.assertEqual(stack_advice(8, 9)["level"], "旺")     # 两旺星叠吉
        self.assertEqual(stack_advice(7, 2)["level"], "煞")     # 两煞星叠凶
        self.assertEqual(stack_advice(3, 2)["level"], "平")     # 一平一煞，参半

    def test_every_palace_carries_stack_advice(self):
        chart = month_chart(dt.date(2026, 6, 10))
        for p in chart["palaces"]:
            self.assertIn(p["stack"]["level"], ("旺", "平", "煞", "大凶"))
            self.assertTrue(p["stack"]["note"])

    def test_best_and_worst_present(self):
        chart = month_chart(dt.date(2026, 5, 20))
        self.assertTrue(chart["best"]["direction"])
        self.assertTrue(chart["worst"]["direction"])
        self.assertNotEqual(chart["best"]["direction"], chart["worst"]["direction"])

    def test_leap_and_month_end_dates_do_not_crash(self):
        for d in (dt.date(2026, 2, 28), dt.date(2024, 2, 29), dt.date(2026, 12, 31)):
            with self.subTest(date=d.isoformat()):
                self.assertEqual(len(month_chart(d)["palaces"]), 9)


# ================================================================ 10. 缓存
class CacheCase(unittest.TestCase):
    def test_lunar_year_cache_installed(self):
        from app.engine import xuankong
        self.assertTrue(xuankong.patched())

    def test_bulk_yun9_sweep_stays_fast(self):
        """24 山整轮扫一遍（含节气表的多次取用）应远快于无缓存时。"""
        import time
        start = time.perf_counter()
        for m in MOUNTAINS:
            house_chart(degree=MOUNTAINS.index(m) * 15.0, yun=9)
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 2.0, f"24 山耗时 {elapsed:.2f}s，缓存可能失效")


class DoubleStarCase(unittest.TestCase):
    """双星组合判词。

    锁的是**分层策略**与可读性不变量，不是字面文案：
    有赋文的走经典层、没赋文的只能标五行生克、含五黄的必须点名五黄。
    """

    FOUR = {"旺", "平", "煞", "大凶"}
    PAIRS = [(a, b) for a in range(1, 10) for b in range(a, 10)]

    def _pair(self, shan, xiang, yun=9, is_center=False):
        return double_star_of(
            shan, xiang, star_state(shan, yun), star_state(xiang, yun), is_center
        )

    def test_all_fortyfive_pairs_produce_verdict(self):
        self.assertEqual(len(self.PAIRS), 45)
        for a, b in self.PAIRS:
            p = self._pair(a, b)
            for key in ("name", "nature", "verdict", "advice", "source"):
                self.assertTrue(p[key], f"{a}{b} 的 {key} 为空")
            self.assertIn(p["level"], self.FOUR, f"{a}{b}")

    def test_order_does_not_matter(self):
        """赋文讲的是「同宫」，组合名与档位必须与山向顺序无关。

        注意 ``wuxing`` 是**有意**保留方向性的（以山星为「我」判我克 / 克我），
        所以这里不断言它对称。
        """
        for a, b in self.PAIRS:
            self.assertEqual(self._pair(a, b)["name"], self._pair(b, a)["name"])
            self.assertEqual(self._pair(a, b)["level"], self._pair(b, a)["level"])
            self.assertEqual(self._pair(a, b)["source"], self._pair(b, a)["source"])

    def test_classic_pairs_are_sourced(self):
        """有赋文的组合必须标出出处，不能混在推导层里。"""
        for (a, b) in DOUBLE_STAR_CLASSIC:
            p = self._pair(a, b)
            self.assertEqual((a, b), tuple(sorted(p["key"] and (a, b))))
            self.assertNotEqual(p["source"], "五行生克", f"{a}{b} 应有赋文出处")
            self.assertTrue(p["source"])

    def test_derived_pairs_claim_no_classic_source(self):
        """没赋文的组合一律标五行生克——不能把推导结果包装成古诀。"""
        derived = [pr for pr in self.PAIRS if pr not in DOUBLE_STAR_CLASSIC]
        self.assertTrue(derived)
        for a, b in derived:
            self.assertEqual(self._pair(a, b)["source"], "五行生克", f"{a}{b}")

    def test_wuhuang_pairs_are_demoted_and_named(self):
        """组合里有五黄：档位至少「煞」，且必须点名五黄是正煞。"""
        for a, b in self.PAIRS:
            if 5 not in (a, b):
                continue
            p = self._pair(a, b)
            order = ["旺", "平", "煞", "大凶"]
            self.assertGreaterEqual(
                order.index(p["level"]), order.index("煞"), f"{a}{b}"
            )
            # 二五交加 / 五黄重叠本身已经说透，其余组合也必须补一句
            self.assertIn("五黄", p["nature"], f"{a}{b}")

    def test_non_wuhuang_pairs_never_mention_wuhuang(self):
        for a, b in self.PAIRS:
            if 5 in (a, b):
                continue
            self.assertNotIn("五黄", self._pair(a, b)["nature"], f"{a}{b}")

    def test_the_two_deadliest_pairs_are_always_daxiong(self):
        """二五交加与五黄重叠：不看当令与否都按大凶论。"""
        for pair in ((2, 5), (5, 5)):
            for yun in range(1, 10):
                p = self._pair(pair[0], pair[1], yun=yun)
                self.assertEqual(p["level"], "大凶", f"{pair} 在 {yun} 运")

    def test_center_palace_stays_flat(self):
        """中宫恒判「平」，与 _palace_level 同口径。"""
        for a, b in self.PAIRS:
            self.assertEqual(self._pair(a, b, is_center=True)["level"], "平")

    def test_timing_switches_verdict(self):
        """当令与失令必须给出不同的断语，否则等于没算。"""
        switched = 0
        for a, b in self.PAIRS:
            on = self._pair(a, b, yun=a)          # a 当运 -> 当令
            off = self._pair(a, b, yun=(a % 9) + 1)  # a 退/死 -> 未必当令
            if on["timing"] != off["timing"]:
                self.assertNotEqual(on["verdict"], off["verdict"], f"{a}{b}")
                switched += 1
        self.assertGreater(switched, 0)

    def test_no_markdown_asterisks(self):
        """前端纯文本渲染，markdown 星号会原样露出。"""
        for a, b in self.PAIRS:
            p = self._pair(a, b)
            for key in ("name", "nature", "verdict", "advice"):
                self.assertNotIn("**", p[key], f"{a}{b} 的 {key}")

    def test_repeated_star_name_reads_naturally(self):
        """同数叠见不能写成「九紫九紫同宫」。"""
        p = self._pair(9, 9)
        self.assertNotIn("九紫九紫", p["name"])
        self.assertIn("九紫", p["name"])

    def test_house_chart_carries_pair(self):
        """宅运盘每一宫都要带双星组合，且大凶组合要进行动要点。"""
        chart = house_chart(degree=0.0, yun=8)
        for p in chart["palaces"]:
            self.assertIn("pair", p)
            self.assertEqual(p["pair"]["key"],
                             "".join(str(x) for x in sorted(
                                 (p["shan_star"], p["xiang_star"]))))
        bad = [p for p in chart["palaces"]
               if not p["is_center"] and p["pair"]["level"] == "大凶"]
        self.assertTrue(bad, "八运子山午向应有二五交加")
        joined = " ".join(chart["key_points"])
        for p in bad:
            self.assertIn(p["pair"]["name"], joined)


if __name__ == "__main__":  # pragma: no cover
    unittest.main(verbosity=2)
