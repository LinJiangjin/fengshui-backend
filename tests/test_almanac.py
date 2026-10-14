# -*- coding: utf-8 -*-
"""黄历与择日引擎测试。

三层断言，目的各不相同：

1. **历法事实不得自研**：逐项对照 ``lunar-python`` 的干支 / 建除 / 天神 /
   宿曜 / 冲煞 / 宜忌 / 时辰，确保引擎只是转述而非另起一套算法——黄历最忌讳
   的就是「自己算一套、和通书对不上」。
2. **常量表自检**：建除 12、天神 12（黄黑道各 6）、宿曜 28（吉凶各 14），
   且与历法库判定一致；事项词表里的每个词都必须真实出现在通书宜忌里，
   否则该词永远命中不了，配置等于摆设。
3. **择日打分可解释**：排序单调、避冲扣分、命中项与宜忌逐一对得上。

运行：python -m unittest tests.test_almanac -v
"""

import datetime as dt
import unittest

from app.engine import (
    day_almanac,
    day_score,
    list_activities,
    month_overview,
    parse_date,
    select_dates,
)
from app.engine import daily_chart
from app.engine.almanac import activity_of
from app.engine.constants import (
    ALMANAC_ACTIVITIES,
    ALMANAC_LEVELS,
    ALMANAC_SCORE,
    JIANCHU_INFO,
    TIAN_SHEN_INFO,
    XIU_INFO,
    ZODIACS,
)

try:
    from lunar_python import Solar
except ImportError:  # pragma: no cover - 依赖缺失时本文件整体无意义
    Solar = None

# 抽样日期：跨 4 个年份、覆盖节气前后、农历年边界与月末
_SAMPLE_DATES = [
    dt.date(year, month, day)
    for year in (2024, 2025, 2026, 2027)
    for month, day in (
        (1, 1), (1, 20), (2, 3), (2, 4), (2, 5), (3, 15),
        (5, 5), (6, 21), (8, 7), (10, 14), (12, 21), (12, 31),
    )
]

FIXED_DATE = dt.date(2026, 10, 14)


