# -*- coding: utf-8 -*-
"""黄历接口的契约测试。

黄历是纯计算接口（不落库、不要求登录），因此这里重点验证三件事：
1. 五个端点的响应结构稳定——客户端据此解析，字段改名等于破坏契约；
2. 入参校验落在正确的状态码上：用户入参问题 400，schema 越界 422；
3. 无 token 可用（与 /bazi、/bazhai 同口径），而不是误挂到鉴权后面。

运行：python -m unittest tests.test_almanac_api -v
依赖 httpx（fastapi.testclient 需要）；未安装时自动跳过整个模块。
"""

import datetime as dt
import unittest

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover
    TestClient = None  # type: ignore[assignment]

import main
from app.engine.constants import ALMANAC_ACTIVITIES, ALMANAC_RULES_VERSION

FIXED = "2026-10-14"


@unittest.skipIf(TestClient is None, "需要 httpx 才能跑接口测试")
class AlmanacApiCase(unittest.TestCase):
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


class TestTodayAndDay(AlmanacApiCase):
    def test_today_returns_full_almanac(self):
        data = self._data(self.client.get("/api/v1/almanac/today"))
        today = dt.date.today()
        self.assertEqual(data["date"], today.isoformat())
        self.assertEqual(data["weekday_index"], today.weekday())
        self.assertEqual(data["rules_version"], ALMANAC_RULES_VERSION)

        for key in (
            "lunar", "gan_zhi", "xun", "jian_chu", "tian_shen", "xiu", "chong",
            "peng_zu", "five_gods", "hours", "lucky_hours", "unlucky_hours",
            "purple_white", "yi", "ji", "ji_shen", "xiong_sha", "score_reasons",
        ):
            self.assertIn(key, data)
        self.assertIsInstance(data["yi"], list)
        self.assertIsInstance(data["ji"], list)
        self.assertGreaterEqual(len(data["hours"]), 12)
        self.assertEqual(len(data["five_gods"]), 5)
        self.assertGreaterEqual(data["score"], 0)
        self.assertLessEqual(data["score"], 100)

    def test_today_equals_day_without_param(self):
        via_today = self._data(self.client.get("/api/v1/almanac/today"))
        via_day = self._data(self.client.get("/api/v1/almanac/day"))
        self.assertEqual(via_today, via_day)

    def test_day_with_explicit_date(self):
        data = self._data(self.client.get("/api/v1/almanac/day", params={"date": FIXED}))
        self.assertEqual(data["date"], FIXED)
        self.assertEqual(data["weekday"], "周三")
        self.assertEqual(data["lunar"]["text"], "二〇二六年九月初五")
        self.assertEqual(data["jian_chu"]["name"], "闭")
        self.assertEqual(data["jian_chu"]["tone"], "大凶")
        self.assertEqual(data["tian_shen"]["name"], "天德")
        self.assertEqual(data["xiu"]["full"], "轸水蚓")
        self.assertEqual(data["chong"]["zodiac"], "兔")
        self.assertEqual(len(data["hours"]), 13)

    def test_day_is_deterministic(self):
        first = self._data(self.client.get("/api/v1/almanac/day", params={"date": FIXED}))
        second = self._data(self.client.get("/api/v1/almanac/day", params={"date": FIXED}))
        self.assertEqual(first, second)

    def test_bad_date_format_returns_400(self):
        for bad in ("2026/10/14", "20261014", "2026-13-45", "今天", "2026-2-30"):
            with self.subTest(bad=bad):
                response = self.client.get("/api/v1/almanac/day", params={"date": bad})
                self.assertEqual(response.status_code, 400, response.text)


class TestActivities(AlmanacApiCase):
    def test_lists_all_activities(self):
        data = self._data(self.client.get("/api/v1/almanac/activities"))
        self.assertEqual(len(data["activities"]), len(ALMANAC_ACTIVITIES))
        for item in data["activities"]:
            self.assertTrue(item["key"])
            self.assertTrue(item["name"])
            self.assertTrue(item["terms"])
        keys = [item["key"] for item in data["activities"]]
        self.assertIn("zhuangxiu", keys)


