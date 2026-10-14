# -*- coding: utf-8 -*-
"""装修方案库：落库读取 + 后台 CRUD 的端到端测试。

用内存 SQLite 覆盖 `get_db`，完全不触碰 .env 里配置的 PostgreSQL。
运行：python -m unittest tests.test_library_admin_api -v

依赖 httpx（fastapi.testclient 需要）；未安装时自动跳过整个模块。
"""

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.routers.auth as auth_module
from app.db import Base, get_db
from app.models import (  # noqa: F401  导入以注册表
    Admin,
    BaziProfile,
    ElementNote,
    House,
    Scheme,
    SmsCode,
    User,
)
from app.security import hash_password
from app.seed_library import SEED_SCHEMES, seed_library
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
PHONE_A = "13800000001"

# App 端 /api/v1/library 返回的单条方案应有的键。
# 写死在这里是为了防止以后改后端时，不小心把 App 依赖的字段改掉。
APP_SCHEME_KEYS = {
    "id",
    "title",
    "subtitle",
    "tag",
    "element",
    "area",
    "from",
    "to",
    "summary",
    "highlights",
    "colors",
    "rooms",
    "element_note",
}


def _override_get_db():
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


def _payload(**overrides) -> dict:
    """一份合法的方案入参，用例只覆盖自己关心的字段。"""
    data = {
        "title": "测试方案 · 一室一厅",
        "subtitle": "五行属火 · 60㎡",
        "tag": "现代简约",
        "element": "火",
        "area": 60,
        "from_color": "#FAF0E6",
        "to_color": "#C2A06B",
        "summary": "用于测试的方案摘要。",
        "highlights": ["亮点一", "亮点二"],
        "colors": [{"name": "米白", "hex": "#FAF0E6"}],
        "rooms": [{"name": "客厅", "hex": "#FAF0E6", "note": "浅米白墙面"}],
        "published": True,
        "sort_order": 100,
    }
    data.update(overrides)
    return data