@unittest.skipIf(Solar is None, "需要 lunar-python 才能做历法对照")
class TestCalendarFidelity(unittest.TestCase):
    """引擎输出必须与历法库逐项一致——这是黄历可信度的底线。"""

    def _lunar(self, date: dt.date):
        return Solar.fromYmd(date.year, date.month, date.day).getLunar()

    def test_gan_zhi_and_xun_match_library(self):
        for date in _SAMPLE_DATES:
            with self.subTest(date=date.isoformat()):
                lunar = self._lunar(date)
                got = day_almanac(date)
                self.assertEqual(got["gan_zhi"]["year"], lunar.getYearInGanZhi())
                self.assertEqual(got["gan_zhi"]["month"], lunar.getMonthInGanZhi())
                self.assertEqual(got["gan_zhi"]["day"], lunar.getDayInGanZhi())
                self.assertEqual(got["gan_zhi"]["year_animal"], lunar.getYearShengXiao())
                self.assertEqual(got["xun"]["name"], lunar.getDayXun())
                self.assertEqual(got["xun"]["kong"], lunar.getDayXunKong())
                self.assertEqual(got["na_yin"], lunar.getDayNaYin())
                self.assertEqual(got["chong"]["zodiac"], lunar.getDayChongShengXiao())
                self.assertEqual(got["chong"]["sha"], lunar.getDaySha())

    def test_jian_chu_and_tian_shen_match_library(self):
        for date in _SAMPLE_DATES:
            with self.subTest(date=date.isoformat()):
                lunar = self._lunar(date)
                got = day_almanac(date)
                self.assertEqual(got["jian_chu"]["name"], lunar.getZhiXing())
                self.assertEqual(got["tian_shen"]["name"], lunar.getDayTianShen())
                self.assertEqual(got["tian_shen"]["type"], lunar.getDayTianShenType())
                self.assertEqual(got["tian_shen"]["luck"], lunar.getDayTianShenLuck())
                # 常量表与库的判定必须一致，防止两套吉凶分档悄悄漂移
                self.assertEqual(
                    got["tian_shen"]["type"], TIAN_SHEN_INFO[lunar.getDayTianShen()]["type"]
                )

    def test_xiu_matches_library(self):
        for date in _SAMPLE_DATES:
            with self.subTest(date=date.isoformat()):
                lunar = self._lunar(date)
                got = day_almanac(date)
                self.assertEqual(got["xiu"]["name"], lunar.getXiu())
                self.assertEqual(got["xiu"]["luck"], lunar.getXiuLuck())
                self.assertEqual(got["xiu"]["luck"], XIU_INFO[lunar.getXiu()]["luck"])

    def test_yi_ji_match_library(self):
        for date in _SAMPLE_DATES:
            with self.subTest(date=date.isoformat()):
                lunar = self._lunar(date)
                raw_yi = list(lunar.getDayYi())
                raw_ji = list(lunar.getDayJi())
                got = day_almanac(date)
                # 字面量「无」会被剔除，其余逐项一致且顺序不变
                self.assertEqual(got["yi"], [x for x in raw_yi if x != "无"])
                self.assertEqual(got["ji"], [x for x in raw_ji if x != "无"])
                self.assertNotIn("无", got["yi"])
                self.assertNotIn("无", got["ji"])
                self.assertEqual(got["all_avoid"], "诸事不宜" in raw_ji)

    def test_chong_and_peng_zu_and_gods(self):
        for date in _SAMPLE_DATES:
            with self.subTest(date=date.isoformat()):
                lunar = self._lunar(date)
                got = day_almanac(date)
                self.assertEqual(got["chong"]["desc"], lunar.getDayChongDesc())
                self.assertEqual(got["peng_zu"]["gan"], lunar.getPengZuGan())
                self.assertEqual(got["peng_zu"]["zhi"], lunar.getPengZuZhi())
                self.assertEqual(got["ji_shen"], list(lunar.getDayJiShen()))
                self.assertEqual(got["xiong_sha"], list(lunar.getDayXiongSha()))
                directions = {g["key"]: g["direction"] for g in got["five_gods"]}
                self.assertEqual(directions["xi"], lunar.getDayPositionXiDesc())
                self.assertEqual(directions["fu"], lunar.getDayPositionFuDesc())
                self.assertEqual(directions["cai"], lunar.getDayPositionCaiDesc())
                self.assertEqual(
                    directions["yang_gui"], lunar.getDayPositionYangGuiDesc()
                )
                self.assertEqual(
                    directions["yin_gui"], lunar.getDayPositionYinGuiDesc()
                )

    def test_hours_match_library(self):
        for date in _SAMPLE_DATES:
            with self.subTest(date=date.isoformat()):
                raw = list(self._lunar(date).getTimes())
                got = day_almanac(date)["hours"]
                self.assertEqual(len(got), len(raw))
                for mine, theirs in zip(got, raw):
                    self.assertEqual(mine["branch"], theirs.getZhi())
                    self.assertEqual(mine["gan_zhi"], theirs.getGanZhi())
                    self.assertEqual(mine["tian_shen"], theirs.getTianShen())
                    self.assertEqual(mine["tian_shen_type"], theirs.getTianShenType())
                    self.assertEqual(mine["luck"], theirs.getTianShenLuck())
                    self.assertEqual(mine["is_lucky"], theirs.getTianShenType() == "黄道")
                    self.assertEqual(
                        mine["range"], f"{theirs.getMinHm()}–{theirs.getMaxHm()}"
                    )


