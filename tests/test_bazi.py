# -*- coding: utf-8 -*-
"""八字排盘引擎单元测试。

这些断言是「大模型不可介入」的底线：算法一旦改动就会红。
运行：python -m unittest discover -s tests -v
"""

import datetime as dt
import unittest

from app.engine import (
    apply_night_zi_fix,
    build_bazi,
    day_pillar_from_anchor,
    element_summary_of,
    hour_branch_of,
    hour_pillar_gan,
    jiazi_index,
    judge_strength,
    na_yin_of,
    pick_gods,
    score_elements,
    shi_shen_of,
    to_percent,
    true_solar_time,
)

try:
    from lunar_python import Solar
except ImportError:  # pragma: no cover - 依赖缺失时跳过交叉校验用例
    Solar = None


def _pillars(profile):
    """四柱干支字符串列表：['戊辰', '乙卯', '丙寅', '壬辰']。"""
    return [p["pillar"] for p in profile["pillars"]]


class TestSolarTermBoundary(unittest.TestCase):
    """月柱必须按节气分界：立春换年、惊蛰换月。"""

    def test_design_case_1988_03_12(self):
        """设计稿示例：1988-03-12 辰时（08:00）· 男。"""
        profile = build_bazi(1988, 3, 12, 8, 0, "男", 120.0)
        self.assertEqual(_pillars(profile), ["戊辰", "乙卯", "丙寅", "壬辰"])
        self.assertEqual(profile["day_master"]["gan"], "丙")
        self.assertEqual(profile["day_master"]["element"], "火")
        self.assertEqual(profile["birth"]["hour_zhi"], "辰")
        self.assertEqual(profile["birth"]["summary"], "1988.03.12 辰时 · 男")
        self.assertEqual(profile["birth"]["is_night_zi"], False)

    def test_month_is_mao_after_jingzhe(self):
        """3 月 12 日在惊蛰之后、清明之前，月支应为卯。"""
        profile = build_bazi(1988, 3, 12, 8, 0)
        self.assertEqual(profile["pillars"][1]["zhi"], "卯")
        self.assertEqual(profile["pillars"][1]["pillar"], "乙卯")

    def test_jingzhe_boundary_switches_month(self):
        """1988 年惊蛰交节于 03-05 16:46:32，前后月柱应由寅转卯。"""
        before = build_bazi(1988, 3, 5, 12, 0)   # 交节前 -> 寅月
        after = build_bazi(1988, 3, 5, 23, 0)    # 交节后 -> 卯月
        self.assertEqual(before["pillars"][1]["zhi"], "寅")
        self.assertEqual(after["pillars"][1]["zhi"], "卯")
        self.assertNotEqual(
            before["pillars"][1]["pillar"], after["pillars"][1]["pillar"]
        )

    def test_next_day_after_jingzhe(self):
        self.assertEqual(build_bazi(1988, 3, 6, 0, 30)["pillars"][1]["zhi"], "卯")

    def test_lichun_boundary_switches_year(self):
        """1988 年立春交节于 02-04 22:42:49，前后年柱应由丁卯转戊辰。"""
        before = build_bazi(1988, 2, 4, 12, 0)
        after = build_bazi(1988, 2, 4, 23, 0)
        self.assertEqual(before["pillars"][0]["pillar"], "丁卯")
        self.assertEqual(after["pillars"][0]["pillar"], "戊辰")

    def test_year_not_calendar_new_year(self):
        """公历 1 月 1 日仍在上一甲子年：1988-01-01 年柱应为丁卯。"""
        profile = build_bazi(1988, 1, 1, 10, 0)
        self.assertEqual(profile["pillars"][0]["pillar"], "丁卯")


