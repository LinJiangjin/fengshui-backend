# -*- coding: utf-8 -*-
"""命理档案接口测试：录入落库、覆盖更新、跨用户隔离、后台可见。

用内存 SQLite 覆盖 `get_db`，完全不触碰 .env 里配置的数据库。
运行：python -m unittest tests.test_bazi_profile_api -v

依赖 httpx（fastapi.testclient 需要）；未安装时自动跳过整个模块。
"""

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.models import Admin, BaziProfile, House, SmsCode, User  # noqa: F401
from app.security import hash_password
from app.utils import new_id

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover
    TestClient = None  # type: ignore[assignment]

import main

# 内存库 + StaticPool：多个 session 共享同一个内存数据库
_test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSession = sessionmaker(
    bind=_test_engine, autoflush=False, autocommit=False, expire_on_commit=False
)

ADMIN_USERNAME = "test_admin"
ADMIN_PASSWORD = "admin123456"

PHONE_A = "13800000001"
PHONE_B = "13800000002"

# 广州：东经 113.26，真太阳时校正用得上
BIRTH_A = {
    "year": 1991,
    "month": 9,
    "day": 10,
    "hour": 7,
    "minute": 35,
    "gender": "男",
    "longitude": 113.26,
    "name": "阿甲",
    "province": "广东",
    "city": "广州",
}


def _override_get_db():
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


