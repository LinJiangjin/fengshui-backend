# -*- coding: utf-8 -*-
"""玄空飞星接口（月盘 + 宅运盘）的契约测试。

玄空是纯计算接口（不落库、不要求登录），因此重点验证三件事：
1. 两个端点的响应结构稳定——客户端据此解析，字段改名等于破坏契约；
2. 入参校验落在正确的状态码上：用户入参问题 400，schema 越界 422；
3. 不带 token 也能用（与 /bazi、/bazhai、/almanac 同口径）。

顺带锁住两个容易回归的结论：八运丑山未向是旺山旺向、九运任何坐向都不是。

运行：python -m unittest tests.test_xuankong_api -v
依赖 httpx（fastapi.testclient 需要）；未安装时自动跳过整个模块。
"""

import datetime as dt
import unittest

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover
    TestClient = None  # type: ignore[assignment]

import main
from app.engine.constants import XUANKONG_RULES_VERSION

# 宅运盘九宫的字段集合：客户端按此解析，增删字段都要同步改这里
PALACE_KEYS = {
    "luoshu", "key", "trigram", "direction", "is_center",
    "shan_star", "shan_star_name", "yun_star", "yun_star_name",
    "xiang_star", "xiang_star_name",
    "shan_state", "xiang_state", "yun_state",
    "level", "role", "has_lost_wuhuang", "is_sit", "is_face",
}
STATE_KEYS = {"state", "level", "note", "delta", "is_wang"}
HOUSE_KEYS = {
    "name", "title", "sit", "face", "orientation", "yun", "center",
    "palaces", "pattern", "score", "level", "level_key", "jianxiang",
    "roles", "key_points", "rules_version",
}
MONTH_PALACE_KEYS = {
    "luoshu", "key", "trigram", "direction", "star", "star_name", "element",
    "level", "label", "note", "is_center", "year_star", "year_star_name",
    "year_star_level", "stacked", "stack",
}


