# -*- coding: utf-8 -*-
"""账号注销（合规）接口的端到端测试。

覆盖四个关键面：
1. 必须显式确认，误触不能注销；
2. 命理档案 / 房屋档案 / 验证码记录被物理删除；
3. 手机号被释放（可重新注册成全新账号），用户行完成匿名化；
4. 旧 token 立即失效，且后台统计与列表不再把已注销账号当活人。

运行：python -m unittest tests.test_account_delete_api -v
依赖 httpx（fastapi.testclient 需要）；未安装时自动跳过整个模块。
"""

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.routers.auth as auth_module
from app.db import Base, get_db
from app.models import Admin, BaziProfile, House, SmsCode, User  # noqa: F401
from app.security import hash_password
from app.utils import new_id

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover
    TestClient = None  # type: ignore[assignment]

import main

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

PHONE = "13800000009"
PHONE_OTHER = "13800000010"


def _override_get_db():
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


@unittest.skipIf(TestClient is None, "需要 httpx：pip install httpx")
class AccountDeleteApiTest(unittest.TestCase):
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
        """每个用例前清空业务数据并重建管理员；发码限频关掉。"""
        if not hasattr(self, "_original_interval"):
            self._original_interval = auth_module.SMS_SEND_INTERVAL_SECONDS
        auth_module.SMS_SEND_INTERVAL_SECONDS = 0

        db = _TestSession()
        try:
            for model in (SmsCode, BaziProfile, House, User, Admin):
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

    # ------------------------------------------------------------ 工具方法
    def _login(self, phone: str = PHONE) -> dict:
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

    def _seed_data(self, token: str) -> None:
        """给当前用户造一份房屋档案 + 一份命理档案（都是要随注销清掉的个人数据）。"""
        house = self.client.post(
            "/api/v1/houses",
            headers=self._auth(token),
            json={"name": "测试房", "layout": "3室2厅", "area": 96.0, "degree": 90.0},
        )
        self.assertEqual(house.status_code, 200, house.text)

        profile = self.client.put(
            "/api/v1/bazi/profile",
            headers=self._auth(token),
            json={
                "year": 1990,
                "month": 5,
                "day": 12,
                "hour": 9,
                "minute": 30,
                "gender": "男",
                "longitude": 113.26,
                "name": "测试",
                "province": "广东",
                "city": "广州",
            },
        )
        self.assertEqual(profile.status_code, 200, profile.text)

    def _delete(self, token: str, body: dict | None = None):
        return self.client.post(
            "/api/v1/auth/delete-account",
            headers=self._auth(token),
            json={"confirm": True} if body is None else body,
        )

    # ------------------------------------------------------------ 用例
    def test_delete_requires_explicit_confirm(self):
        """空 body 或 confirm=false 都不能注销——这是不可恢复的操作。"""
        data = self._login()
        token = data["token"]

        for body in ({}, {"confirm": False}):
            resp = self._delete(token, body)
            self.assertEqual(resp.status_code, 400, resp.text)
            self.assertIn("确认", resp.json()["detail"])

        # 账号应毫发无损
        me = self.client.get("/api/v1/auth/me", headers=self._auth(token))
        self.assertEqual(me.status_code, 200, me.text)

    def test_delete_purges_personal_data(self):
        """命理档案、房屋档案、验证码记录必须被物理删除。"""
        data = self._login()
        self._seed_data(data["token"])
        user_id = data["user"]["id"]

        resp = self._delete(data["token"])
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()["data"]
        self.assertTrue(payload["deleted"])
        self.assertEqual(payload["removed_houses"], 1)
        self.assertEqual(payload["removed_bazi_profiles"], 1)
        self.assertGreaterEqual(payload["removed_sms_codes"], 1)

        db = _TestSession()
        try:
            self.assertEqual(
                db.query(House).filter(House.owner_id == user_id).count(), 0
            )
            self.assertEqual(
                db.query(BaziProfile).filter(BaziProfile.owner_id == user_id).count(),
                0,
            )
            self.assertEqual(
                db.query(SmsCode).filter(SmsCode.phone == PHONE).count(), 0
            )
        finally:
            db.close()

    def test_deleted_user_row_is_anonymized(self):
        """用户行保留但已匿名化：手机号、昵称、头像都不可回溯。"""
        data = self._login()
        user_id = data["user"]["id"]
        self._delete(data["token"])

        db = _TestSession()
        try:
            row = db.get(User, user_id)
            self.assertIsNotNone(row, "用户行应保留以维持统计连续性")
            self.assertEqual(row.status, "deleted")
            self.assertNotEqual(row.phone, PHONE)
            self.assertTrue(row.phone.startswith("del-"))
            self.assertLessEqual(len(row.phone), 20, "不能超出 phone 列长度上限")
            self.assertEqual(row.nickname, "")
            self.assertEqual(row.avatar, "")
        finally:
            db.close()

    def test_phone_is_released_for_new_registration(self):
        """注销后同一手机号能重新注册成全新账号，且不继承任何历史数据。"""
        first = self._login()
        old_id = first["user"]["id"]
        self._seed_data(first["token"])
        self._delete(first["token"])

        second = self._login()
        self.assertNotEqual(second["user"]["id"], old_id)
        self.assertEqual(second["user"]["phone"], PHONE)
        self.assertEqual(second["user"]["status"], "active")

        houses = self.client.get(
            "/api/v1/houses", headers=self._auth(second["token"])
        )
        self.assertEqual(houses.status_code, 200, houses.text)
        self.assertEqual(houses.json()["data"]["items"], [])

    def test_old_token_is_rejected_after_delete(self):
        """注销后旧 token 立刻失效，且提示是「已注销」而非「被封禁」。"""
        data = self._login()
        token = data["token"]
        self._delete(token)

        me = self.client.get("/api/v1/auth/me", headers=self._auth(token))
        self.assertEqual(me.status_code, 403, me.text)
        self.assertIn("注销", me.json()["detail"])

    def test_admin_stats_excludes_deleted_accounts(self):
        """看板不再把已注销账号算成用户。"""
        self._login(PHONE)
        gone = self._login(PHONE_OTHER)
        self._delete(gone["token"])

        admin = self._admin_login()
        stats = self.client.get("/api/v1/admin/stats", headers=self._auth(admin))
        self.assertEqual(stats.status_code, 200, stats.text)
        self.assertEqual(stats.json()["data"]["total_users"], 1)

    def test_admin_user_list_hides_deleted_by_default(self):
        """用户列表默认过滤已注销；显式查 deleted 才可见，且手机号已匿名化。"""
        self._login(PHONE)
        gone = self._login(PHONE_OTHER)
        self._delete(gone["token"])

        admin = self._admin_login()

        default = self.client.get("/api/v1/admin/users", headers=self._auth(admin))
        self.assertEqual(default.status_code, 200, default.text)
        phones = [item["phone"] for item in default.json()["data"]["items"]]
        self.assertIn(PHONE, phones)
        self.assertNotIn(PHONE_OTHER, phones)

        only_deleted = self.client.get(
            "/api/v1/admin/users?status=deleted", headers=self._auth(admin)
        )
        self.assertEqual(only_deleted.status_code, 200, only_deleted.text)
        items = only_deleted.json()["data"]["items"]
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0]["phone"].startswith("del-"))


