# -*- coding: utf-8 -*-
"""合婚配对测试。

锁三类东西：
1. **地支关系表与生肖口诀对得上**——六合 / 六冲 / 六害 / 三合 / 自刑逐对核对，
   且必须与八字、玄空**共用同一份常量**（不另建一套）。
2. **立春分界**——1、2 月出生的人不能按元旦算生肖。
3. **可读性不变量**——行话就地解释、无 markdown 星号、不断定论。
"""

from __future__ import annotations

import unittest

from app.engine import (
    branch_relation_of,
    build_match,
    bazi_match,
    san_he_of,
    zodiac_branch_of,
    zodiac_match,
)
from app.engine.constants import (
    BRANCH_CLASH,
    BRANCH_HARM,
    BRANCH_HE,
    BRANCH_SAN_HE,
    BRANCH_SELF_PUNISH,
    EARTHLY_BRANCHES,
    MARRIAGE_LEVELS,
    STEM_CLASH,
    STEM_HE,
    STEM_HE_ELEMENT,
    ZODIACS,
)
from app.engine.marriage import ZODIAC_BY_BRANCH

B = EARTHLY_BRANCHES


class ZodiacBranchCase(unittest.TestCase):
    """生肖取年支，一律按立春分界。"""

    def test_zodiac_table_matches_branches(self):
        self.assertEqual(ZODIAC_BY_BRANCH["子"], "鼠")
        self.assertEqual(ZODIAC_BY_BRANCH["亥"], "猪")
        self.assertEqual(len(ZODIACS), 12)

    def test_known_years(self):
        # 1990 庚午马、1991 辛未羊、1996 丙子鼠、1984 甲子鼠、1993 癸酉鸡
        for year, zodiac in ((1990, "马"), (1991, "羊"), (1996, "鼠"),
                             (1984, "鼠"), (1993, "鸡"), (2000, "龙")):
            self.assertEqual(zodiac_branch_of(year)[0], zodiac, year)

    def test_lichun_boundary_shifts_one_year(self):
        """立春前出生算上一年：1990-02-01 尚未立春 -> 蛇（1989 己巳）。"""
        before = zodiac_branch_of(1990, 2, 1)
        after = zodiac_branch_of(1990, 2, 10)
        self.assertEqual(before[0], "蛇")
        self.assertEqual(after[0], "马")
        self.assertEqual(before[2], 1989)
        self.assertEqual(after[2], 1990)

    def test_year_only_no_correction(self):
        """只给年份时不做修正（与 bazhai.lichun_year 同口径）。"""
        self.assertEqual(zodiac_branch_of(1990)[2], 1990)


