# -*- coding: utf-8 -*-
"""用户体系 + 管理后台接口的端到端测试。

用内存 SQLite 覆盖 `get_db`，完全不触碰 .env 里配置的 PostgreSQL。
运行：python -m unittest tests.test_user_admin_api -v

依赖 httpx（fastapi.testclient 需要）；未安装时自动跳过整个模块。
"""

import unittest
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.routers.auth as auth_module
from app.db import Base, get_db
from app.models import Admin, House, SmsCode, User  # noqa: F401  导入以注册表
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


def _override_get_db():
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


@unittest.skipIf(TestClient is None, "需要 httpx：pip install httpx")
class UserAdminApiTest(unittest.TestCase):
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
        """每个用例前清空数据并重建管理员。

        默认关掉发码间隔限制：多数用例需要连续走多次登录流程，
        否则会撞上 60 秒限频。限频本身的用例会临时把间隔调回去。
        """
        self._set_send_interval(0)
        db = _TestSession()
        try:
            for model in (SmsCode, House, User, Admin):
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

    def tearDown(self):
        auth_module.SMS_SEND_INTERVAL_SECONDS = self._original_interval

    def _set_send_interval(self, seconds: int) -> None:
        if not hasattr(self, "_original_interval"):
            self._original_interval = auth_module.SMS_SEND_INTERVAL_SECONDS
        auth_module.SMS_SEND_INTERVAL_SECONDS = seconds

    @contextmanager
    def _rate_limit(self, seconds: int):
        """在 with 块内临时启用发码限频。"""
        previous = auth_module.SMS_SEND_INTERVAL_SECONDS
        auth_module.SMS_SEND_INTERVAL_SECONDS = seconds
        try:
            yield
        finally:
            auth_module.SMS_SEND_INTERVAL_SECONDS = previous

    # ------------------------------------------------------------ 工具方法
    def _login(self, phone: str) -> dict:
        """走完整的发码 + 登录流程，返回 {token, user}。"""
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

    # ------------------------------------------------------------ 认证
    def test_login_creates_user_and_returns_profile(self):
        data = self._login(PHONE_A)
        self.assertTrue(data["token"])
        self.assertEqual(data["user"]["phone"], PHONE_A)
        self.assertEqual(data["user"]["status"], "active")
        # 新用户自动注册，昵称用手机号后四位兜底
        self.assertIn(PHONE_A[-4:], data["user"]["nickname"])

        me = self.client.get("/api/v1/auth/me", headers=self._auth(data["token"]))
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["data"]["id"], data["user"]["id"])

    def test_same_phone_second_login_reuses_account(self):
        first = self._login(PHONE_A)
        second = self._login(PHONE_A)
        self.assertEqual(first["user"]["id"], second["user"]["id"])
        self.assertEqual(second["user"]["login_count"], 2)

    def test_send_code_is_rate_limited(self):
        with self._rate_limit(60):
            ok = self.client.post("/api/v1/auth/send-code", json={"phone": PHONE_A})
            self.assertEqual(ok.status_code, 200)

            again = self.client.post("/api/v1/auth/send-code", json={"phone": PHONE_A})
            self.assertEqual(again.status_code, 429)

    def test_wrong_code_is_rejected(self):
        self.client.post("/api/v1/auth/send-code", json={"phone": PHONE_A})
        resp = self.client.post(
            "/api/v1/auth/login", json={"phone": PHONE_A, "code": "000000"}
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("验证码", resp.json()["message"])

    def test_invalid_phone_rejected(self):
        resp = self.client.post("/api/v1/auth/send-code", json={"phone": "12345"})
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 422)

    def test_me_requires_token(self):
        resp = self.client.get("/api/v1/auth/me")
        self.assertEqual(resp.status_code, 401)

    # ------------------------------------------------------------ 房屋归属隔离
    def test_houses_are_isolated_between_users(self):
        user_a = self._login(PHONE_A)
        user_b = self._login(PHONE_B)

        created = self.client.post(
            "/api/v1/houses",
            json={"name": "A 的房子", "layout": "3室2厅", "area": 96},
            headers=self._auth(user_a["token"]),
        )
        self.assertEqual(created.status_code, 200, created.text)
        house_id = created.json()["data"]["id"]

        # A 能看到，B 看不到
        list_a = self.client.get("/api/v1/houses", headers=self._auth(user_a["token"]))
        self.assertEqual(list_a.json()["data"]["total"], 1)

        list_b = self.client.get("/api/v1/houses", headers=self._auth(user_b["token"]))
        self.assertEqual(list_b.json()["data"]["total"], 0)

        # B 直接按 id 取 A 的房子 → 404，不泄露存在性
        stolen = self.client.get(
            f"/api/v1/houses/{house_id}", headers=self._auth(user_b["token"])
        )
        self.assertEqual(stolen.status_code, 404)

    # ------------------------------------------------------------ 管理后台
    def test_admin_token_is_separate_from_app_token(self):
        user = self._login(PHONE_A)
        # App 端 token 打后台接口必须被拒
        resp = self.client.get("/api/v1/admin/users", headers=self._auth(user["token"]))
        self.assertEqual(resp.status_code, 401)

        # 反过来，管理员 token 也不能当 App 用户用
        admin_token = self._admin_login()
        resp = self.client.get("/api/v1/auth/me", headers=self._auth(admin_token))
        self.assertEqual(resp.status_code, 401)

    def test_admin_login_rejects_wrong_password(self):
        resp = self.client.post(
            "/api/v1/admin/login",
            json={"username": ADMIN_USERNAME, "password": "wrong-password"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_admin_can_list_search_and_ban_user(self):
        user = self._login(PHONE_A)
        token = self._admin_login()

        listing = self.client.get("/api/v1/admin/users", headers=self._auth(token))
        self.assertEqual(listing.status_code, 200)
        body = listing.json()["data"]
        self.assertEqual(body["page_meta"]["total"], 1)
        self.assertEqual(body["items"][0]["phone"], PHONE_A)
        self.assertEqual(body["items"][0]["house_count"], 0)

        # 关键字搜索命中
        hit = self.client.get(
            "/api/v1/admin/users",
            params={"keyword": PHONE_A[-4:]},
            headers=self._auth(token),
        )
        self.assertEqual(hit.json()["data"]["page_meta"]["total"], 1)

        miss = self.client.get(
            "/api/v1/admin/users",
            params={"keyword": "13900000000"},
            headers=self._auth(token),
        )
        self.assertEqual(miss.json()["data"]["page_meta"]["total"], 0)

        # 封禁
        banned = self.client.patch(
            f"/api/v1/admin/users/{user['user']['id']}/status",
            json={"status": "banned", "reason": "测试封禁"},
            headers=self._auth(token),
        )
        self.assertEqual(banned.status_code, 200, banned.text)
        self.assertEqual(banned.json()["data"]["status"], "banned")
        self.assertEqual(banned.json()["data"]["ban_reason"], "测试封禁")

        # 被封用户即使拿到正确验证码也不能登录
        sent = self.client.post("/api/v1/auth/send-code", json={"phone": PHONE_A})
        code = sent.json()["data"]["debug_code"]
        login = self.client.post(
            "/api/v1/auth/login", json={"phone": PHONE_A, "code": code}
        )
        self.assertEqual(login.status_code, 403)

        # 解封后恢复
        unbanned = self.client.patch(
            f"/api/v1/admin/users/{user['user']['id']}/status",
            json={"status": "active", "reason": ""},
            headers=self._auth(token),
        )
        self.assertEqual(unbanned.json()["data"]["status"], "active")
        self.assertEqual(unbanned.json()["data"]["ban_reason"], "")

    def test_admin_user_detail_includes_houses(self):
        user = self._login(PHONE_A)
        self.client.post(
            "/api/v1/houses",
            json={"name": "阳光房", "layout": "2室1厅", "area": 78},
            headers=self._auth(user["token"]),
        )
        token = self._admin_login()

        detail = self.client.get(
            f"/api/v1/admin/users/{user['user']['id']}", headers=self._auth(token)
        )
        self.assertEqual(detail.status_code, 200)
        data = detail.json()["data"]
        self.assertEqual(data["user"]["phone"], PHONE_A)
        self.assertEqual(len(data["houses"]), 1)
        self.assertEqual(data["houses"][0]["name"], "阳光房")

        # 列表里的房屋数也应同步
        listing = self.client.get("/api/v1/admin/users", headers=self._auth(token))
        self.assertEqual(listing.json()["data"]["items"][0]["house_count"], 1)

    def test_delete_user_keeps_houses_by_default(self):
        user = self._login(PHONE_A)
        self.client.post(
            "/api/v1/houses",
            json={"name": "待保留房屋"},
            headers=self._auth(user["token"]),
        )
        token = self._admin_login()

        resp = self.client.delete(
            f"/api/v1/admin/users/{user['user']['id']}", headers=self._auth(token)
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["detached_houses"], 1)

        # 房屋还在，但已无归属
        houses = self.client.get("/api/v1/admin/houses", headers=self._auth(token))
        items = houses.json()["data"]["items"]
        self.assertEqual(len(items), 1)
        self.assertIsNone(items[0]["owner_id"])

    def test_admin_stats(self):
        self._login(PHONE_A)
        self._login(PHONE_B)
        token = self._admin_login()

        resp = self.client.get("/api/v1/admin/stats", headers=self._auth(token))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]

        self.assertEqual(data["total_users"], 2)
        self.assertEqual(data["new_today"], 2)
        self.assertEqual(data["new_7d"], 2)
        self.assertEqual(data["active_7d"], 2)
        self.assertEqual(data["banned_users"], 0)
        # 14 个数据点，最后一个是今天
        self.assertEqual(len(data["trend"]), 14)
        self.assertEqual(data["trend"][-1]["new_users"], 2)


if __name__ == "__main__":
    unittest.main()