class TestConstantTables(unittest.TestCase):
    """常量表自身的完整性与有效性。"""

    def test_jian_chu_table_is_complete(self):
        self.assertEqual(len(JIANCHU_INFO), 12)
        allowed = {"大吉", "黄道", "黑道", "大凶"}
        for name, info in JIANCHU_INFO.items():
            with self.subTest(name=name):
                self.assertIn(info["tone"], allowed)
                for key in ("meaning", "good", "bad"):
                    self.assertTrue(info[key], f"{name} 缺 {key}")

    def test_tian_shen_table_has_six_each(self):
        self.assertEqual(len(TIAN_SHEN_INFO), 12)
        types = [info["type"] for info in TIAN_SHEN_INFO.values()]
        self.assertEqual(types.count("黄道"), 6)
        self.assertEqual(types.count("黑道"), 6)
        for name, info in TIAN_SHEN_INFO.items():
            with self.subTest(name=name):
                expected_luck = "吉" if info["type"] == "黄道" else "凶"
                self.assertEqual(info["luck"], expected_luck)

    def test_xiu_table_is_complete(self):
        self.assertEqual(len(XIU_INFO), 28)
        lucks = [info["luck"] for info in XIU_INFO.values()]
        self.assertEqual(lucks.count("吉"), 14)
        self.assertEqual(lucks.count("凶"), 14)
        mansions = {info["mansion"] for info in XIU_INFO.values()}
        self.assertEqual(len(mansions), 4)

    def test_activity_terms_are_real_almanac_words(self):
        """事项词表里的每个词都必须真的出现在通书宜忌里。

        否则该词永远命中不了，配置等于摆设——这条断言就是为了防止
        以后随手加一个「看起来像通书用词」但历法库根本不用的词。
        """
        vocabulary = set()
        for offset in range(366):
            day = day_almanac(dt.date(2026, 1, 1) + dt.timedelta(days=offset))
            vocabulary.update(day["yi"])
            vocabulary.update(day["ji"])

        for activity in ALMANAC_ACTIVITIES:
            with self.subTest(activity=activity["name"]):
                unknown = [t for t in activity["terms"] if t not in vocabulary]
                self.assertEqual(unknown, [], f"无效词：{unknown}")

    def test_activity_keys_are_unique(self):
        keys = [a["key"] for a in ALMANAC_ACTIVITIES]
        self.assertEqual(len(keys), len(set(keys)))


@unittest.skipIf(Solar is None, "需要 lunar-python")
class TestDayAlmanac(unittest.TestCase):
    """单日通书的固定快照：任何改动把结论改坏都会红。"""

    def test_fixed_date_snapshot(self):
        got = day_almanac(FIXED_DATE)
        self.assertEqual(got["date"], "2026-10-14")
        self.assertEqual(got["weekday"], "周三")
        self.assertEqual(got["lunar"]["text"], "二〇二六年九月初五")
        self.assertEqual(got["lunar"]["month"], "九月")
        self.assertEqual(got["lunar"]["day"], "初五")
        self.assertFalse(got["lunar"]["is_leap"])
        self.assertEqual(got["gan_zhi"]["day"], "辛酉")
        self.assertEqual(got["jian_chu"]["name"], "闭")
        self.assertEqual(got["jian_chu"]["tone"], "大凶")
        self.assertEqual(got["jian_chu"]["label"], "闭日")
        self.assertEqual(got["tian_shen"]["name"], "天德")
        self.assertEqual(got["tian_shen"]["type"], "黄道")
        self.assertEqual(got["xiu"]["name"], "轸")
        self.assertEqual(got["xiu"]["full"], "轸水蚓")
        self.assertEqual(got["xiu"]["mansion"], "南方朱雀")
        self.assertEqual(got["xiu"]["luck"], "吉")
        self.assertEqual(got["chong"]["zodiac"], "兔")
        self.assertEqual(got["na_yin"], "石榴木")
        self.assertIn("动土", got["yi"])
        self.assertNotIn("动土", got["ji"])
        self.assertFalse(got["all_avoid"])
        self.assertEqual(len(got["hours"]), 13)
        self.assertEqual(len(got["lucky_hours"]), 6)
        self.assertEqual(
            len(got["hours"]), len(got["lucky_hours"]) + len(got["unlucky_hours"])
        )

    def test_zi_hours_are_split_and_labelled(self):
        """早子时与晚子时都必须保留且可区分（两者干支不同）。"""
        got = day_almanac(FIXED_DATE)
        zi = [h for h in got["hours"] if h["branch"] == "子"]
        self.assertEqual(len(zi), 2)
        self.assertEqual(zi[0]["slot_label"], "子时（早）")
        self.assertEqual(zi[1]["slot_label"], "子时（晚）")
        self.assertEqual(zi[0]["range"], "00:00–00:59")
        self.assertEqual(zi[1]["range"], "23:00–23:59")
        self.assertNotEqual(zi[0]["gan_zhi"], zi[1]["gan_zhi"])
        # 非子时不做早晚标注
        for hour in got["hours"]:
            if hour["branch"] != "子":
                self.assertEqual(hour["slot_label"], hour["label"])

    def test_purple_white_reuses_daily_chart(self):
        got = day_almanac(FIXED_DATE)["purple_white"]
        chart = daily_chart(FIXED_DATE)
        self.assertEqual(got["center_star"], chart["center_star"])
        self.assertEqual(got["center_star_name"], chart["center_star_name"])
        self.assertEqual(got["escape"], chart["escape"])
        self.assertEqual(got["yuan"], chart["yuan"])
        self.assertEqual(got["best"], chart["best"])
        self.assertEqual(got["worst"], chart["worst"])

    def test_score_is_in_range_and_deterministic(self):
        first = day_almanac(FIXED_DATE)
        second = day_almanac(FIXED_DATE)
        self.assertEqual(first["score"], second["score"])
        self.assertEqual(first["score_reasons"], second["score_reasons"])
        self.assertGreaterEqual(first["score"], 0)
        self.assertLessEqual(first["score"], 100)
        labels = [label for _, label, _ in ALMANAC_LEVELS]
        self.assertIn(first["level"], labels)