class RelationCase(unittest.TestCase):
    """地支 / 天干关系表。"""

    def test_liu_he_matches_the_rhyme(self):
        """六合：鼠牛、虎猪、兔狗、龙鸡、蛇猴、马羊。"""
        expect = {"子丑", "寅亥", "卯戌", "辰酉", "巳申", "午未"}
        got = {"".join(sorted((a, b))) for a, b in BRANCH_HE.items()}
        # 排序键按地支序，保证集合比较不含顺序
        norm = {min(p, key=B.index) + max(p, key=B.index) for p in got}
        self.assertEqual(norm, expect)

    def test_liu_chong(self):
        """六冲：鼠马、牛羊、虎猴、兔鸡、龙狗、蛇猪。"""
        expect = {"子午", "丑未", "寅申", "卯酉", "辰戌", "巳亥"}
        got = {min((a, b), key=B.index) + max((a, b), key=B.index)
               for a, b in BRANCH_CLASH.items()}
        self.assertEqual(got, expect)

    def test_liu_hai(self):
        """六害：鼠羊、牛马、虎蛇、兔龙、猴猪、鸡狗。"""
        expect = {"子未", "丑午", "寅巳", "卯辰", "申亥", "酉戌"}
        got = {min((a, b), key=B.index) + max((a, b), key=B.index)
               for a, b in BRANCH_HARM.items()}
        self.assertEqual(got, expect)

    def test_san_he_groups(self):
        """三合局：申子辰水、亥卯未木、寅午戌火、巳酉丑金。"""
        table = {frozenset(g["branches"]): g["element"] for g in BRANCH_SAN_HE}
        self.assertEqual(table[frozenset(("申", "子", "辰"))], "水")
        self.assertEqual(table[frozenset(("亥", "卯", "未"))], "木")
        self.assertEqual(table[frozenset(("寅", "午", "戌"))], "火")
        self.assertEqual(table[frozenset(("巳", "酉", "丑"))], "金")

    def test_san_he_only_two_is_not_full(self):
        """只有两支只能算半合，不能谎称成局。"""
        rel = san_he_of("申", "子")
        self.assertIsNotNone(rel)
        self.assertFalse(rel["is_full"])
        self.assertIsNone(san_he_of("子", "午"))

    def test_self_punish(self):
        """自刑：辰午酉亥 —— 龙、马、鸡、猪。"""
        self.assertEqual(set(BRANCH_SELF_PUNISH), {"辰", "午", "酉", "亥"})
        self.assertEqual(branch_relation_of("午", "午")["key"], "自刑")

    def test_clash_outranks_everything(self):
        for a, b in BRANCH_CLASH.items():
            self.assertEqual(branch_relation_of(a, b)["key"], "六冲", f"{a}{b}")

    def test_stem_he_and_element(self):
        """天干五合：甲己土、乙庚金、丙辛水、丁壬木、戊癸火。"""
        for a, b in STEM_HE.items():
            key = "".join(sorted((a, b), key="甲乙丙丁戊己庚辛壬癸".index))
            self.assertIn(key, STEM_HE_ELEMENT)

    def test_stem_clash(self):
        self.assertEqual(STEM_CLASH["甲"], "庚")
        self.assertEqual(STEM_CLASH["庚"], "甲")
        self.assertNotIn("戊", STEM_CLASH)  # 戊己居中央，无冲


class ZodiacMatchCase(unittest.TestCase):
    """生肖合婚。"""

    def test_liu_he_scores_high(self):
        r = zodiac_match(1990, 1991)  # 马配羊，午未六合
        self.assertEqual(r["items"][0]["relation"], "六合")
        self.assertGreater(r["score"], 60)

    def test_clash_scores_low(self):
        r = zodiac_match(1990, 1996)  # 马配鼠，子午冲
        self.assertEqual(r["items"][0]["relation"], "六冲")
        self.assertLess(r["score"], 40)

    def test_score_within_range(self):
        for a in range(1960, 2010, 7):
            for b in range(1960, 2010, 7):
                r = zodiac_match(a, b)
                self.assertTrue(0 <= r["score"] <= 100, f"{a}{b}")
                self.assertIn(r["level"], [x[1] for x in MARRIAGE_LEVELS])

    def test_all_144_pairs_have_plain(self):
        for x in B:
            for y in B:
                rel = branch_relation_of(x, y)
                self.assertTrue(rel["plain"], f"{x}{y}")
                self.assertIn(rel["level"], ("旺", "平", "煞", "大凶"))

    def test_no_markdown_asterisks(self):
        for a in range(1970, 2000, 5):
            for b in range(1970, 2000, 5):
                r = zodiac_match(a, b)
                for text in [r["plain"], r["advice"], *r["points"]]:
                    self.assertNotIn("**", text)

    def test_plain_names_both_zodiacs(self):
        r = zodiac_match(1990, 1991)
        self.assertIn("马", r["plain"])
        self.assertIn("羊", r["plain"])


