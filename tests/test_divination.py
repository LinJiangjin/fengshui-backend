# -*- coding: utf-8 -*-
"""六爻纳甲 / 梅花易数测试。

重心在两件事：
1. **八宫卦序与卦名表互为校验**——算法生成 64 个爻型，名表给 64 个卦名，
   两边必须对得上，任何一边错了都会在这里暴露。
2. **装卦每一项都能手工验算**——纳甲、六亲、六神、世应、旺衰都不是
   「写死一张表」，而是从歌诀推出来的，所以每一项都要能被独立算一遍。
"""

from __future__ import annotations

import datetime as dt
import unittest

from app.engine import build_divination, hexagram_of, liuyao_chart, meihua_chart
from app.engine.constants import (
    DIVINATION_TOPICS,
    GUA64,
    LIU_QIN_BY_RELATION,
    LIU_SHEN_ORDER,
    LIU_SHEN_START,
    NA_JIA_GAN,
    NA_JIA_ZHI,
    TRIGRAM_BITS,
    TRIGRAM_GUA_INFO,
    XIAN_TIAN_NUM,
)
from app.engine.divination import GUA_TABLE, _relation_of, _wang_xiang_of

WHEN = dt.datetime(2026, 10, 17, 9, 30)


class GuaTableCase(unittest.TestCase):
    """八宫与六十四卦名。"""

    def test_table_covers_all_64_patterns(self):
        self.assertEqual(len(GUA_TABLE), 64)
        self.assertEqual(len({tuple(k) for k in GUA_TABLE}), 64)

    def test_names_match_the_constant_table(self):
        inv = {bits: name for name, bits in TRIGRAM_BITS.items()}
        for lines, meta in GUA_TABLE.items():
            lower = inv[tuple(lines[0:3])]
            upper = inv[tuple(lines[3:6])]
            self.assertEqual(meta["name"], GUA64[(upper, lower)],
                             f"{lines} 的卦名对不上")

    def test_all_64_names_are_unique(self):
        names = [m["name"] for m in GUA_TABLE.values()]
        self.assertEqual(len(set(names)), 64)

    def test_pure_hexagrams_are_themselves(self):
        """八纯卦：上下同卦，世在六爻，宫即本卦。"""
        for name, bits in TRIGRAM_BITS.items():
            meta = hexagram_of(list(bits) + list(bits))
            self.assertEqual(meta["palace"], name)
            self.assertEqual(meta["order"], "本宫")
            self.assertEqual(meta["shi"], 5)
            self.assertEqual(meta["ying"], 2)

    def test_dry_palace_sequence(self):
        """乾宫八变：与《京房八宫》传统卦序逐卦核对。"""
        expect = ["乾为天", "天风姤", "天山遁", "天地否",
                  "风地观", "山地剥", "火地晋", "火天大有"]
        got = []
        for lines, meta in GUA_TABLE.items():
            if meta["palace"] == "乾":
                got.append((meta["order"], meta["name"]))
        order = ["本宫", "一世", "二世", "三世", "四世", "五世", "游魂", "归魂"]
        got.sort(key=lambda item: order.index(item[0]))
        self.assertEqual([n for _, n in got], expect)

    def test_every_palace_has_eight(self):
        counts: dict[str, int] = {}
        for meta in GUA_TABLE.values():
            counts[meta["palace"]] = counts.get(meta["palace"], 0) + 1
        self.assertEqual(counts, {p: 8 for p in TRIGRAM_BITS})

    def test_shi_ying_are_three_apart(self):
        for meta in GUA_TABLE.values():
            self.assertEqual(meta["ying"], (meta["shi"] + 3) % 6)

    def test_shi_index_by_order(self):
        """世爻位置随卦序而定：本宫六、一二三四五世随序、游魂四、归魂三。"""
        expect = {"本宫": 5, "一世": 0, "二世": 1, "三世": 2,
                  "四世": 3, "五世": 4, "游魂": 3, "归魂": 2}
        for meta in GUA_TABLE.values():
            self.assertEqual(meta["shi"], expect[meta["order"]], meta["name"])

    def test_palace_element_is_trigram_element(self):
        for meta in GUA_TABLE.values():
            self.assertEqual(meta["element"],
                             TRIGRAM_GUA_INFO[meta["palace"]]["element"])