class TestHourPillar(unittest.TestCase):
    """时柱：五鼠遁 + 时辰地支。"""

    def test_hour_branch_of(self):
        self.assertEqual(hour_branch_of(23), "子")
        self.assertEqual(hour_branch_of(0), "子")
        self.assertEqual(hour_branch_of(1), "丑")
        self.assertEqual(hour_branch_of(3), "寅")
        self.assertEqual(hour_branch_of(8), "辰")
        self.assertEqual(hour_branch_of(13), "未")
        self.assertEqual(hour_branch_of(21), "亥")

    def test_wu_shu_dun_start(self):
        self.assertEqual(hour_pillar_gan("甲", "子"), "甲")
        self.assertEqual(hour_pillar_gan("己", "子"), "甲")
        self.assertEqual(hour_pillar_gan("乙", "子"), "丙")
        self.assertEqual(hour_pillar_gan("庚", "子"), "丙")
        self.assertEqual(hour_pillar_gan("丙", "子"), "戊")
        self.assertEqual(hour_pillar_gan("辛", "子"), "戊")
        self.assertEqual(hour_pillar_gan("丁", "子"), "庚")
        self.assertEqual(hour_pillar_gan("壬", "子"), "庚")
        self.assertEqual(hour_pillar_gan("戊", "子"), "壬")
        self.assertEqual(hour_pillar_gan("癸", "子"), "壬")

    def test_design_case_time_pillar(self):
        """日干丙 -> 子时起戊子 -> 辰时为壬辰。"""
        self.assertEqual(hour_pillar_gan("丙", "辰"), "壬")
        profile = build_bazi(1988, 3, 12, 8, 0)
        self.assertEqual(profile["pillars"][3]["pillar"], "壬辰")

    def test_night_zi_flag(self):
        night = build_bazi(1988, 3, 12, 23, 30)
        day = build_bazi(1988, 3, 12, 0, 30)
        self.assertTrue(night["birth"]["is_night_zi"])
        self.assertFalse(day["birth"]["is_night_zi"])
        self.assertEqual(night["birth"]["hour_zhi"], "子")

    def test_hour_gan_consistent_with_day_gan_all_hours(self):
        """0-23 全小时：时干必须由当日日干五鼠遁得出。

        排盘库在 23 时会用「次日日干」遁时干，与 sect=2 的当日日柱打架，
        曾拼出「丙寅日 + 庚子时」这种六十甲子里并不存在的组合。这条断言
        是该 bug 的回归防线，改动排盘路径时先看这里。
        """
        for hour in range(24):
            with self.subTest(hour=hour):
                profile = build_bazi(1988, 3, 12, hour, 30)
                day_gan = profile["pillars"][2]["gan"]
                hour_pillar = profile["pillars"][3]
                self.assertEqual(
                    hour_pillar["gan"],
                    hour_pillar_gan(day_gan, hour_pillar["zhi"]),
                )
                self.assertEqual(
                    hour_pillar["pillar"],
                    hour_pillar["gan"] + hour_pillar["zhi"],
                )

    def test_night_zi_pillar_is_self_consistent(self):
        """夜子时验收口径：丙日 23:30 -> 时柱戊子（非库默认的庚子）。

        时干错会连带污染五行与用神：修前金为 10%、「木旺缺金」被翻成
        「木旺五行均衡」，喜用神推荐跟着变。
        """
        profile = build_bazi(1988, 3, 12, 23, 30)
        self.assertEqual(profile["pillars"][3]["pillar"], "戊子")
        self.assertEqual(profile["element_summary"], "日主丙火 · 木旺缺金")
        gold = next(e for e in profile["elements"] if e["element"] == "金")
        self.assertEqual(gold["percent"], 0)

    def test_hour_gan_same_as_day_gan_is_bijian(self):
        """时干与日干同名时十神为「比肩」，不是「日主」。

        「日主」是日柱天干这一位置的称呼。六十甲子中只有甲日的子时会让
        时干与日干同名（甲子时），叠加夜子时修正路径，曾把时柱十神错标
        成「日主」。
        """
        night = build_bazi(1988, 3, 20, 23, 30)  # 甲日 23:30 -> 甲子时
        self.assertEqual(night["pillars"][2]["gan"], "甲")
        self.assertEqual(night["pillars"][3]["pillar"], "甲子")
        self.assertEqual(night["pillars"][3]["gan_shi_shen"], "比肩")
        self.assertEqual(night["pillars"][2]["gan_shi_shen"], "日主")
        # 同日干走库默认路径（非夜子时），口径必须一致
        day = build_bazi(1988, 3, 20, 0, 30)
        self.assertEqual(day["pillars"][3]["pillar"], "甲子")
        self.assertEqual(day["pillars"][3]["gan_shi_shen"], "比肩")