class BaziMatchCase(unittest.TestCase):
    """八字合婚。"""

    A = {"year": 1991, "month": 9, "day": 10, "hour": 7, "minute": 35,
         "gender": "男", "longitude": 113.26}
    B = {"year": 1993, "month": 3, "day": 5, "hour": 14, "minute": 0,
         "gender": "女", "longitude": 116.4}

    def _match(self):
        return build_match("bazi", a=self.A, b=self.B)

    def test_four_items(self):
        r = self._match()
        self.assertEqual([i["key"] for i in r["items"]],
                         ["year", "day_stem", "day_branch", "yong"])

    def test_parties_carried(self):
        r = self._match()
        self.assertEqual(r["a"]["zodiac"], "羊")
        self.assertEqual(r["b"]["zodiac"], "鸡")
        self.assertTrue(r["a"]["day_pillar"])
        self.assertTrue(r["a"]["favorable"])

    def test_score_within_range(self):
        r = self._match()
        self.assertTrue(0 <= r["score"] <= 100)
        self.assertTrue(r["level"] and r["level_key"])

    def test_deterministic(self):
        self.assertEqual(self._match(), self._match())

    def test_no_markdown(self):
        r = self._match()
        for i in r["items"]:
            self.assertNotIn("**", i["plain"])
        for text in [r["plain"], r["advice"], *r["points"]]:
            self.assertNotIn("**", text)

    def test_relation_keys_are_known(self):
        known = {"三合", "六合", "六冲", "六害", "相刑", "自刑", "半合",
                 "同支", "无合冲", "天干五合", "天干相冲", "互补",
                 "不互补", "不足"}
        r = self._match()
        for i in r["items"]:
            self.assertIn(i["relation"], known, i["key"])

    def test_bazi_match_direct(self):
        from app.engine import build_bazi

        a = build_bazi(**{k: v for k, v in self.A.items() if k != "minute"})
        b = build_bazi(**{k: v for k, v in self.B.items() if k != "minute"})
        r = bazi_match(a, b, self.A, self.B)
        self.assertEqual(r["mode"], "bazi")


class DispatchCase(unittest.TestCase):
    def test_zodiac_mode_uses_years(self):
        r = build_match("zodiac", a_year=1990, b_year=1991)
        self.assertEqual(r["mode"], "zodiac")

    def test_bazi_requires_parties(self):
        with self.assertRaises(ValueError):
            build_match("bazi")

    def test_bazi_requires_full_info(self):
        with self.assertRaises(ValueError):
            build_match("bazi", a={"year": 1990}, b={"year": 1991})

    def test_bad_mode(self):
        with self.assertRaises(ValueError):
            build_match("tarot", a_year=1990, b_year=1991)


class MarriageApiCase(unittest.TestCase):
    def setUp(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:  # pragma: no cover
            self.skipTest("缺少 fastapi TestClient")
        from main import app

        self.client = TestClient(app)

    def _post(self, **kw):
        payload = {
            "mode": "zodiac",
            "a": {"year": 1990, "month": 6, "day": 1},
            "b": {"year": 1991, "month": 6, "day": 1},
        }
        payload.update(kw)
        return self.client.post("/api/v1/marriage", json=payload)

    def test_zodiac_ok(self):
        res = self._post()
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()["data"]
        self.assertEqual(data["a"]["zodiac"], "马")
        self.assertEqual(data["b"]["zodiac"], "羊")
        self.assertEqual(len(data["items"]), 1)
        self.assertTrue(data["plain"] and data["advice"])

    def test_bazi_ok(self):
        res = self._post(
            mode="bazi",
            a={"year": 1991, "month": 9, "day": 10, "hour": 7, "minute": 35,
               "gender": "男", "longitude": 113.26},
            b={"year": 1993, "month": 3, "day": 5, "hour": 14, "minute": 0,
               "gender": "女", "longitude": 116.4},
        )
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()["data"]
        self.assertEqual(len(data["items"]), 4)
        self.assertTrue(data["points"])

    def test_public_endpoint(self):
        self.assertEqual(self._post().status_code, 200)

    def test_bad_mode(self):
        self.assertEqual(self._post(mode="tarot").status_code, 422)

    def test_bad_gender(self):
        res = self._post(
            mode="bazi",
            a={"year": 1991, "month": 9, "day": 10, "hour": 7, "gender": "未知"},
            b={"year": 1993, "month": 3, "day": 5, "hour": 14, "gender": "女"},
        )
        self.assertEqual(res.status_code, 422)

    def test_bazi_missing_field_400(self):
        """MarriageParty 只有 year 必填，缺 hour 之类要由引擎的 ValueError 兜住 -> 400。"""
        res = self._post(mode="bazi", a={"year": 1991}, b={"year": 1993})
        self.assertEqual(res.status_code, 400)
        self.assertIn("出生月日不完整", res.json()["detail"])


if __name__ == "__main__":
    unittest.main()