@unittest.skipIf(Solar is None, "需要 lunar-python")
class TestDayScore(unittest.TestCase):
    """打分必须可解释：每条加/减分都能落到具体依据上。"""

    def test_activity_discriminates_within_same_day(self):
        """同一天对不同事项的分数必须不同——否则择日毫无意义。"""
        day = day_almanac(dt.date(2026, 11, 17))
        zhuangxiu = day_score(day, activity_of("zhuangxiu"))
        ruhuo = day_score(day, activity_of("ruhuo"))
        self.assertGreater(zhuangxiu["value"], ruhuo["value"])
        self.assertTrue(zhuangxiu["hits"])
        # 当天忌入宅 / 移徙，搬家分必然被压下去
        self.assertTrue(set(ruhuo["misses"]) & {"入宅", "移徙"})

    def test_hits_misses_trace_back_to_yi_ji(self):
        for offset in range(30):
            date = dt.date(2026, 11, 1) + dt.timedelta(days=offset)
            day = day_almanac(date)
            scored = day_score(day, activity_of("zhuangxiu"))
            with self.subTest(date=date.isoformat()):
                for term in scored["hits"]:
                    self.assertIn(term, day["yi"])
                for term in scored["misses"]:
                    self.assertIn(term, day["ji"])

    def test_score_is_monotonic_in_hits(self):
        """在其它条件相同时，命中宜项越多分数越高。

        构造法：取同一份「当日事实」，只替换宜 / 忌列表，避免建除、宿曜
        等条件混入干扰。
        """
        base = day_almanac(dt.date(2026, 11, 17))
        activity = activity_of("zhuangxiu")
        one_hit = dict(base, yi=["动土"], ji=[])
        three_hits = dict(base, yi=["动土", "修造", "拆卸"], ji=[])
        one_miss = dict(base, yi=["动土"], ji=["修造"])
        self.assertLess(
            day_score(one_hit, activity)["value"],
            day_score(three_hits, activity)["value"],
        )
        self.assertLess(
            day_score(one_miss, activity)["value"],
            day_score(one_hit, activity)["value"],
        )

    def test_core_term_outweighs_auxiliary_term(self):
        """词表靠前的核心工序比靠后的辅助工序更能定性。"""
        base = day_almanac(dt.date(2026, 11, 17))
        activity = activity_of("zhuangxiu")  # 动土 > 修造 > … > 安门
        core = dict(base, yi=["动土"], ji=[])
        aux = dict(base, yi=["安门"], ji=[])
        self.assertGreater(
            day_score(core, activity)["value"], day_score(aux, activity)["value"]
        )

    def test_no_hit_day_is_penalized(self):
        """宜项里没有该事项时不能算吉日，只能算「不忌」。"""
        base = day_almanac(dt.date(2026, 11, 17))
        activity = activity_of("zhuangxiu")
        missed_list = dict(base, yi=["祭祀"], ji=[])
        scored = day_score(missed_list, activity)
        self.assertEqual(scored["hits"], [])
        penalty = [r for r in scored["reasons"] if "非专宜之日" in r]
        self.assertEqual(len(penalty), 1)
        self.assertIn(str(ALMANAC_SCORE["no_hit"]), penalty[0])
        # 比命中核心工序的同样一天要低
        self.assertLess(scored["value"], day_score(base, activity)["value"])

    def test_all_avoid_day_is_penalized(self):
        """「诸事不宜」的日子必须被识别并重扣。"""
        target = None
        for offset in range(120):
            date = dt.date(2026, 1, 1) + dt.timedelta(days=offset)
            day = day_almanac(date)
            if day["all_avoid"]:
                target = day
                break
        self.assertIsNotNone(target, "120 天内应存在「诸事不宜」的日子")
        scored = day_score(target, activity_of("zhuangxiu"))
        reasons = " ".join(scored["reasons"])
        self.assertIn("诸事不宜", reasons)

    def test_clash_reduces_score_and_flags(self):
        """冲用户生肖的日子要扣分并显式标记，而不是悄悄消失。"""
        target = None
        for offset in range(40):
            date = dt.date(2026, 1, 1) + dt.timedelta(days=offset)
            day = day_almanac(date)
            if day["chong"]["zodiac"] == "兔":
                target = day
                break
        self.assertIsNotNone(target)
        activity = activity_of("zhuangxiu")
        neutral = day_score(target, activity, "")
        clashing = day_score(target, activity, "兔")
        self.assertFalse(neutral["clash"])
        self.assertTrue(clashing["clash"])
        self.assertLessEqual(clashing["value"], neutral["value"])
        self.assertIn("相冲", " ".join(clashing["reasons"]))
        # 其它生肖不受影响
        other = day_score(target, activity, "鼠")
        self.assertFalse(other["clash"])


