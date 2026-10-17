# -*- coding: utf-8 -*-
"""号码八星（数字能量）测试。

这个模块的可靠性完全依赖**数组表的自洽性**，所以第一组测试就是那张表：
八星各 8 组、合计 64 组，必须恰好等于 {1,2,3,4,6,7,8,9} 的全部有序两两组合，
无缺无重。这是它唯一站得住的部分，破了就等于表错了。

另外锁两件事：
* **隐私**：响应与错误文案里都不能出现完整号码。
* **性质声明**：``nature_note`` 必须存在且非空，前端不能淡化它。
"""

from __future__ import annotations

import unittest

from app.engine import analyze_number, mask_number, split_pairs, star_of_pair
from app.engine.constants import EIGHT_STARS, PHONE_KINDS, PHONE_LEVELS
from app.engine.phone_energy import _PAIR_TO_STAR

DIGITS = ("1", "2", "3", "4", "6", "7", "8", "9")


class StarTableCase(unittest.TestCase):
    """八星数组表。"""

    def test_eight_stars_eight_pairs_each(self):
        self.assertEqual(len(EIGHT_STARS), 8)
        for star, info in EIGHT_STARS.items():
            self.assertEqual(len(info["pairs"]), 8, star)
            self.assertEqual(len(set(info["pairs"])), 8, star)

    def test_table_partitions_all_64_ordered_pairs(self):
        """8 星 × 8 组 = 64 = {1,2,3,4,6,7,8,9} 的全部有序对，无缺无重。"""
        full = {f"{a}{b}" for a in DIGITS for b in DIGITS}
        self.assertEqual(len(full), 64)
        self.assertEqual(set(_PAIR_TO_STAR), full)
        self.assertEqual(len(_PAIR_TO_STAR), 64)

    def test_lookup_is_consistent_with_table(self):
        for star, info in EIGHT_STARS.items():
            for pair in info["pairs"]:
                self.assertEqual(star_of_pair(pair), star, pair)

    def test_zero_and_five_are_not_stars(self):
        """0 与 5 不参与分组（另有修饰规则）。"""
        for pair in ("05", "50", "15", "51", "45", "54", "00", "55"):
            self.assertIsNone(star_of_pair(pair), pair)

    def test_bad_input(self):
        self.assertIsNone(star_of_pair("1"))
        self.assertIsNone(star_of_pair(""))
        self.assertIsNone(star_of_pair("ab"))


class SplitCase(unittest.TestCase):
    def test_overlapping_pairs(self):
        self.assertEqual(split_pairs("138"), ["13", "38"])
        self.assertEqual(split_pairs("13812345678"),
                         ["13", "38", "81", "12", "23",
                          "34", "45", "56", "67", "78"])

    def test_short(self):
        self.assertEqual(split_pairs("13"), ["13"])
        self.assertEqual(split_pairs("1"), [])


class MaskCase(unittest.TestCase):
    """隐私：不回显完整号码。"""

    def test_mobile_keeps_first3_last4(self):
        self.assertEqual(mask_number("13812345678", "mobile"), "138****5678")

    def test_mask_never_equals_raw(self):
        for kind in PHONE_KINDS:
            masked = mask_number("13812345678", kind)
            self.assertNotEqual(masked, "13812345678")
            self.assertIn("*", masked)

    def test_short_is_fully_masked(self):
        self.assertEqual(mask_number("12", "general"), "**")

    def test_letters_and_separators_ignored(self):
        self.assertEqual(mask_number("138-1234-5678", "mobile"), "138****5678")