class TestTrueSolarTime(unittest.TestCase):
    """真太阳时：每度 4 分钟。"""

    def test_offset_minutes(self):
        _, offset = true_solar_time(1988, 3, 12, 8, 0, 105.0)
        self.assertAlmostEqual(offset, -60.0)
        _, offset = true_solar_time(1988, 3, 12, 8, 0, 127.5)
        self.assertAlmostEqual(offset, 30.0)

    def test_cross_midnight(self):
        moment, offset = true_solar_time(1988, 3, 12, 0, 30, 100.0)
        self.assertAlmostEqual(offset, -80.0)
        self.assertEqual(moment, dt.datetime(1988, 3, 11, 23, 10))

    def test_longitude_changes_hour_branch(self):
        """东经 90° 时差 -120 分钟，8:00 变成真太阳时 6:00 -> 卯时。"""
        profile = build_bazi(1988, 3, 12, 8, 0, "男", 90.0)
        self.assertEqual(profile["birth"]["true_solar"], "1988-03-12 06:00")
        self.assertEqual(profile["birth"]["hour_zhi"], "卯")
        self.assertEqual(profile["pillars"][3]["pillar"], "辛卯")


class TestDayPillarAnchor(unittest.TestCase):
    """日柱：1900-01-01 = 甲戌 为锚点按日差推算，并与排盘库交叉校验。"""

    def test_anchor_itself(self):
        self.assertEqual(day_pillar_from_anchor(dt.date(1900, 1, 1)), "甲戌")

    def test_anchor_next_days(self):
        self.assertEqual(day_pillar_from_anchor(dt.date(1900, 1, 2)), "乙亥")
        self.assertEqual(day_pillar_from_anchor(dt.date(1900, 1, 3)), "丙子")

    @unittest.skipIf(Solar is None, "lunar-python 未安装")
    def test_cross_check_with_library(self):
        """1900-2100 全区间抽样，锚点算法与排盘库必须完全一致。"""
        start = dt.date(1900, 1, 1)
        for offset in range(0, (dt.date(2100, 12, 31) - start).days, 37):
            day = start + dt.timedelta(days=offset)
            expected = day_pillar_from_anchor(day)
            actual = Solar.fromYmdHms(
                day.year, day.month, day.day, 12, 0, 0
            ).getLunar().getEightChar().getDay()
            self.assertEqual(expected, actual, f"{day}: {expected} != {actual}")


class TestHiddenGan(unittest.TestCase):
    """地支藏干：本气 / 中气 / 余气。"""

    def test_chen_hidden(self):
        profile = build_bazi(1988, 3, 12, 8, 0)
        chen = profile["pillars"][0]["hidden"]
        self.assertEqual([h["gan"] for h in chen], ["戊", "乙", "癸"])
        self.assertEqual([h["role"] for h in chen], ["本气", "中气", "余气"])
        self.assertEqual([h["weight"] for h in chen], [1.0, 0.6, 0.3])
        self.assertEqual(profile["pillars"][0]["hidden_text"], "戊乙癸")

    def test_mao_hidden_single(self):
        profile = build_bazi(1988, 3, 12, 8, 0)
        self.assertEqual(profile["pillars"][1]["hidden_text"], "乙")

    @unittest.skipIf(Solar is None, "lunar-python 未安装")
    def test_cross_check_with_library(self):
        """藏干表（含顺序）与排盘库输出一致。"""
        samples = [
            (1988, 3, 12, 8), (1975, 7, 21, 15),
            (2000, 1, 1, 0), (2024, 12, 21, 23),
            (1966, 5, 5, 11),
        ]
        for year, month, day, hour in samples:
            profile = build_bazi(year, month, day, hour, 0)
            chart = Solar.fromYmdHms(
                year, month, day, hour, 0, 0
            ).getLunar().getEightChar()
            library = [
                chart.getYearHideGan(), chart.getMonthHideGan(),
                chart.getDayHideGan(), chart.getTimeHideGan(),
            ]
            for pillar, expected in zip(profile["pillars"], library):
                self.assertEqual(
                    list(pillar["hidden_text"]), expected,
                    f"{year}-{month}-{day} {pillar['name']}",
                )