@unittest.skipIf(Solar is None, "需要 lunar-python")
class TestSelectDates(unittest.TestCase):
    """择日：排序、区间、避冲、参数校验。"""

    START = dt.date(2026, 11, 1)

    def test_sorted_desc_and_inside_range(self):
        result = select_dates("zhuangxiu", self.START, days=45, limit=10)
        pairs = [(item["score"], item["date"]) for item in result["items"]]
        self.assertEqual(pairs, sorted(pairs, key=lambda p: (-p[0], p[1])))
        for item in result["items"]:
            day = parse_date(item["date"])
            self.assertGreaterEqual(day, self.START)
            self.assertLessEqual(day, self.START + dt.timedelta(days=44))
        self.assertEqual(result["scanned"], 45)
        self.assertEqual(result["range"]["days"], 45)

    def test_limit_and_min_score(self):
        result = select_dates("zhuangxiu", self.START, days=60, limit=3)
        self.assertLessEqual(len(result["items"]), 3)
        strict = select_dates("zhuangxiu", self.START, days=60, limit=60, min_score=90)
        for item in strict["items"]:
            self.assertGreaterEqual(item["score"], 90)
        self.assertGreaterEqual(strict["recommended_count"], len(strict["items"]))

    def test_best_is_top_of_interval(self):
        result = select_dates("zhuangxiu", self.START, days=30, limit=5)
        best = result["best"]
        self.assertIsNotNone(best)
        self.assertGreaterEqual(best["score"], max(i["score"] for i in result["items"]))

    def test_clash_items_are_kept_but_flagged(self):
        result = select_dates("zhuangxiu", self.START, days=60, limit=60, zodiac="兔")
        self.assertTrue(result["items"])
        clashed = [i for i in result["items"] if i["clash"]]
        self.assertTrue(clashed, "60 天内应存在冲兔的日子")
        # 冲日若仍被推荐，必须显式标记，不能瞒着用户
        for item in clashed:
            self.assertIn("相冲", " ".join(item["reasons"]))

    def test_unknown_activity_and_zodiac_raise(self):
        with self.assertRaises(ValueError):
            select_dates("nope", self.START, days=5)
        with self.assertRaises(ValueError):
            select_dates("zhuangxiu", self.START, days=5, zodiac="猫")

    def test_days_and_limit_are_clamped(self):
        result = select_dates("zhuangxiu", self.START, days=9999, limit=999)
        self.assertEqual(result["scanned"], 366)
        self.assertLessEqual(len(result["items"]), 60)

    def test_every_activity_returns_candidates(self):
        for activity in list_activities():
            with self.subTest(activity=activity["name"]):
                result = select_dates(activity["key"], self.START, days=60, limit=5)
                self.assertTrue(
                    result["items"], f"{activity['name']} 60 天内无候选"
                )
                for item in result["items"]:
                    self.assertTrue(item["reasons"])

    def test_zodiac_list_is_covered(self):
        self.assertEqual(len(ZODIACS), 12)
        for zodiac in ZODIACS:
            with self.subTest(zodiac=zodiac):
                select_dates("zhuangxiu", self.START, days=2, zodiac=zodiac)