class TestSelect(AlmanacApiCase):
    def _select(self, **overrides):
        payload = {"activity": "zhuangxiu", "start_date": "2026-11-01", "days": 30}
        payload.update(overrides)
        return self.client.post("/api/v1/almanac/select", json=payload)

    def test_returns_ranked_picks(self):
        data = self._data(self._select(limit=5, zodiac="兔"))
        self.assertEqual(data["activity"]["key"], "zhuangxiu")
        self.assertEqual(data["range"]["start"], "2026-11-01")
        self.assertEqual(data["range"]["end"], "2026-11-30")
        self.assertEqual(data["scanned"], 30)
        self.assertEqual(data["zodiac"], "兔")
        self.assertEqual(data["rules_version"], ALMANAC_RULES_VERSION)
        self.assertLessEqual(len(data["items"]), 5)
        scores = [item["score"] for item in data["items"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

        first = data["items"][0]
        for key in (
            "date", "weekday", "lunar", "gan_zhi", "jian_chu", "jian_chu_tone",
            "tian_shen", "xiu", "xiu_luck", "chong", "score", "level", "tone",
            "hits", "misses", "reasons", "clash", "lucky_hours", "best_hour",
        ):
            self.assertIn(key, first)
        self.assertTrue(first["reasons"])
        self.assertTrue(first["lucky_hours"])
        self.assertTrue(first["best_hour"])

    def test_start_date_defaults_to_today(self):
        data = self._data(
            self.client.post("/api/v1/almanac/select", json={"activity": "anchuang"})
        )
        self.assertEqual(data["range"]["start"], dt.date.today().isoformat())
        self.assertEqual(data["range"]["days"], 30)

    def test_min_score_filters(self):
        data = self._data(self._select(days=90, limit=60, min_score=85))
        for item in data["items"]:
            self.assertGreaterEqual(item["score"], 85)

    def test_every_activity_is_selectable(self):
        for item in ALMANAC_ACTIVITIES:
            with self.subTest(activity=item["key"]):
                data = self._data(
                    self.client.post(
                        "/api/v1/almanac/select",
                        json={"activity": item["key"], "start_date": "2026-11-01", "days": 60},
                    )
                )
                self.assertTrue(data["items"])

    def test_unknown_activity_returns_400(self):
        response = self._select(activity="nope")
        self.assertEqual(response.status_code, 400, response.text)

    def test_unknown_zodiac_returns_400(self):
        response = self._select(zodiac="猫")
        self.assertEqual(response.status_code, 400, response.text)

    def test_bad_start_date_returns_400(self):
        response = self._select(start_date="2026-11-31")
        self.assertEqual(response.status_code, 400, response.text)

    def test_out_of_range_params_return_422(self):
        cases = [
            {"days": 0},
            {"days": 367},
            {"limit": 0},
            {"limit": 61},
            {"min_score": -1},
            {"min_score": 101},
        ]
        for overrides in cases:
            with self.subTest(overrides=overrides):
                response = self._select(**overrides)
                self.assertEqual(response.status_code, 422, response.text)
        # 全默认入参是合法的（activity 已由 _select 带上）
        self.assertEqual(self._select().status_code, 200)
        # activity 为必填
        response = self.client.post("/api/v1/almanac/select", json={"days": 5})
        self.assertEqual(response.status_code, 422)
        # 空 activity 不合法
        response = self.client.post(
            "/api/v1/almanac/select", json={"activity": "", "days": 5}
        )
        self.assertEqual(response.status_code, 422)


class TestMonth(AlmanacApiCase):
    def test_month_overview(self):
        data = self._data(
            self.client.get(
                "/api/v1/almanac/month",
                params={"year": 2026, "month": 11, "activity": "zhuangxiu", "zodiac": "兔"},
            )
        )
        self.assertEqual(data["year"], 2026)
        self.assertEqual(data["month"], 11)
        self.assertEqual(len(data["days"]), 30)
        self.assertEqual(data["first_weekday"], dt.date(2026, 11, 1).weekday())
        self.assertEqual(data["activity"]["key"], "zhuangxiu")
        self.assertEqual(data["zodiac"], "兔")
        self.assertIsNotNone(data["best"])
        self.assertEqual(
            data["best"]["score"], max(day["score"] for day in data["days"])
        )
        for day in data["days"]:
            self.assertIn("clash", day)
            self.assertIn("lucky_hour_count", day)
        self.assertEqual(sum(1 for d in data["days"] if d["clash"]), 2)

    def test_month_without_activity(self):
        data = self._data(
            self.client.get("/api/v1/almanac/month", params={"year": 2026, "month": 2})
        )
        self.assertEqual(len(data["days"]), 28)
        self.assertIsNone(data["activity"])

    def test_leap_february(self):
        data = self._data(
            self.client.get("/api/v1/almanac/month", params={"year": 2024, "month": 2})
        )
        self.assertEqual(len(data["days"]), 29)

    def test_invalid_params(self):
        for params in (
            {"year": 2026, "month": 13},
            {"year": 2026, "month": 0},
            {"year": 1800, "month": 1},
            {"month": 1},
            {"year": 2026},
        ):
            with self.subTest(params=params):
                response = self.client.get("/api/v1/almanac/month", params=params)
                self.assertEqual(response.status_code, 422, response.text)
        # 事项 key 由引擎校验，走 400
        response = self.client.get(
            "/api/v1/almanac/month", params={"year": 2026, "month": 11, "activity": "nope"}
        )
        self.assertEqual(response.status_code, 400, response.text)


class TestPublicAccess(AlmanacApiCase):
    """黄历与排盘口径一致：公开计算接口，不需要登录。"""

    def test_no_token_required(self):
        calls = [
            ("get", "/api/v1/almanac/today", None),
            ("get", "/api/v1/almanac/day", {"params": {"date": FIXED}}),
            ("get", "/api/v1/almanac/activities", None),
            ("get", "/api/v1/almanac/month", {"params": {"year": 2026, "month": 11}}),
            ("post", "/api/v1/almanac/select", {"json": {"activity": "anchuang", "days": 3}}),
        ]
        for method, url, kwargs in calls:
            with self.subTest(url=url):
                response = getattr(self.client, method)(url, **(kwargs or {}))
                self.assertEqual(response.status_code, 200, response.text)

    def test_error_body_keeps_detail_field(self):
        """客户端靠 detail 拿中文提示，包装统一响应时不能丢。"""
        response = self.client.get("/api/v1/almanac/day", params={"date": "bad"})
        body = response.json()
        self.assertIn("detail", body)
        self.assertIn("YYYY-MM-DD", body["detail"])


if __name__ == "__main__":
    unittest.main()
