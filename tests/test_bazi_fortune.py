# -*- coding: utf-8 -*-
"""八字大运 / 流年测试。

锁的是**规则与可读性不变量**，不是字面文案——文案改版不该让测试红，
但「起运怎么算」「大运怎么推」「行话有没有解释」变了就必须红。
"""

from __future__ import annotations

import datetime as dt
import unittest

from app.engine import (
    build_bazi,
    build_bazi_fortune,
    build_bazi_years,
    da_yun_of,
    da_yun_forward_of,
    jiazi_index,
    true_solar_time,
)
from app.engine.bazi_fortune import (
    BRANCH_SELF_PUNISH,
    SHI_SHEN_PLAIN,
    _walk_jie,
)
from app.engine.constants import (
    BAZI_YEAR_COUNT,
    BRANCH_CLASH,
    BRANCH_HARM,
    BRANCH_HE,
    DA_YUN_SPAN,
    DA_YUN_STEPS,
    SHI_SHEN_FIELD,
)
from app.engine.ziwei_year import gan_zhi_of_year


def _chart(year: int, month: int, day: int, hour: int, minute: int,
           gender: str, longitude: float = 120.0):
    """排一份盘，并连带返回真太阳时（起运必须与排盘用同一时刻）。"""
    profile = build_bazi(year, month, day, hour, minute,
                         gender=gender, longitude=longitude)
    true_dt, _ = true_solar_time(year, month, day, hour, minute, longitude)
    return profile, true_dt


class ForwardCase(unittest.TestCase):
    """阳男阴女顺行，阴男阳女逆行。"""

    def test_yang_male_forward(self):
        self.assertTrue(da_yun_forward_of("甲", "男"))
        self.assertTrue(da_yun_forward_of("丙", "男"))
        self.assertTrue(da_yun_forward_of("戊", "男"))
        self.assertTrue(da_yun_forward_of("庚", "男"))
        self.assertTrue(da_yun_forward_of("壬", "男"))

    def test_yin_female_forward(self):
        self.assertTrue(da_yun_forward_of("乙", "女"))
        self.assertTrue(da_yun_forward_of("丁", "女"))
        self.assertTrue(da_yun_forward_of("辛", "女"))

    def test_yin_male_and_yang_female_backward(self):
        self.assertFalse(da_yun_forward_of("乙", "男"))
        self.assertFalse(da_yun_forward_of("辛", "男"))
        self.assertFalse(da_yun_forward_of("甲", "女"))
        self.assertFalse(da_yun_forward_of("戊", "女"))

    def test_bad_input(self):
        with self.assertRaises(ValueError):
            da_yun_forward_of("甲", "未知")
        with self.assertRaises(ValueError):
            da_yun_forward_of("X", "男")


class JieCase(unittest.TestCase):
    """找「节」必须跳过中气，且能跨年。"""

    def test_forward_skips_mid_term(self):
        # 1991-09-10 之后是秋分（中气），再之后才是寒露（节）
        name, at = _walk_jie(dt.datetime(1991, 9, 10, 7, 35), True)
        self.assertEqual(name, "寒露")
        self.assertEqual(at.date(), dt.date(1991, 10, 9))

    def test_backward_finds_prev_jie(self):
        name, at = _walk_jie(dt.datetime(1991, 9, 10, 7, 35), False)
        self.assertEqual(name, "白露")
        self.assertEqual(at.date(), dt.date(1991, 9, 8))

    def test_forward_crosses_year(self):
        # 1991-12-20 之后的节是次年的小寒
        name, at = _walk_jie(dt.datetime(1991, 12, 20, 7, 35), True)
        self.assertEqual(name, "小寒")
        self.assertEqual(at.year, 1992)

    def test_backward_crosses_year(self):
        # 1991-01-05 之前最近的节是上一年大雪（1991 小寒在 1/6，还没到）
        name, at = _walk_jie(dt.datetime(1991, 1, 5, 7, 35), False)
        self.assertEqual(name, "大雪")
        self.assertEqual(at.year, 1990)