@unittest.skipIf(Solar is None, "需要 lunar-python")
class TestMonthOverview(unittest.TestCase):
    def test_day_count_and_best(self):
        for year, month, expected in (
            (2026, 2, 28),
            (2026, 11, 30),
            (2024, 2, 29),
            (2026, 10, 31),
        ):
            with self.subTest(year=year, month=month):
                overview = month_overview(year, month, "zhuangxiu")
                self.assertEqual(len(overview["days"]), expected)
                self.assertEqual(overview["days"][0]["day"], 1)
                self.assertEqual(overview["days"][-1]["day"], expected)
                self.assertEqual(overview["first_weekday"], dt.date(year, month, 1).weekday())
                self.assertEqual(
                    overview["best"]["score"],
                    max(d["score"] for d in overview["days"]),
                )

    def test_without_activity_is_general_score(self):
        overview = month_overview(2026, 11)
        self.assertIsNone(overview["activity"])
        self.assertTrue(overview["days"])

    def test_invalid_month_raises(self):
        with self.assertRaises(ValueError):
            month_overview(2026, 13)
        with self.assertRaises(ValueError):
            month_overview(2026, 0)

    def test_scores_match_single_day_calls(self):
        """月历每天的分数必须与单独算那天一致，避免两条口径。"""
        overview = month_overview(2026, 11, "zhuangxiu")
        activity = activity_of("zhuangxiu")
        for item in overview["days"][:5]:
            day = day_almanac(parse_date(item["date"]))
            self.assertEqual(item["score"], day_score(day, activity)["value"])
            self.assertEqual(item["chong"], day["chong"]["desc"])


class TestDateParsing(unittest.TestCase):
    def test_parse_date(self):
        self.assertEqual(parse_date("2026-10-14"), dt.date(2026, 10, 14))
        self.assertIsNone(parse_date(""))
        self.assertIsNone(parse_date(None))
        for bad in ("2026/10/14", "20261014", "2026-13-45", "今天"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    parse_date(bad)


@unittest.skipIf(Solar is None, "需要 lunar-python")
class TestLunarYearCache(unittest.TestCase):
    """多年份历法表缓存的正确性与性能护栏。

    库自带的缓存只有单槽，黄历需要同时用到 year±1 的历法表，命中率极低。
    ``app.engine.lunar_cache`` 换成多年份缓存——这里的断言保证两件事：
    缓存不改变任何输出；以及缓存确实在生效（否则一次 30 天择日要 2.5 秒）。
    """

    def test_cache_is_installed(self):
        from app.engine.lunar_cache import INSTALLED

        self.assertTrue(INSTALLED, "多年份历法缓存未生效")

    def test_from_year_is_memoized(self):
        from lunar_python.LunarYear import LunarYear

        self.assertIs(LunarYear.fromYear(2026), LunarYear.fromYear(2026))
        # 隔着一个年份再取，仍应拿到同一实例（单槽缓存做不到这点）
        first = LunarYear.fromYear(2025)
        LunarYear.fromYear(2026)
        self.assertIs(LunarYear.fromYear(2025), first)

    def test_clearing_cache_does_not_change_output(self):
        from lunar_python.LunarYear import LunarYear

        date = dt.date(2026, 10, 14)
        before = day_almanac(date)
        cache_clear = getattr(LunarYear.fromYear, "cache_clear", None)
        self.assertIsNotNone(cache_clear, "缓存函数应可清空，便于对照")
        cache_clear()
        after = day_almanac(date)
        self.assertEqual(before, after)

    def test_thirty_day_select_stays_fast(self):
        """性能护栏：缓存一旦失效，30 天选区会退化到 2.5 秒量级。"""
        import time

        start = dt.date(2026, 11, 1)
        select_dates("zhuangxiu", start, days=2)  # 预热
        began = time.perf_counter()
        select_dates("zhuangxiu", start, days=30)
        elapsed = time.perf_counter() - began
        # 实测约 0.06 秒；给 25 倍余量以容忍 CI 抖动，但足以拦住缓存丢失
        self.assertLess(elapsed, 1.5, f"30 天择日耗时 {elapsed:.2f}s，疑似历法缓存失效")


if __name__ == "__main__":
    unittest.main()