@unittest.skipIf(TestClient is None, "需要 httpx：pip install httpx")
class LibraryAdminApiTest(unittest.TestCase):
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
        """清空数据 → 重建管理员 → 写入方案库初始内容。

        发码间隔直接关掉，方便用例里随意走登录流程。
        """
        self._set_send_interval(0)
        db = _TestSession()
        try:
            for model in (SmsCode, ElementNote, Scheme, House, BaziProfile, User, Admin):
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
            seed_library(db)
        finally:
            db.close()

    def tearDown(self):
        auth_module.SMS_SEND_INTERVAL_SECONDS = self._original_interval

    def _set_send_interval(self, seconds: int) -> None:
        if not hasattr(self, "_original_interval"):
            self._original_interval = auth_module.SMS_SEND_INTERVAL_SECONDS
        auth_module.SMS_SEND_INTERVAL_SECONDS = seconds

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

    def _public_library(self, month: int = 0) -> dict:
        resp = self.client.get("/api/v1/library", params={"month": month})
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()["data"]

    def _public_ids(self) -> list[str]:
        return [s["id"] for s in self._public_library()["schemes"]]

    def _admin_list(self, token: str, **params) -> dict:
        resp = self.client.get(
            "/api/v1/admin/schemes", params=params, headers=self._auth(token)
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()["data"]

    def _admin_create(self, token: str, body: dict) -> dict:
        resp = self.client.post(
            "/api/v1/admin/schemes", json=body, headers=self._auth(token)
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()["data"]

    # ------------------------------------------------------------ 初始化
    def test_seed_populates_public_library(self):
        data = self._public_library()

        self.assertEqual(len(data["schemes"]), len(SEED_SCHEMES))
        # 老版本的 slug 保持不变，已分享出去的链接不会失效
        self.assertEqual(data["schemes"][0]["id"], SEED_SCHEMES[0]["id"])

        # 每条方案都必须是 App 端约定的字段集合，不多也不少
        for scheme in data["schemes"]:
            self.assertEqual(set(scheme.keys()), APP_SCHEME_KEYS)

        # 色值键名从库里的 from_color / to_color 映射回 from / to
        first = data["schemes"][0]
        self.assertEqual(first["from"], SEED_SCHEMES[0]["from_color"])
        self.assertEqual(first["to"], SEED_SCHEMES[0]["to_color"])

        # 风格 chips 按实际方案推导，且首项固定是「全部」
        self.assertEqual(data["filters"][0], "全部")
        self.assertIn("新中式", data["filters"])
        self.assertIn("日式侘寂", data["filters"])
        # 五行按出现顺序去重
        self.assertEqual(data["elements"], ["木", "土", "金"])

        # 五行解读按方案所属五行复用
        wood = next(s for s in data["schemes"] if s["element"] == "木")
        self.assertIn("木主生发", wood["element_note"]["fit"])
        self.assertTrue(wood["element_note"]["avoid"])

        self.assertTrue(data["palette"]["colors"])
        self.assertEqual(len(data["area_ranges"]), 4)

    def test_seed_is_idempotent_and_keeps_edits(self):
        db = _TestSession()
        try:
            # 第二次初始化不应写入任何东西
            self.assertEqual(seed_library(db), (0, 0))

            # 运营改过的文案不会被重启覆盖
            scheme = db.get(Scheme, SEED_SCHEMES[0]["id"])
            scheme.title = "运营改过的标题"
            db.commit()
            self.assertEqual(seed_library(db), (0, 0))
            db.refresh(scheme)
            self.assertEqual(scheme.title, "运营改过的标题")
        finally:
            db.close()

    # ------------------------------------------------------------ 读库
    def test_public_library_reads_from_db(self):
        db = _TestSession()
        try:
            scheme = db.get(Scheme, SEED_SCHEMES[0]["id"])
            scheme.subtitle = "改自数据库"
            db.commit()
        finally:
            db.close()

        first = self._public_library()["schemes"][0]
        self.assertEqual(first["subtitle"], "改自数据库")

    def test_public_detail_returns_scheme(self):
        scheme_id = SEED_SCHEMES[0]["id"]
        resp = self.client.get(f"/api/v1/library/{scheme_id}")
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["data"]["id"], scheme_id)

    def test_public_detail_404_for_unknown(self):
        resp = self.client.get("/api/v1/library/not-exist")
        self.assertEqual(resp.status_code, 404)

    # ------------------------------------------------------------ 后台 CRUD
    def test_create_scheme_appears_in_app(self):
        token = self._admin_login()
        created = self._admin_create(token, _payload())

        self.assertTrue(created["id"].startswith("sch_"))
        self.assertIn(created["id"], self._public_ids())

        # 新风格标签自动进入 chips，不需要再去改代码里的常量
        self.assertIn("现代简约", self._public_library()["filters"])
        # 新增的五行（火）也在筛选项里
        self.assertIn("火", self._public_library()["elements"])

        detail = self.client.get(f"/api/v1/library/{created['id']}").json()["data"]
        self.assertEqual(detail["title"], "测试方案 · 一室一厅")
        self.assertEqual(detail["colors"], [{"name": "米白", "hex": "#FAF0E6"}])

    def test_create_normalizes_whitespace_and_hex_case(self):
        token = self._admin_login()
        created = self._admin_create(
            token,
            _payload(
                title="  前后有空格  ",
                from_color="#abcdef",
                summary="  摘要  ",
                highlights=["  有空格  ", "   ", "正常"],
            ),
        )
        self.assertEqual(created["title"], "前后有空格")
        self.assertEqual(created["summary"], "摘要")
        self.assertEqual(created["from_color"], "#ABCDEF")
        # 纯空白的亮点条目被丢弃，详情页不会出现空行
        self.assertEqual(created["highlights"], ["有空格", "正常"])

    def test_unpublished_scheme_is_hidden_from_app(self):
        token = self._admin_login()
        created = self._admin_create(token, _payload(published=False))

        self.assertNotIn(created["id"], self._public_ids())
        # 详情接口对外也等同于不存在
        self.assertEqual(
            self.client.get(f"/api/v1/library/{created['id']}").status_code, 404
        )
        # 后台仍然看得到，能随时恢复
        listed = self._admin_list(token, published="draft")
        self.assertIn(created["id"], [item["id"] for item in listed["items"]])

    def test_update_scheme_reflects_in_app(self):
        token = self._admin_login()
        scheme_id = SEED_SCHEMES[0]["id"]

        resp = self.client.put(
            f"/api/v1/admin/schemes/{scheme_id}",
            json=_payload(id=scheme_id, title="改后的标题", area=123),
            headers=self._auth(token),
        )
        self.assertEqual(resp.status_code, 200, resp.text)

        detail = self.client.get(f"/api/v1/library/{scheme_id}").json()["data"]
        self.assertEqual(detail["title"], "改后的标题")
        self.assertEqual(detail["area"], 123)
        self.assertEqual(detail["tag"], "现代简约")

    def test_update_unknown_scheme_404(self):
        token = self._admin_login()
        resp = self.client.put(
            "/api/v1/admin/schemes/sch_nope",
            json=_payload(),
            headers=self._auth(token),
        )
        self.assertEqual(resp.status_code, 404)

    def test_status_toggle(self):
        token = self._admin_login()
        created = self._admin_create(token, _payload(published=False))
        scheme_id = created["id"]

        on = self.client.patch(
            f"/api/v1/admin/schemes/{scheme_id}/status",
            json={"published": True},
            headers=self._auth(token),
        )
        self.assertEqual(on.status_code, 200, on.text)
        self.assertTrue(on.json()["data"]["published"])
        self.assertIn(scheme_id, self._public_ids())

        off = self.client.patch(
            f"/api/v1/admin/schemes/{scheme_id}/status",
            json={"published": False},
            headers=self._auth(token),
        )
        self.assertEqual(off.status_code, 200, off.text)
        self.assertNotIn(scheme_id, self._public_ids())

    def test_delete_scheme(self):
        token = self._admin_login()
        scheme_id = SEED_SCHEMES[0]["id"]

        resp = self.client.delete(
            f"/api/v1/admin/schemes/{scheme_id}", headers=self._auth(token)
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertNotIn(scheme_id, self._public_ids())
        self.assertEqual(
            self.client.get(f"/api/v1/library/{scheme_id}").status_code, 404
        )

        again = self.client.delete(
            f"/api/v1/admin/schemes/{scheme_id}", headers=self._auth(token)
        )
        self.assertEqual(again.status_code, 404)

    def test_admin_detail_returns_all_fields(self):
        token = self._admin_login()
        scheme_id = SEED_SCHEMES[0]["id"]
        resp = self.client.get(
            f"/api/v1/admin/schemes/{scheme_id}", headers=self._auth(token)
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        item = resp.json()["data"]
        # 后台用库里的列名，不经过 from/to 映射
        self.assertIn("from_color", item)
        self.assertIn("to_color", item)
        self.assertIn("published", item)
        self.assertIn("sort_order", item)

    def test_admin_list_filters(self):
        token = self._admin_login()
        self._admin_create(token, _payload(published=False))

        self.assertEqual(self._admin_list(token)["page_meta"]["total"], 5)
        self.assertEqual(
            self._admin_list(token, published="published")["page_meta"]["total"], 4
        )
        self.assertEqual(
            self._admin_list(token, published="draft")["page_meta"]["total"], 1
        )
        # 五行筛选
        wood = self._admin_list(token, element="木")
        self.assertTrue(wood["items"])
        self.assertTrue(all(i["element"] == "木" for i in wood["items"]))
        # 关键词命中风格标签
        hit = self._admin_list(token, keyword="侘寂")
        self.assertEqual(hit["page_meta"]["total"], 1)

    def test_admin_list_rejects_bad_filters(self):
        token = self._admin_login()
        bad_element = self.client.get(
            "/api/v1/admin/schemes", params={"element": "雷"}, headers=self._auth(token)
        )
        self.assertEqual(bad_element.status_code, 422)

        bad_published = self.client.get(
            "/api/v1/admin/schemes",
            params={"published": "yes"},
            headers=self._auth(token),
        )
        self.assertEqual(bad_published.status_code, 422)

    # ------------------------------------------------------------ 入参校验
    def test_invalid_payload_rejected(self):
        token = self._admin_login()
        auth = self._auth(token)

        cases = {
            "色值格式不对": _payload(from_color="red"),
            "五行不在枚举内": _payload(element="雷"),
            "标题为空": _payload(title=""),
            "亮点条数超限": _payload(highlights=["x"] * 13),
            "颜色名称缺失": _payload(colors=[{"name": "", "hex": "#FFFFFF"}]),
        }
        for name, body in cases.items():
            with self.subTest(name):
                resp = self.client.post(
                    "/api/v1/admin/schemes", json=body, headers=auth
                )
                self.assertEqual(resp.status_code, 422, resp.text)
                self.assertEqual(resp.json()["code"], 422)

    # ------------------------------------------------------------ 越权
    def test_app_token_cannot_touch_admin_schemes(self):
        app_token = self._login(PHONE_A)["token"]
        auth = self._auth(app_token)

        self.assertEqual(
            self.client.get("/api/v1/admin/schemes", headers=auth).status_code, 401
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/admin/schemes", json=_payload(), headers=auth
            ).status_code,
            401,
        )
        self.assertEqual(
            self.client.delete(
                f"/api/v1/admin/schemes/{SEED_SCHEMES[0]['id']}", headers=auth
            ).status_code,
            401,
        )

    def test_admin_schemes_require_token(self):
        self.assertEqual(self.client.get("/api/v1/admin/schemes").status_code, 401)

    # ------------------------------------------------------------ 五行解读
    def test_element_note_update_reflects_in_app(self):
        token = self._admin_login()

        listed = self.client.get(
            "/api/v1/admin/element-notes", headers=self._auth(token)
        )
        self.assertEqual(listed.status_code, 200, listed.text)
        # 五行相生序：木 火 土 金 水
        self.assertEqual(
            [n["element"] for n in listed.json()["data"]], ["木", "火", "土", "金", "水"]
        )

        resp = self.client.put(
            "/api/v1/admin/element-notes/木",
            json={"fit": "改过的宜", "avoid": "改过的忌"},
            headers=self._auth(token),
        )
        self.assertEqual(resp.status_code, 200, resp.text)

        wood = next(
            s for s in self._public_library()["schemes"] if s["element"] == "木"
        )
        self.assertEqual(wood["element_note"], {"fit": "改过的宜", "avoid": "改过的忌"})

    def test_element_note_upsert_creates_missing_row(self):
        token = self._admin_login()
        db = _TestSession()
        try:
            db.query(ElementNote).filter(ElementNote.element == "水").delete()
            db.commit()
        finally:
            db.close()

        resp = self.client.put(
            "/api/v1/admin/element-notes/水",
            json={"fit": "润下", "avoid": "忌燥"},
            headers=self._auth(token),
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["data"]["sort_order"], 5)

    def test_element_note_rejects_unknown_element(self):
        token = self._admin_login()
        resp = self.client.put(
            "/api/v1/admin/element-notes/雷",
            json={"fit": "x", "avoid": "y"},
            headers=self._auth(token),
        )
        self.assertEqual(resp.status_code, 422)

    def test_scheme_without_note_returns_empty_note(self):
        """新增一行没维护解读的五行时，方案仍能正常下发，只是宜忌为空。"""
        token = self._admin_login()
        db = _TestSession()
        try:
            db.query(ElementNote).filter(ElementNote.element == "火").delete()
            db.commit()
        finally:
            db.close()

        created = self._admin_create(token, _payload(element="火"))
        detail = self.client.get(f"/api/v1/library/{created['id']}").json()["data"]
        self.assertEqual(detail["element_note"], {"fit": "", "avoid": ""})