class TestElements(unittest.TestCase):
    """五行占比。"""

    def test_design_case_values(self):
        profile = build_bazi(1988, 3, 12, 8, 0)
        percents = {e["element"]: e["percent"] for e in profile["elements"]}
        # 木 4.2 / 火 1.6 / 土 3.3 / 金 0 / 水 1.6，总分 10.7
        self.assertEqual(percents["木"], 39)
        self.assertEqual(percents["火"], 15)
        self.assertEqual(percents["土"], 31)
        self.assertEqual(percents["金"], 0)
        self.assertEqual(percents["水"], 15)
        self.assertEqual(profile["element_summary"], "日主丙火 · 木旺缺金")

    def test_summary_lists_all_missing_elements(self):
        """多个五行同时为 0 时，摘要须全部列出，不能只报一个。

        约 2% 的命盘会有多个五行缺失（如 2024-01-01 23:30 火土金皆缺），
        只报「缺火」会让人误以为土金不缺。
        """
        self.assertEqual(
            element_summary_of(
                "丙", "火", {"木": 39, "火": 15, "土": 31, "金": 0, "水": 15}),
            "日主丙火 · 木旺缺金",
        )
        self.assertEqual(
            element_summary_of(
                "甲", "木", {"木": 50, "火": 0, "土": 0, "金": 0, "水": 50}),
            "日主甲木 · 木旺缺火土金",
        )
        self.assertEqual(
            element_summary_of(
                "乙", "木", {"木": 12, "火": 25, "土": 21, "金": 32, "水": 10}),
            "日主乙木 · 五行均衡",
        )
        # 端到端：2024-01-01 23:30 火土金皆缺
        self.assertIn("缺火土金", build_bazi(2024, 1, 1, 23, 30)["element_summary"])

    def test_percent_always_sum_to_100(self):
        samples = [
            (1988, 3, 12, 8), (1975, 7, 21, 15), (2000, 1, 1, 0),
            (2024, 12, 21, 23), (1966, 5, 5, 11), (1999, 9, 9, 9),
            (2010, 6, 15, 3), (1949, 10, 1, 12),
        ]
        for year, month, day, hour in samples:
            profile = build_bazi(year, month, day, hour, 0)
            total = sum(e["percent"] for e in profile["elements"])
            self.assertEqual(total, 100, f"{year}-{month}-{day} -> {total}")

    def test_to_percent_largest_remainder(self):
        percents = to_percent({"木": 1.0, "火": 1.0, "土": 1.0, "金": 0.0, "水": 0.0})
        self.assertEqual(sum(percents.values()), 100)
        self.assertEqual(percents["金"], 0)
        self.assertEqual(percents["水"], 0)

    def test_score_elements_weights(self):
        """天干 1.0 + 本气 1.0 + 中气 0.6 + 余气 0.3。"""
        profile = build_bazi(1988, 3, 12, 8, 0)
        scores = {e["element"]: e["score"] for e in profile["elements"]}
        self.assertAlmostEqual(scores["木"], 4.2, places=4)
        self.assertAlmostEqual(scores["火"], 1.6, places=4)
        self.assertAlmostEqual(scores["土"], 3.3, places=4)
        self.assertAlmostEqual(scores["水"], 1.6, places=4)
        self.assertAlmostEqual(scores["金"], 0.0, places=4)

    def test_score_elements_pure(self):
        pillars = [{"gan": "甲", "hidden": []}]
        scores = score_elements(pillars)
        self.assertAlmostEqual(scores["木"], 1.0)