@unittest.skipIf(TestClient is None, "需要 httpx：pip install httpx")
class BaziProfileApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=_test_engine)
        main.app.dependency_overrides[get_db] = _override_get_db
        cls.client = TestClient(main.app)

    @classmethod
    def tearDownClass(cls):
        main.app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(bind=_test_engine)
        _test_engine.dispose()

    def setUp(self):
        """每个用例前清空数据并重建管理员。"""
        db = _TestSession()
        try:
            for model in (SmsCode, House, BaziProfile, User, Admin):
                db.query(model).delete()
            db.add(
                Admin(
                    id=new_id("adm"),
                    username=ADMIN_USERNAME,
                    password_hash=hash_password(ADMIN_PASSWORD),
                    display_name="测试管理员",
                    status="active",
                )
            )
            db.commit()
        finally:
            db.close()

    # ------------------------------------------------------------ 工具方法
    def _login(self, phone: str) -> dict:
        sent = self.client.post("/api/v1/auth/send-code", json={"phone": phone})
        self.assertEqual(sent.status_code, 200, sent.text)
        code = sent.json()["data"]["debug_code"]
        resp = self.client.post(
            "/api/v1/auth/login", json={"phone": phone, "code": code}
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()["data"]

    def _admin_login(self) -> str:
        resp = self.client.post(
            "/api/v1/admin/login",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()["data"]["token"]

    @staticmethod
    def _auth(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def _save(self, token: str, **overrides):
        payload = dict(BIRTH_A)
        payload.update(overrides)
        return self.client.put(
            "/api/v1/bazi/profile", json=payload, headers=self._auth(token)
        )

    def _count(self) -> int:
        db = _TestSession()
        try:
            return db.query(BaziProfile).count()
        finally:
            db.close()

    # ------------------------------------------------------------ 鉴权
    def test_profile_requires_login(self):
        self.assertEqual(self.client.get("/api/v1/bazi/profile").status_code, 401)
        self.assertEqual(
            self.client.put("/api/v1/bazi/profile", json=BIRTH_A).status_code, 401
        )

    # ------------------------------------------------------------ 读取 / 保存
    def test_get_returns_null_before_any_save(self):
        token = self._login(PHONE_A)["token"]
        resp = self.client.get("/api/v1/bazi/profile", headers=self._auth(token))
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertIsNone(resp.json()["data"])

    def test_save_then_get_returns_recorded_birth_info(self):
        token = self._login(PHONE_A)["token"]

        saved = self._save(token)
        self.assertEqual(saved.status_code, 200, saved.text)
        data = saved.json()["data"]
        self.assertTrue(data["id"].startswith("bazi_"))
        self.assertEqual(data["year"], 1991)
        self.assertEqual(data["hour"], 7)
        self.assertEqual(data["minute"], 35)
        self.assertEqual(data["gender"], "男")
        self.assertEqual(data["longitude"], 113.26)
        self.assertEqual(data["province"], "广东")
        self.assertEqual(data["city"], "广州")
        # 四柱摘要由排盘引擎算出，供后台一眼查看
        self.assertTrue(data["pillars"], data)

        got = self.client.get("/api/v1/bazi/profile", headers=self._auth(token))
        self.assertEqual(got.status_code, 200, got.text)
        self.assertEqual(got.json()["data"]["id"], data["id"])

    def test_resave_overwrites_same_record(self):
        """重新录入是修改同一份档案，不能在库里堆出多条。"""
        token = self._login(PHONE_A)["token"]

        first = self._save(token).json()["data"]
        second = self._save(
            token, day=11, hour=9, longitude=116.41, province="北京", city="东城"
        ).json()["data"]

        self.assertEqual(first["id"], second["id"])
        self.assertEqual(second["day"], 11)
        self.assertEqual(second["longitude"], 116.41)
        self.assertEqual(self._count(), 1)

    def test_profile_is_isolated_between_users(self):
        token_a = self._login(PHONE_A)["token"]
        token_b = self._login(PHONE_B)["token"]

        self._save(token_a)

        got_b = self.client.get("/api/v1/bazi/profile", headers=self._auth(token_b))
        self.assertEqual(got_b.status_code, 200, got_b.text)
        self.assertIsNone(got_b.json()["data"])

        # B 保存自己的档案，不影响 A
        saved_b = self._save(token_b, name="阿乙", gender="女").json()["data"]
        got_a = self.client.get("/api/v1/bazi/profile", headers=self._auth(token_a))
        self.assertEqual(got_a.json()["data"]["name"], "阿甲")
        self.assertNotEqual(got_a.json()["data"]["id"], saved_b["id"])

    def test_delete_clears_profile(self):
        token = self._login(PHONE_A)["token"]
        self._save(token)

        resp = self.client.delete("/api/v1/bazi/profile", headers=self._auth(token))
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertTrue(resp.json()["data"]["deleted"])
        self.assertEqual(self._count(), 0)

        again = self.client.delete("/api/v1/bazi/profile", headers=self._auth(token))
        self.assertFalse(again.json()["data"]["deleted"])

    def test_invalid_longitude_is_rejected(self):
        token = self._login(PHONE_A)["token"]
        resp = self._save(token, longitude=60)
        self.assertEqual(resp.status_code, 422, resp.text)

    # ------------------------------------------------------------ 管理后台
    def test_admin_lists_profiles_with_owner(self):
        token = self._login(PHONE_A)["token"]
        self._save(token)
        admin_token = self._admin_login()

        resp = self.client.get(
            "/api/v1/admin/bazi-profiles", headers=self._auth(admin_token)
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()["data"]
        self.assertEqual(data["page_meta"]["total"], 1)

        item = data["items"][0]
        self.assertEqual(item["owner_phone"], PHONE_A)
        self.assertEqual(item["city"], "广州")
        self.assertEqual(item["pillars"], self._save(token).json()["data"]["pillars"])

    def test_admin_list_supports_keyword_and_gender_filter(self):
        token_a = self._login(PHONE_A)["token"]
        token_b = self._login(PHONE_B)["token"]
        self._save(token_a)  # 阿甲 / 男
        self._save(token_b, name="阿乙", gender="女")
        admin_token = self._admin_login()

        by_keyword = self.client.get(
            "/api/v1/admin/bazi-profiles",
            params={"keyword": "阿乙"},
            headers=self._auth(admin_token),
        ).json()["data"]
        self.assertEqual(by_keyword["page_meta"]["total"], 1)
        self.assertEqual(by_keyword["items"][0]["name"], "阿乙")

        by_phone = self.client.get(
            "/api/v1/admin/bazi-profiles",
            params={"keyword": PHONE_A},
            headers=self._auth(admin_token),
        ).json()["data"]
        self.assertEqual(by_phone["page_meta"]["total"], 1)
        self.assertEqual(by_phone["items"][0]["owner_phone"], PHONE_A)

        by_gender = self.client.get(
            "/api/v1/admin/bazi-profiles",
            params={"gender": "女"},
            headers=self._auth(admin_token),
        ).json()["data"]
        self.assertEqual(by_gender["page_meta"]["total"], 1)
        self.assertEqual(by_gender["items"][0]["gender"], "女")

        bad = self.client.get(
            "/api/v1/admin/bazi-profiles",
            params={"gender": "未知"},
            headers=self._auth(admin_token),
        )
        self.assertEqual(bad.status_code, 422, bad.text)

    def test_admin_list_rejects_user_token(self):
        token = self._login(PHONE_A)["token"]
        resp = self.client.get(
            "/api/v1/admin/bazi-profiles", headers=self._auth(token)
        )
        self.assertEqual(resp.status_code, 401, resp.text)

    def test_admin_can_delete_profile(self):
        token = self._login(PHONE_A)["token"]
        profile_id = self._save(token).json()["data"]["id"]
        admin_token = self._admin_login()

        resp = self.client.delete(
            f"/api/v1/admin/bazi-profiles/{profile_id}",
            headers=self._auth(admin_token),
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(self._count(), 0)

        missing = self.client.delete(
            f"/api/v1/admin/bazi-profiles/{profile_id}",
            headers=self._auth(admin_token),
        )
        self.assertEqual(missing.status_code, 404, missing.text)


if __name__ == "__main__":
    unittest.main()