class ConstantCollisionCase(unittest.TestCase):
    """常量同名覆盖的护栏。

    constants.py 里已有一个 ``TRIGRAM_INFO``（八宅 / 玄空 / 罗盘在用，带
    ``luoshu``）。占卜那份若也叫同名，会**整块覆盖**掉它，让八宅与玄空
    大面积 KeyError。这里把这条陷阱钉住。
    """

    def test_existing_trigram_info_keeps_luoshu(self):
        from app.engine.constants import TRIGRAM_INFO

        for gua in TRIGRAM_BITS:
            self.assertIn("luoshu", TRIGRAM_INFO[gua], gua)

    def test_divination_uses_its_own_table(self):
        from app.engine.constants import TRIGRAM_GUA_INFO

        self.assertNotIn("luoshu", TRIGRAM_GUA_INFO["乾"])
        self.assertEqual(TRIGRAM_GUA_INFO["乾"]["symbol"], "☰")


class ZhuangGuaCase(unittest.TestCase):
    """装卦：纳甲、六亲、六神、世应、动爻。"""

    def setUp(self):
        # 水泽节：上坎下兑，坎宫一世
        self.chart = liuyao_chart([7, 9, 8, 6, 7, 8], when=WHEN, topic="财运")
        self.rows = self.chart["lines"]

    def test_hexagram(self):
        self.assertEqual(self.chart["ben"]["name"], "水泽节")
        self.assertEqual(self.chart["ben"]["palace"], "坎")
        self.assertEqual(self.chart["ben"]["order"], "一世")

    def test_na_jia_matches_the_mnemonic(self):
        """纳甲歌：兑金丁巳外丁亥、坎水戊寅外戊申（阴卦逆行、阳卦顺行）。"""
        expect = ["丁巳", "丁卯", "丁丑", "戊申", "戊戌", "戊子"]
        self.assertEqual([r["pillar"] for r in self.rows], expect)
        # 逐爻核对来源：内兑取丁 + 兑的内卦三支，外坎取戊 + 坎的外卦三支
        for i, r in enumerate(self.rows):
            is_upper = i >= 3
            tri = "坎" if is_upper else "兑"
            self.assertEqual(r["gan"], NA_JIA_GAN[tri][1 if is_upper else 0])
            self.assertEqual(r["zhi"], NA_JIA_ZHI[tri][1 if is_upper else 0][i % 3])

    def test_liu_qin_derived_from_palace_element(self):
        """六亲以卦宫五行为「我」：坎宫属水。"""
        expect = ["妻财", "子孙", "官鬼", "父母", "官鬼", "兄弟"]
        self.assertEqual([r["liu_qin"] for r in self.rows], expect)
        for r in self.rows:
            self.assertEqual(
                r["liu_qin"],
                LIU_QIN_BY_RELATION[_relation_of(r["element"], "水")],
                r["pillar"],
            )

    def test_liu_shen_start_from_day_gan(self):
        """六神按日干起：甲日起青龙，自初爻往上顺排。"""
        self.assertEqual(self.chart["day"]["day_gan"], "甲")
        start = LIU_SHEN_ORDER.index(LIU_SHEN_START["甲"])
        for i, r in enumerate(self.rows):
            self.assertEqual(r["liu_shen"], LIU_SHEN_ORDER[(start + i) % 6])

    def test_shi_and_ying(self):
        self.assertEqual(self.rows[0]["is_shi"], True)
        self.assertEqual(self.rows[3]["is_ying"], True)
        self.assertEqual(sum(1 for r in self.rows if r["is_shi"]), 1)
        self.assertEqual(sum(1 for r in self.rows if r["is_ying"]), 1)

    def test_moving_lines_and_changed_hexagram(self):
        """老阳(9) 变阴、老阴(6) 变阳；少阳少阴不变。"""
        self.assertEqual(self.chart["moving"], ["二爻", "四爻"])
        self.assertEqual(self.chart["bian"]["name"], "泽雷随")
        for r in self.rows:
            self.assertEqual(r["is_moving"], r["value"] in (6, 9), r["position"])

    def test_wang_xiang_against_month_zhi(self):
        """戌月属土：土旺、金相、火休、木囚、水死。"""
        self.assertEqual(self.chart["day"]["month_zhi"], "戌")
        expect = ["休", "囚", "旺", "相", "旺", "死"]
        self.assertEqual([r["wang_xiang"] for r in self.rows], expect)
        for r in self.rows:
            self.assertEqual(r["wang_xiang"], _wang_xiang_of(r["element"], "戌")[0])

    def test_yong_shen_follows_topic(self):
        self.assertEqual(self.chart["yong"]["name"], "妻财")
        self.assertEqual(self.chart["yong"]["positions"], ["初爻"])
        self.assertTrue(self.chart["yong"]["on_hexagram"])

    def test_female_love_uses_guan_gui(self):
        """女问感情取官鬼，男问取妻财。"""
        male = liuyao_chart([7, 9, 8, 6, 7, 8], when=WHEN,
                            topic="感情", gender="男")
        female = liuyao_chart([7, 9, 8, 6, 7, 8], when=WHEN,
                              topic="感情", gender="女")
        self.assertEqual(male["yong"]["name"], "妻财")
        self.assertEqual(female["yong"]["name"], "官鬼")

    def test_no_moving_lines_has_no_bian(self):
        static = liuyao_chart([7, 8, 8, 7, 7, 8], when=WHEN, topic="决策")
        self.assertIsNone(static["bian"])
        self.assertEqual(static["moving"], [])

    def test_topic_known(self):
        for topic in DIVINATION_TOPICS:
            chart = liuyao_chart([7, 9, 8, 6, 7, 8], when=WHEN, topic=topic)
            self.assertEqual(chart["topic"], topic)