class AnalyzeCase(unittest.TestCase):
    def setUp(self):
        self.r = analyze_number("13812345678", "mobile")

    def test_no_raw_number_in_response(self):
        """响应里不能出现完整号码，只能有脱敏形式。"""
        blob = str(self.r)
        self.assertNotIn("13812345678", blob)
        self.assertIn("138****5678", blob)

    def test_nature_note_present(self):
        """性质声明必须存在——不能与玄空 / 八字同等权威地呈现。"""
        self.assertTrue(self.r["nature_note"])
        self.assertIn("民俗", self.r["nature_note"])

    def test_items_match_pairs(self):
        self.assertEqual(len(self.r["items"]), len(self.r["pairs"]))
        for item, pair in zip(self.r["items"], self.r["pairs"]):
            self.assertEqual(item["pair"], pair)
            self.assertEqual(item["star"], star_of_pair(pair))

    def test_distribution_sums_to_classified_pairs(self):
        classified = sum(1 for i in self.r["items"] if i["star"] is not None)
        self.assertEqual(sum(self.r["distribution"].values()), classified)

    def test_tail_is_weighted_double(self):
        tail = [i for i in self.r["items"] if i["is_tail"] and i["star"]]
        self.assertTrue(tail)
        for i in tail:
            base = __import__("app.engine.constants",
                              fromlist=["PHONE_SCORE"]).PHONE_SCORE["star"][i["star"]]
            self.assertEqual(i["score"], base * 2)

    def test_score_within_range_and_level_known(self):
        self.assertTrue(0 <= self.r["score"] <= 100)
        self.assertIn(self.r["level"], [x[1] for x in PHONE_LEVELS])

    def test_deterministic(self):
        self.assertEqual(analyze_number("13812345678", "mobile"), self.r)

    def test_zeros_and_fives_counted(self):
        # 1 3 0 0 5 0 0 5 6 7 8 -> 4 个 0、2 个 5
        r = analyze_number("13005005678", "mobile")
        self.assertEqual(r["zeros"], 4)
        self.assertEqual(r["fives"], 2)

    def test_no_markdown(self):
        for text in [self.r["plain"], self.r["advice"],
                     self.r["nature_note"], *self.r["points"]]:
            self.assertNotIn("**", text)

    def test_kinds(self):
        for kind in PHONE_KINDS:
            r = analyze_number("13812345678", kind)
            self.assertEqual(r["kind"], kind)

    def test_bad_kind(self):
        with self.assertRaises(ValueError):
            analyze_number("13812345678", "wechat")

    def test_too_short(self):
        with self.assertRaises(ValueError):
            analyze_number("1", "mobile")

    def test_too_long(self):
        with self.assertRaises(ValueError):
            analyze_number("1" * 21, "mobile")


class DistributionCase(unittest.TestCase):
    """评分分布不能退化成「全是同一档」。"""

    def test_spread_over_levels(self):
        import random
        from collections import Counter

        random.seed(7)
        counter: Counter = Counter()
        for _ in range(1500):
            n = "1" + "".join(random.choice("0123456789") for _ in range(10))
            counter[analyze_number(n, "mobile")["level"]] += 1
        # 至少覆盖四档，且没有任何一档吃掉全部
        self.assertGreaterEqual(len(counter), 4, dict(counter))
        top = counter.most_common(1)[0][1]
        self.assertLess(top, 1500 * 0.6, dict(counter))


class PhoneEnergyApiCase(unittest.TestCase):
    def setUp(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:  # pragma: no cover
            self.skipTest("缺少 fastapi TestClient")
        from main import app

        self.client = TestClient(app)

    def _post(self, **kw):
        payload = {"number": "13812345678", "kind": "mobile"}
        payload.update(kw)
        return self.client.post("/api/v1/phone-energy", json=payload)

    def test_ok(self):
        res = self._post()
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()["data"]
        self.assertEqual(data["masked"], "138****5678")
        self.assertEqual(len(data["items"]), 10)
        self.assertTrue(data["nature_note"])

    def test_no_raw_number_echoed(self):
        res = self._post()
        self.assertNotIn("13812345678", res.text)

    def test_public_endpoint(self):
        self.assertEqual(self._post().status_code, 200)

    def test_error_does_not_echo_raw(self):
        """超长号码走引擎的 ValueError -> 400，且提示里只放脱敏号码。"""
        res = self._post(number="138" + "1" * 18)
        self.assertEqual(res.status_code, 400)
        self.assertNotIn("1" * 18, res.text)
        self.assertIn("****", res.text)

    def test_bad_kind(self):
        self.assertEqual(self._post(kind="wechat").status_code, 422)

    def test_plate_ok(self):
        res = self._post(number="粤A12345", kind="plate")
        self.assertEqual(res.status_code, 200, res.text)
        # 粤A12345 -> 数字 12345（5 位），首尾各留 2 -> 12*45
        self.assertEqual(res.json()["data"]["masked"], "12*45")


if __name__ == "__main__":
    unittest.main()