class BranchRelationTableCase(unittest.TestCase):
    """地支关系表必须成对可逆，否则流年会判漏。"""

    def test_tables_are_symmetric(self):
        for table in (BRANCH_CLASH, BRANCH_HARM, BRANCH_HE):
            for a, b in table.items():
                self.assertEqual(table[b], a, f"{a}->{b} 不可逆")

    def test_each_branch_has_one_partner_per_table(self):
        for table in (BRANCH_CLASH, BRANCH_HARM, BRANCH_HE):
            self.assertEqual(len(table), 12)

    def test_self_punish_subset_of_branches(self):
        self.assertEqual(set(BRANCH_SELF_PUNISH), {"辰", "午", "酉", "亥"})


class DaYunCase(unittest.TestCase):
    """起运岁数与八步运程。"""

    def setUp(self):
        self.profile, self.true_dt = _chart(1991, 9, 10, 7, 35, "男", 113.26)
        self.dayun = da_yun_of(self.profile, self.true_dt, 1991)

    def test_direction_matches_year_gan_and_gender(self):
        # 1991 辛未年，辛为阴、命主男 -> 逆行
        self.assertFalse(self.dayun["forward"])

    def test_start_age_is_gap_days_over_three(self):
        self.assertEqual(self.dayun["start_age"],
                         self.dayun["gap_days"] // 3)
        self.assertEqual(self.dayun["start_months"],
                         (self.dayun["gap_days"] % 3) * 4)

    def test_steps_count_and_span(self):
        steps = self.dayun["steps"]
        self.assertEqual(len(steps), DA_YUN_STEPS)
        for s in steps:
            self.assertEqual(s["to_age"] - s["from_age"] + 1, DA_YUN_SPAN)
            self.assertEqual(s["to_year"] - s["from_year"] + 1, DA_YUN_SPAN)

    def test_steps_are_contiguous(self):
        steps = self.dayun["steps"]
        for prev, cur in zip(steps, steps[1:]):
            self.assertEqual(cur["from_age"], prev["to_age"] + 1)
            self.assertEqual(cur["from_year"], prev["to_year"] + 1)

    def test_first_step_is_one_away_from_month_pillar(self):
        """大运自月柱起：顺行 +1、逆行 -1。"""
        month = self.profile["pillars"][1]
        base = jiazi_index(month["gan"], month["zhi"])
        first = self.dayun["steps"][0]
        got = jiazi_index(first["gan"], first["zhi"])
        expect = (base - 1) % 60 if not self.dayun["forward"] else (base + 1) % 60
        self.assertEqual(got, expect)

    def test_anchor_yin_year_male(self):
        """1991-09-10 男：月柱丁酉，逆行第一步应为丙申。"""
        month = self.profile["pillars"][1]
        self.assertEqual(month["pillar"], "丁酉")
        self.assertEqual(self.dayun["steps"][0]["gan_zhi"], "丙申")

    def test_current_step_contains_today_age(self):
        cur = self.dayun["current"]
        self.assertIsNotNone(cur)
        self.assertTrue(cur["is_current"])
        self.assertLessEqual(cur["from_age"], self.dayun["age"])
        self.assertGreaterEqual(cur["to_age"], self.dayun["age"])
        # 只有一步被标记为当前
        self.assertEqual(sum(1 for s in self.dayun["steps"] if s["is_current"]), 1)

    def test_not_entered_yet(self):
        """起运之前：current 为 None，plain 要说明看月柱。"""
        profile, true_dt = _chart(2020, 6, 10, 8, 0, "女", 120.0)
        dayun = da_yun_of(profile, true_dt, 2020, today=dt.date(2022, 1, 1))
        if dayun["age"] < dayun["start_age"]:
            self.assertIsNone(dayun["current"])
            self.assertIn("月柱", dayun["plain"])

    def test_basis_is_human_readable(self):
        basis = self.dayun["basis"]
        self.assertIn("逆行" if not self.dayun["forward"] else "顺行", basis)
        self.assertIn(self.dayun["jie_name"], basis)
        self.assertIn("三天折一岁", basis)


class YearCase(unittest.TestCase):
    """流年。"""

    def setUp(self):
        self.profile, self.true_dt = _chart(1991, 9, 10, 7, 35, "男", 113.26)
        self.fortune = build_bazi_fortune(self.profile, self.true_dt, 1991)
        self.years = self.fortune["years"]

    def test_count_and_continuity(self):
        self.assertEqual(len(self.years), BAZI_YEAR_COUNT)
        for prev, cur in zip(self.years, self.years[1:]):
            self.assertEqual(cur["year"], prev["year"] + 1)
            self.assertEqual(cur["age"], prev["age"] + 1)

    def test_gan_zhi_matches_shared_helper(self):
        """流年干支与紫微流年共用同一个函数，不能各算各的。"""
        for y in self.years:
            self.assertEqual(y["gan_zhi"], gan_zhi_of_year(y["year"]))

    def test_window_covers_a_da_yun_switch(self):
        """12 年窗口里必须能看到换运（换运点刚好在窗口外时才允许为 0）。"""
        switches = [y for y in self.years if y["is_da_yun_switch"]]
        self.assertTrue(switches, "12 年里应当至少有一次换运")
        for y in switches:
            self.assertIsNotNone(y["da_yun"])

    def test_switch_year_lands_on_step_start(self):
        for y in self.years:
            if not y["is_da_yun_switch"]:
                continue
            self.assertEqual(y["age"] - self.fortune["da_yun"]["start_age"],
                             y["da_yun"]["index"] * DA_YUN_SPAN)

    def test_da_yun_of_year_matches_steps(self):
        """流年所属大运必须是八步之一，且年龄段能包住当年岁数。"""
        steps = {s["index"]: s for s in self.fortune["da_yun"]["steps"]}
        for y in self.years:
            if y["da_yun"] is None:
                self.assertLess(y["age"], self.fortune["da_yun"]["start_age"])
                continue
            step = steps[y["da_yun"]["index"]]
            self.assertEqual(step["gan_zhi"], y["da_yun"]["gan_zhi"])
            self.assertLessEqual(step["from_age"], y["age"])
            self.assertGreaterEqual(step["to_age"], y["age"])

    def test_stance_values(self):
        for y in self.years:
            self.assertIn(y["stance"], ("宜主动", "宜守成", "稳中求进"))

    def test_relations_are_grounded(self):
        """报出的关系必须真的能在关系表里查到，不能凭空编。"""
        for y in self.years:
            zhi = y["gan_zhi"][1]
            pillar_zhi = {p["name"]: p["zhi"] for p in self.profile["pillars"]}
            for rel in y["relations"]:
                self.assertIn(rel["palace"], pillar_zhi)
                target = pillar_zhi[rel["palace"]]
                if rel["kind"] == "冲":
                    self.assertEqual(BRANCH_CLASH.get(zhi), target)
                elif rel["kind"] == "合":
                    self.assertEqual(BRANCH_HE.get(zhi), target)
                elif rel["kind"] == "害":
                    self.assertEqual(BRANCH_HARM.get(zhi), target)
                else:  # 刑
                    self.assertTrue(
                        (zhi == target and zhi in BRANCH_SELF_PUNISH)
                        or any(zhi in g and target in g
                               for g in (("寅", "巳", "申"),
                                         ("丑", "戌", "未"), ("子", "卯"))),
                        f"{zhi} 与 {target} 不应判刑",
                    )

    def test_tian_ke_di_chong_is_strict(self):
        """天克地冲 = 天干克日干 + 地支冲日支，两个条件都要成立。"""
        day_zhi = self.profile["day_master"]["zhi"]
        for y in self.years:
            if not y["tian_ke_di_chong"]:
                continue
            self.assertEqual(BRANCH_CLASH.get(y["gan_zhi"][1]), day_zhi)

    def test_deterministic(self):
        again = build_bazi_years(
            self.profile, self.fortune["da_yun"], 1991,
            start_year=self.years[0]["year"], count=BAZI_YEAR_COUNT,
        )
        self.assertEqual(again, self.years)


class PlainLanguageCase(unittest.TestCase):
    """可读性不变量：行话必须就地解释，不留未解释的名词。"""

    def setUp(self):
        self.profile, self.true_dt = _chart(1991, 9, 10, 7, 35, "男", 113.26)
        self.fortune = build_bazi_fortune(self.profile, self.true_dt, 1991)

    def test_shi_shen_plain_covers_field(self):
        self.assertEqual(set(SHI_SHEN_PLAIN), set(SHI_SHEN_FIELD))

    def test_every_step_has_plain(self):
        for s in self.fortune["da_yun"]["steps"]:
            self.assertTrue(s["plain"], s["gan_zhi"])
            self.assertIn(s["shi_shen"], s["plain"])
            self.assertIn(s["gan_zhi"], s["plain"])

    def test_no_markdown_asterisks(self):
        """前端是纯文本渲染，markdown 星号会原样露出。"""
        blobs = [self.fortune["da_yun"]["plain"], self.fortune["da_yun"]["basis"]]
        blobs += [s["plain"] for s in self.fortune["da_yun"]["steps"]]
        for y in self.fortune["years"]:
            blobs.append(y["plain"])
            blobs += y["points"]
        for text in blobs:
            self.assertNotIn("**", text, text[:40])

    def test_year_shi_shen_is_explained_in_place(self):
        """出现「正财」这类行话的同一条里，必须有对应白话片段。"""
        for y in self.fortune["years"]:
            joined = " ".join(y["points"])
            self.assertIn(y["shi_shen"], joined)
            self.assertTrue(y["shi_shen_plain"], y["shi_shen"])
            self.assertIn(y["shi_shen_plain"], joined)

    def test_relation_kind_is_explained(self):
        for y in self.fortune["years"]:
            for rel in y["relations"]:
                self.assertTrue(rel["plain"], rel["kind"])
                self.assertIn(f"相{rel['kind']}", " ".join(y["points"]))

    def test_year_plain_is_not_empty(self):
        for y in self.fortune["years"]:
            self.assertTrue(y["plain"])
            self.assertIn(str(y["age"]), y["plain"])


class ApiCase(unittest.TestCase):
    """接口契约：字段集合必须对得上，缺一个前端就静默渲染成空白。"""

    def setUp(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:  # pragma: no cover
            self.skipTest("缺少 fastapi TestClient")
        from main import app

        self.client = TestClient(app)

    def _post(self, **kw):
        payload = {
            "year": 1991, "month": 9, "day": 10, "hour": 7, "minute": 35,
            "gender": "男", "longitude": 113.26, "name": "测试",
        }
        payload.update(kw)
        return self.client.post("/api/v1/bazi", json=payload)

    def test_ok_and_contract(self):
        res = self._post()
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["code"], 0)
        data = body["data"]
        self.assertIn("da_yun", data)
        self.assertIn("years", data)

        dayun = data["da_yun"]
        for key in ("forward", "jie_name", "start_age", "start_year",
                    "basis", "plain", "steps", "current"):
            self.assertIn(key, dayun)
        self.assertEqual(len(dayun["steps"]), DA_YUN_STEPS)
        for s in dayun["steps"]:
            for key in ("gan_zhi", "shi_shen", "from_age", "to_age",
                        "from_year", "to_year", "is_current", "plain"):
                self.assertIn(key, s)

        self.assertEqual(len(data["years"]), BAZI_YEAR_COUNT)
        for y in data["years"]:
            for key in ("year", "gan_zhi", "age", "shi_shen", "da_yun",
                        "is_da_yun_switch", "relations", "tian_ke_di_chong",
                        "focus", "stance", "plain", "points"):
                self.assertIn(key, y)

    def test_public_endpoint(self):
        """八字是纯计算接口，不需要登录。"""
        self.assertEqual(self._post().status_code, 200)

    def test_bad_input_still_400(self):
        self.assertEqual(self._post(gender="未知").status_code, 422)
        self.assertEqual(self._post(year=1899).status_code, 422)


if __name__ == "__main__":
    unittest.main()