class TestStrengthAndGods(unittest.TestCase):
    """日主强弱与用神喜忌。"""

    def test_design_case_is_strong(self):
        """丙火生于卯月，得印绶当令，又有寅中丙火为根 -> 偏强。"""
        profile = build_bazi(1988, 3, 12, 8, 0)
        self.assertEqual(profile["strength"]["level"], "偏强")
        self.assertGreaterEqual(profile["strength"]["score"], 4.0)
        self.assertEqual(profile["strength"]["detail"]["得令"], 3.0)
        # 寅为丙火长生，日支中气根计 1.0
        self.assertEqual(profile["strength"]["detail"]["得地"], 1.0)

    def test_strong_prefers_lacking_element(self):
        """身强缺金 -> 以财星（金）为喜用，忌印比（木）。"""
        profile = build_bazi(1988, 3, 12, 8, 0)
        favorable = [g["element"] for g in profile["favorable"]]
        unfavorable = [g["element"] for g in profile["unfavorable"]]
        self.assertEqual(favorable[0], "金")
        self.assertIn("金", favorable)
        self.assertNotIn("金", unfavorable)
        self.assertEqual(unfavorable[0], "木")

    def test_weak_prefers_supporting_element(self):
        """身弱（癸水生于午月）-> 喜印比（金 / 水），忌克泄。"""
        profile = build_bazi(1988, 6, 20, 12, 0)
        level = profile["strength"]["level"]
        if level == "偏弱":
            favorable = [g["element"] for g in profile["favorable"]]
            self.assertTrue(
                set(favorable).issubset({"金", "水"}),
                f"身弱应取印比，实际 {favorable}",
            )

    def test_pick_gods_pure(self):
        favorable, unfavorable = pick_gods("火", "偏强",
                                           {"木": 39, "火": 15, "土": 31, "金": 0, "水": 15})
        self.assertEqual([g["element"] for g in favorable], ["金", "水"])
        self.assertEqual([g["element"] for g in unfavorable], ["木", "火"])
        self.assertEqual(favorable[0]["label"], "金 · 收敛")
        self.assertEqual(favorable[0]["reason"], "财星耗身")
        self.assertEqual(favorable[0]["color_key"], "metal")

    def test_judge_strength_no_root_is_weak(self):
        """地支无同类根且月支克我 -> 偏弱。"""
        pillars = [
            {"key": "year", "name": "年柱", "gan": "戊", "zhi": "午",
             "gan_element": "土", "hidden": [
                 {"gan": "丁", "element": "火", "role": "本气", "weight": 1.0},
                 {"gan": "己", "element": "土", "role": "中气", "weight": 0.6}]},
            {"key": "month", "name": "月柱", "gan": "戊", "zhi": "午",
             "gan_element": "土", "hidden": [
                 {"gan": "丁", "element": "火", "role": "本气", "weight": 1.0},
                 {"gan": "己", "element": "土", "role": "中气", "weight": 0.6}]},
            {"key": "day", "name": "日柱", "gan": "癸", "zhi": "酉",
             "gan_element": "水", "hidden": [
                 {"gan": "辛", "element": "金", "role": "本气", "weight": 1.0}]},
            {"key": "time", "name": "时柱", "gan": "戊", "zhi": "午",
             "gan_element": "土", "hidden": [
                 {"gan": "丁", "element": "火", "role": "本气", "weight": 1.0},
                 {"gan": "己", "element": "土", "role": "中气", "weight": 0.6}]},
        ]
        result = judge_strength(pillars, "水")
        self.assertEqual(result["level"], "偏弱")
        self.assertEqual(result["detail"]["根"], "四支无根")


class TestValidation(unittest.TestCase):
    """入参校验。"""

    def test_invalid_date(self):
        with self.assertRaises(ValueError):
            build_bazi(1988, 2, 30, 8, 0)

    def test_invalid_gender(self):
        with self.assertRaises(ValueError):
            build_bazi(1988, 3, 12, 8, 0, "未知")

    def test_invalid_hour(self):
        with self.assertRaises(ValueError):
            build_bazi(1988, 3, 12, 24, 0)

    def test_invalid_longitude(self):
        with self.assertRaises(ValueError):
            build_bazi(1988, 3, 12, 8, 0, "男", 300.0)


class TestEnhance(unittest.TestCase):
    """文案增强钩子：未配置模型时原样返回。"""

    def test_enhance_is_identity(self):
        from app.engine import enhance_bazi

        profile = build_bazi(1988, 3, 12, 8, 0)
        self.assertEqual(enhance_bazi(profile, {}), profile)


if __name__ == "__main__":
    unittest.main()