@unittest.skipIf(TestClient is None, "需要 httpx：pip install httpx")
class LegalDocApiTest(unittest.TestCase):
    """合规文档接口：登录页的两条链接依赖它。"""

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

    def test_list_documents(self):
        resp = self.client.get("/api/v1/legal/documents")
        self.assertEqual(resp.status_code, 200, resp.text)
        items = resp.json()["data"]["items"]
        slugs = [item["slug"] for item in items]
        self.assertEqual(slugs, ["user-agreement", "privacy-policy"])
        for item in items:
            self.assertTrue(item["title"])
            self.assertTrue(item["version"])
            self.assertTrue(item["updated_at"])

    def test_get_document_returns_sections(self):
        for slug in ("user-agreement", "privacy-policy"):
            resp = self.client.get(f"/api/v1/legal/{slug}")
            self.assertEqual(resp.status_code, 200, resp.text)
            data = resp.json()["data"]
            self.assertEqual(data["slug"], slug)
            self.assertGreater(len(data["sections"]), 0)
            for section in data["sections"]:
                self.assertTrue(section["heading"])
                self.assertGreater(len(section["paragraphs"]), 0)

    def test_privacy_policy_covers_statutory_topics(self):
        """隐私政策必须说到收集范围、用户权利与注销删除，否则过不了审核。"""
        resp = self.client.get("/api/v1/legal/privacy-policy")
        text = resp.json()["data"]
        joined = "".join(
            section["heading"] + "".join(section["paragraphs"])
            for section in text["sections"]
        )
        for keyword in ("手机号", "出生", "房屋", "注销", "删除", "未成年人"):
            self.assertIn(keyword, joined, f"隐私政策缺少「{keyword}」相关说明")

    def test_unknown_slug_returns_404(self):
        resp = self.client.get("/api/v1/legal/not-a-real-doc")
        self.assertEqual(resp.status_code, 404, resp.text)


if __name__ == "__main__":
    unittest.main()