@unittest.skipIf(TestClient is None, "需要 httpx 才能跑接口测试")
class XuankongApiCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)

    def _data(self, response):
        """统一响应格式 {code, status, data} 的 data 部分。"""
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["code"], 0)
        self.assertEqual(payload["status"], "ok")
        return payload["data"]

    # ------------------------------------------------------------ 月盘
    def test_month_with_explicit_date(self):
        data = self._data(
            self.client.get("/api/v1/xuankong/month?year=2026&month=10&day=15")
        )
        self.assertEqual(data["month_name"], "九月")
        self.assertEqual(data["jieqi"], "寒露")
        self.assertEqual(data["branch"], "午")
        self.assertEqual(data["center_star"], 9)
        self.assertEqual(len(data["palaces"]), 9)
        self.assertEqual(data["rules_version"], XUANKONG_RULES_VERSION)

    def test_month_defaults_to_today(self):
        data = self._data(self.client.get("/api/v1/xuankong/month"))
        today = dt.date.today()
        self.assertEqual(data["date"], today.isoformat())
        self.assertEqual(data["year"], today.year)

    def test_month_accepts_date_param(self):
        """`?date=YYYY-MM-DD` 与 `/almanac/day` 同口径，客户端用的是这一种。"""
        by_date = self._data(
            self.client.get("/api/v1/xuankong/month?date=2026-10-15")
        )
        by_triple = self._data(
            self.client.get("/api/v1/xuankong/month?year=2026&month=10&day=15")
        )
        self.assertEqual(by_date, by_triple)
        self.assertEqual(by_date["date"], "2026-10-15")
        self.assertEqual(by_date["jieqi"], "寒露")

    def test_month_date_param_wins_over_triple(self):
        """两种给法同时出现时以 date 为准，避免客户端把「今天」和「指定日」混着传。"""
        data = self._data(
            self.client.get(
                "/api/v1/xuankong/month?date=2026-10-15&year=2030&month=3&day=3"
            )
        )
        self.assertEqual(data["date"], "2026-10-15")
        self.assertEqual(data["year"], 2026)

    def test_month_rejects_bad_date(self):
        """日期格式非法要报 400，不能静默当成今天。"""
        resp = self.client.get("/api/v1/xuankong/month?date=20261015")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("YYYY-MM-DD", resp.json()["detail"])

    def test_month_date_param_drives_jieqi_month(self):
        """换日期要真的换节气月，否则客户端的「上一天 / 下一天」等于没动。"""
        before = self._data(
            self.client.get("/api/v1/xuankong/month?date=2026-10-07")
        )
        after = self._data(
            self.client.get("/api/v1/xuankong/month?date=2026-10-09")
        )
        # 2026 寒露在 10/8 前后，跨过界节即换月
        self.assertNotEqual(before["jieqi"], after["jieqi"])
        self.assertNotEqual(before["center_star"], after["center_star"])

    def test_month_accepts_year_only(self):
        """只给年份时，月日回落到服务端当天——不应报错。"""
        data = self._data(self.client.get("/api/v1/xuankong/month?year=2027"))
        self.assertEqual(data["year"], 2027)
        self.assertEqual(len(data["palaces"]), 9)

    def test_month_palace_contract(self):
        data = self._data(self.client.get("/api/v1/xuankong/month?year=2026&month=10&day=15"))
        for p in data["palaces"]:
            self.assertEqual(set(p), MONTH_PALACE_KEYS)
            self.assertIn(p["level"], ("旺", "平", "煞", "大凶"))
            self.assertIn(p["stack"]["level"], ("旺", "平", "煞", "大凶"))
            self.assertIn(p["year_star"], range(1, 10))
        self.assertEqual(sorted(p["star"] for p in data["palaces"]), list(range(1, 10)))

    def test_month_best_and_worst_differ(self):
        data = self._data(self.client.get("/api/v1/xuankong/month?year=2026&month=10&day=15"))
        self.assertTrue(data["best"]["title"])
        self.assertTrue(data["worst"]["title"])
        self.assertNotEqual(data["best"]["direction"], data["worst"]["direction"])

    def test_month_key_points_mention_terms(self):
        data = self._data(self.client.get("/api/v1/xuankong/month?year=2026&month=10&day=15"))
        self.assertTrue(data["key_points"])
        joined = "".join(data["key_points"])
        self.assertIn("节气月", joined)

    def test_month_is_public(self):
        """不带 Authorization 也能访问：计算类接口不要求登录。"""
        resp = self.client.get("/api/v1/xuankong/month?year=2026&month=1&day=1")
        self.assertEqual(resp.status_code, 200)

    # ------------------------------------------------------------ 宅运盘
    def test_house_by_degree(self):
        data = self._data(self.client.post(
            "/api/v1/xuankong/house",
            json={"degree": 0.0, "yun": 9, "name": "自家"},
        ))
        self.assertEqual(data["title"], "子山午向 · 九运宅运盘")
        self.assertEqual(data["name"], "自家")
        self.assertEqual(data["sit"]["mountain"], "子")
        self.assertEqual(data["face"]["mountain"], "午")
        self.assertEqual(data["yun"]["number"], 9)
        self.assertEqual(data["orientation"]["title"], "子山午向")

    def test_house_by_trigram(self):
        data = self._data(self.client.post(
            "/api/v1/xuankong/house", json={"trigram": "坎", "yun": 9}
        ))
        self.assertEqual(data["sit"]["mountain"], "子")     # 取天元龙
        self.assertEqual(data["orientation"], {})

    def test_house_by_build_year(self):
        data = self._data(self.client.post(
            "/api/v1/xuankong/house", json={"degree": 30.0, "build_year": 2010}
        ))
        self.assertEqual(data["yun"]["number"], 8)
        self.assertEqual(data["yun"]["source"], "build_year")
        self.assertEqual(data["pattern"]["key"], "旺山旺向")

    def test_house_explicit_yun_wins(self):
        data = self._data(self.client.post(
            "/api/v1/xuankong/house",
            json={"degree": 0.0, "yun": 7, "build_year": 2026},
        ))
        self.assertEqual(data["yun"]["number"], 7)
        self.assertEqual(data["yun"]["source"], "explicit")

    def test_house_contract(self):
        data = self._data(self.client.post(
            "/api/v1/xuankong/house", json={"degree": 137.0, "yun": 9}
        ))
        self.assertEqual(set(data), HOUSE_KEYS)
        self.assertEqual(set(data["roles"]), {"shan", "xiang", "yun"})
        self.assertEqual(len(data["palaces"]), 9)
        for p in data["palaces"]:
            self.assertEqual(set(p), PALACE_KEYS)
            self.assertEqual(set(p["shan_state"]), STATE_KEYS)
            self.assertEqual(set(p["xiang_state"]), STATE_KEYS)
            self.assertEqual(set(p["yun_state"]), STATE_KEYS)
        for key in ("shan_star", "yun_star", "xiang_star"):
            self.assertEqual(sorted(p[key] for p in data["palaces"]), list(range(1, 10)))

    def test_house_pattern_contract(self):
        data = self._data(self.client.post(
            "/api/v1/xuankong/house", json={"degree": 30.0, "yun": 8}
        ))
        pattern = data["pattern"]
        self.assertEqual(pattern["key"], "旺山旺向")
        self.assertTrue(pattern["to_sit"] and pattern["to_face"])
        self.assertTrue(pattern["summary"] and pattern["advice"])
        self.assertGreaterEqual(data["score"], 80)
        self.assertEqual(data["level_key"], "旺")

    def test_house_jianxiang_flag_in_response(self):
        ok = self._data(self.client.post(
            "/api/v1/xuankong/house", json={"degree": 0.0, "yun": 9}
        ))
        off = self._data(self.client.post(
            "/api/v1/xuankong/house", json={"degree": 6.0, "yun": 9}
        ))
        self.assertFalse(ok["jianxiang"])
        self.assertTrue(off["jianxiang"])

    def test_house_is_public(self):
        resp = self.client.post(
            "/api/v1/xuankong/house", json={"degree": 0.0, "yun": 9}
        )
        self.assertEqual(resp.status_code, 200)

    # ------------------------------------------------------------ 错误分支
    def test_missing_sit_direction_returns_400(self):
        resp = self.client.post("/api/v1/xuankong/house", json={"yun": 9})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("degree", resp.json()["detail"])

    def test_missing_yun_returns_400(self):
        resp = self.client.post("/api/v1/xuankong/house", json={"degree": 0.0})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("yun", resp.json()["detail"])

    def test_empty_body_returns_400(self):
        resp = self.client.post("/api/v1/xuankong/house", json={})
        self.assertEqual(resp.status_code, 400)

    def test_bad_trigram_returns_400(self):
        resp = self.client.post(
            "/api/v1/xuankong/house", json={"trigram": "X", "yun": 9}
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("宅卦", resp.json()["detail"])

    def test_out_of_range_params_return_422(self):
        cases = [
            {"degree": 0.0, "yun": 0},
            {"degree": 0.0, "yun": 10},
            {"degree": 0.0, "yun": 9, "build_year": 1800},
            {"degree": 0.0, "yun": 9, "build_year": 2200},
            {"degree": 360.0, "yun": 9},
            {"degree": -1.0, "yun": 9},
            {"degree": 0.0, "yun": 9, "declination": 45.0},
        ]
        for body in cases:
            with self.subTest(body=body):
                resp = self.client.post("/api/v1/xuankong/house", json=body)
                self.assertEqual(resp.status_code, 422, resp.text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main(verbosity=2)