class LiuYaoContractCase(unittest.TestCase):
    """入参校验与可读性。"""

    def test_bad_lines(self):
        for bad in ([7] * 5, [7] * 7, [1, 2, 3, 4, 5, 6]):
            with self.assertRaises(ValueError):
                liuyao_chart(bad, when=WHEN)

    def test_bad_gender(self):
        with self.assertRaises(ValueError):
            liuyao_chart([7, 8, 8, 7, 7, 8], when=WHEN, gender="未知")

    def test_deterministic(self):
        a = liuyao_chart([7, 9, 8, 6, 7, 8], when=WHEN, topic="财运")
        b = liuyao_chart([7, 9, 8, 6, 7, 8], when=WHEN, topic="财运")
        self.assertEqual(a, b)

    def test_plain_and_points_not_empty(self):
        chart = liuyao_chart([7, 9, 8, 6, 7, 8], when=WHEN, topic="财运")
        self.assertTrue(chart["plain"])
        self.assertGreaterEqual(len(chart["points"]), 4)
        self.assertIn(chart["stance"], chart["plain"])

    def test_no_markdown_asterisks(self):
        for topic in DIVINATION_TOPICS:
            chart = liuyao_chart([7, 9, 8, 6, 7, 8], when=WHEN, topic=topic)
            for text in [chart["plain"], *chart["points"]]:
                self.assertNotIn("**", text)

    def test_level_in_four_tiers(self):
        for lines in ([7, 8, 8, 7, 7, 8], [6, 6, 6, 6, 6, 6], [9, 9, 9, 9, 9, 9]):
            chart = liuyao_chart(lines, when=WHEN, topic="财运")
            self.assertIn(chart["level"], ("旺", "平", "煞", "大凶"))


class MeiHuaCase(unittest.TestCase):
    """梅花易数。"""

    def test_time_qigua(self):
        """农历丙午年九月初八巳时：上卦 24%8=8 坤，下卦 30%8=6 坎，动爻 30%6=6。"""
        m = meihua_chart(when=WHEN, topic="出行")
        self.assertEqual(m["source"], "时间起卦")
        self.assertEqual(m["zhu"]["upper"], "坤")
        self.assertEqual(m["zhu"]["lower"], "坎")
        self.assertEqual(m["zhu"]["name"], "地水师")
        self.assertEqual(m["moving_index"], 6)

    def test_ti_yong_split_by_moving_line(self):
        """动爻在上卦 -> 上卦为用、下卦为体。"""
        m = meihua_chart(when=WHEN, topic="出行")
        self.assertEqual(m["ti"]["trigram"], "坎")
        self.assertEqual(m["yong"]["trigram"], "坤")
        self.assertEqual(m["relation"], "用克体")
        self.assertEqual(m["verdict"], "凶")

    def test_number_qigua(self):
        """取数 13、8：13%8=5 巽上，8%8=8 坤下，动爻取两数之和 21%6=3。"""
        m = meihua_chart(numbers=[13, 8], when=WHEN, topic="决策")
        self.assertEqual(m["source"], "数字起卦")
        self.assertEqual(m["zhu"]["upper"], "巽")
        self.assertEqual(m["zhu"]["lower"], "坤")
        self.assertEqual(m["moving_index"], 3)

    def test_number_qigua_with_explicit_moving(self):
        m = meihua_chart(numbers=[1, 1, 1], when=WHEN, topic="决策")
        self.assertEqual(m["zhu"]["upper"], "乾")
        self.assertEqual(m["zhu"]["lower"], "乾")
        self.assertEqual(m["moving_index"], 1)

    def test_hu_gua_uses_middle_four(self):
        """互卦：234 爻为下卦、345 爻为上卦。"""
        m = meihua_chart(numbers=[1, 8, 2], when=WHEN, topic="决策")
        self.assertTrue(m["hu"]["name"])
        self.assertTrue(m["hu"]["upper"] and m["hu"]["lower"])

    def test_bian_gua_flips_the_moving_line(self):
        m = meihua_chart(numbers=[1, 1, 1], when=WHEN, topic="决策")
        # 乾为天初爻动 -> 天风姤
        self.assertEqual(m["zhu"]["name"], "乾为天")
        self.assertEqual(m["bian"]["name"], "天风姤")

    def test_xian_tian_num(self):
        self.assertEqual(XIAN_TIAN_NUM,
                         {"乾": 1, "兑": 2, "离": 3, "震": 4,
                          "巽": 5, "坎": 6, "艮": 7, "坤": 8})

    def test_bad_numbers(self):
        for bad in ([1], [0, 5], [-1, 3]):
            with self.assertRaises(ValueError):
                meihua_chart(numbers=bad, when=WHEN)

    def test_all_five_relations_reachable(self):
        """五个体用关系都要能出现，否则说明映射写漏了。"""
        seen = set()
        for a in range(1, 9):
            for b in range(1, 9):
                for c in range(1, 7):
                    m = meihua_chart(numbers=[a, b, c], when=WHEN, topic="决策")
                    seen.add(m["relation"])
                    self.assertIn(m["verdict"], ("大吉", "小吉", "小凶", "凶"))
        self.assertEqual(seen, {"用生体", "比和", "体克用", "体生用", "用克体"})

    def test_plain_and_basis(self):
        m = meihua_chart(when=WHEN, topic="出行")
        self.assertIn(m["zhu"]["name"], m["plain"])
        self.assertIn("除 8", m["basis"])   # 依据要能让人复核
        self.assertTrue(m["points"])


class DivinationDispatchCase(unittest.TestCase):
    def test_dispatch(self):
        self.assertEqual(build_divination("liuyao", lines=[7, 8, 8, 7, 7, 8],
                                          when=WHEN)["mode"], "liuyao")
        self.assertEqual(build_divination("meihua", numbers=[1, 1],
                                          when=WHEN)["mode"], "meihua")

    def test_liuyao_requires_lines(self):
        with self.assertRaises(ValueError):
            build_divination("liuyao", when=WHEN)

    def test_bad_mode(self):
        with self.assertRaises(ValueError):
            build_divination("tarot", lines=[7, 8, 8, 7, 7, 8], when=WHEN)


class DivinationApiCase(unittest.TestCase):
    def setUp(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:  # pragma: no cover
            self.skipTest("缺少 fastapi TestClient")
        from main import app

        self.client = TestClient(app)

    def _post(self, **kw):
        payload = {"mode": "liuyao", "lines": [7, 9, 8, 6, 7, 8],
                   "topic": "财运", "question": "今年投资如何"}
        payload.update(kw)
        return self.client.post("/api/v1/divination", json=payload)

    def test_liuyao_ok(self):
        res = self._post(when="2026-10-17 09:30")
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()["data"]
        self.assertEqual(data["ben"]["name"], "水泽节")
        self.assertEqual(len(data["lines"]), 6)
        self.assertEqual(data["moving"], ["二爻", "四爻"])
        self.assertTrue(data["plain"])

    def test_meihua_ok(self):
        res = self._post(mode="meihua", lines=None, numbers=[13, 8],
                         when="2026-10-17 09:30")
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()["data"]
        self.assertEqual(data["zhu"]["name"], "风地观")
        self.assertEqual(data["mode"], "meihua")

    def test_public_endpoint(self):
        self.assertEqual(self._post(when="2026-10-17 09:30").status_code, 200)

    def test_bad_when(self):
        self.assertEqual(self._post(when="2026/10/17 9:30").status_code, 400)

    def test_bad_lines(self):
        self.assertEqual(self._post(lines=[1, 2, 3, 4, 5, 6]).status_code, 400)

    def test_bad_mode(self):
        self.assertEqual(self._post(mode="tarot").status_code, 422)


if __name__ == "__main__":
    unittest.main()
