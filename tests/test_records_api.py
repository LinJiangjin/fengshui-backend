# -*- coding: utf-8 -*-
"""测算记录接口的契约测试。

锁四类东西：
1. **档案类边界**——必须登录（无 token 一律 401）；跨用户访问一律 404 而非 403，
   删他人记录也不暴露 id 是否存在（deleted=False）。
2. **入参校验**——kind 白名单（400）、空 params（400）、NaN（400）、
   超长 params（400）、空 title（schema 422）。
3. **同参去重**——同一份入参重复保存走更新（id 不变、不插重复行）；
   换 kind 才算另一条；列表按 updated_at 倒序。
4. **分界未破**——计算类接口（/almanac 等）仍然不要求登录，
   证明加档案路由没有顺手给纯计算接口装上鉴权。

运行：python -m unittest tests.test_records_api -v
依赖 httpx（fastapi.testclient 需要）；未安装时自动跳过整个模块。
"""

from __future__ import annotations

import unittest
import uuid

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover
    TestClient = None  # type: ignore[assignment]

import main
from app.db import Base, SessionLocal, engine
from app.models import CalcRecord, User
from app.routers.records import MAX_PARAMS_CHARS, RECORD_KINDS
from app.security import create_token

BAZI_PARAMS = {
    "year": 1990,
    "month": 5,
    "day": 20,
    "hour": 14,
    "minute": 30,
    "gender": "男",
    "longitude": 120.0,
    "name": "测试",
}


@unittest.skipIf(TestClient is None, "需要 httpx 才能跑接口测试")
class RecordsApiCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)
        # calc_records 是新增表：开发库可能还没建（服务没重启过），这里幂等补建
        Base.metadata.create_all(bind=engine)
        cls.users = {}
        cls.tokens = {}
        session = SessionLocal()
        try:
            for tag in ("owner", "other"):
                uid = f"test-rec-{tag}-{uuid.uuid4().hex[:8]}"
                # phone 列 String(20)：只需唯一且不超长，用明显非手机号的格式
                user = User(
                    id=uid,
                    phone=("u" + uuid.uuid4().hex)[:20],
                    nickname=f"记录测试-{tag}",
                )
                session.add(user)
                cls.users[tag] = user
            session.commit()
            for tag, user in cls.users.items():
                token, _ = create_token(user.id, "user")
                cls.tokens[tag] = token
        finally:
            session.close()

    @classmethod
    def tearDownClass(cls):
        session = SessionLocal()
        try:
            ids = [u.id for u in cls.users.values()]
            session.query(CalcRecord).filter(CalcRecord.owner_id.in_(ids)).delete(
                synchronize_session=False
            )
            session.query(User).filter(User.id.in_(ids)).delete(synchronize_session=False)
            session.commit()
        finally:
            session.close()

    def setUp(self):
        self._clear_records()

    def tearDown(self):
        self._clear_records()

    # ------------------------------------------------------------  helpers
    def _clear_records(self):
        session = SessionLocal()
        try:
            ids = [u.id for u in self.users.values()]
            session.query(CalcRecord).filter(CalcRecord.owner_id.in_(ids)).delete(
                synchronize_session=False
            )
            session.commit()
        finally:
            session.close()

    def _auth(self, tag: str = "owner") -> dict:
        return {"Authorization": f"Bearer {self.tokens[tag]}"}

    def _save(self, tag: str = "owner", **body) -> dict:
        res = self.client.post(
            "/api/v1/records", json=body, headers=self._auth(tag)
        )
        return self._ok(res)

    def _ok(self, res) -> dict:
        self.assertEqual(res.status_code, 200, res.text)
        payload = res.json()
        self.assertEqual(payload["code"], 0)
        self.assertEqual(payload["status"], "ok")
        return payload["data"]

    # ------------------------------------------------------------ 档案类边界
    def test_whitelist_is_deliberate(self):
        """白名单锁死：新增 kind 必须是显式决定，不能悄悄多一个。"""
        self.assertEqual(
            RECORD_KINDS,
            frozenset(
                {
                    "bazi",
                    "bazhai",
                    "xuankong",
                    "almanac",
                    "divination",
                    "marriage",
                    "diagnose",
                }
            ),
        )

    def test_unauthenticated_is_401(self):
        """无 token：保存 / 列表 / 详情 / 删除全部 401，不落到数据层。"""
        res = self.client.post(
            "/api/v1/records",
            json={"kind": "bazi", "title": "无token", "params": BAZI_PARAMS},
        )
        self.assertEqual(res.status_code, 401, res.text)
        self.assertEqual(self.client.get("/api/v1/records").status_code, 401)
        self.assertEqual(
            self.client.get("/api/v1/records/rec_nope").status_code, 401
        )
        self.assertEqual(
            self.client.delete("/api/v1/records/rec_nope").status_code, 401
        )

    def test_cross_user_is_404_not_403(self):
        """他人的记录：详情 404、删除返回 deleted=False，都不泄露存在性。"""
        saved = self._save(
            kind="bazi", title="乾造 1990-05-20", params=BAZI_PARAMS
        )
        rid = saved["id"]

        res = self.client.get(f"/api/v1/records/{rid}", headers=self._auth("other"))
        self.assertEqual(res.status_code, 404, res.text)
        self.assertEqual(res.json()["detail"], "测算记录不存在")

        res = self.client.delete(f"/api/v1/records/{rid}", headers=self._auth("other"))
        self.assertEqual(res.status_code, 200, res.text)
        self.assertFalse(res.json()["data"]["deleted"])

        # 原主仍然读得到，证明上一步真的什么都没动
        self.assertEqual(
            self._ok(
                self.client.get(f"/api/v1/records/{rid}", headers=self._auth())
            )["id"],
            rid,
        )

    # ------------------------------------------------------------ 入参校验
    def test_unknown_kind_is_400(self):
        res = self.client.post(
            "/api/v1/records",
            json={"kind": "qimen", "title": "奇门", "params": BAZI_PARAMS},
            headers=self._auth(),
        )
        self.assertEqual(res.status_code, 400, res.text)
        self.assertEqual(res.json()["detail"], "不支持的测算类型")

    def test_empty_params_is_400(self):
        res = self.client.post(
            "/api/v1/records",
            json={"kind": "bazi", "title": "空参数", "params": {}},
            headers=self._auth(),
        )
        self.assertEqual(res.status_code, 400, res.text)
        self.assertEqual(res.json()["detail"], "params 不能为空")

    def test_nan_params_is_400(self):
        """NaN 写不进 JSON 列，保存前就该挡掉，不能等到落库才炸。

        走 content= 发原始 body：httpx 的 json= 自己就拒绝序列化 NaN，
        那样请求根本到不了服务端，测不到这道防线。Python 的 json.loads
        默认放行 NaN，所以非本客户端（或构造的请求）是能把它送进来的。
        """
        headers = {**self._auth(), "Content-Type": "application/json"}
        res = self.client.post(
            "/api/v1/records",
            content='{"kind":"bazi","title":"含NaN","params":{"year":NaN}}',
            headers=headers,
        )
        self.assertEqual(res.status_code, 400, res.text)
        self.assertEqual(res.json()["detail"], "params 含非法数值（NaN 等）")

    def test_oversized_params_is_400(self):
        res = self.client.post(
            "/api/v1/records",
            json={
                "kind": "bazi",
                "title": "超大参数",
                "params": {"blob": "x" * (MAX_PARAMS_CHARS + 10)},
            },
            headers=self._auth(),
        )
        self.assertEqual(res.status_code, 400, res.text)
        self.assertEqual(res.json()["detail"], "params 过大")

    def test_empty_title_is_422(self):
        """空标题是 schema 越界（min_length=1），走 422 而非业务 400。"""
        res = self.client.post(
            "/api/v1/records",
            json={"kind": "bazi", "title": "", "params": BAZI_PARAMS},
            headers=self._auth(),
        )
        self.assertEqual(res.status_code, 422, res.text)

    # ------------------------------------------------------------ 保存与去重
    def test_save_returns_full_detail(self):
        data = self._save(
            kind="bazi", title="乾造 1990-05-20", summary="辛未 丁酉 癸未 丙辰",
            params=BAZI_PARAMS,
        )
        self.assertTrue(data["id"].startswith("rec_"))
        self.assertEqual(data["kind"], "bazi")
        self.assertEqual(data["title"], "乾造 1990-05-20")
        self.assertEqual(data["params"], BAZI_PARAMS)
        self.assertTrue(data["created_at"])
        self.assertTrue(data["updated_at"])

    def test_list_is_light_and_scoped(self):
        """列表项不带 params；只看得到自己的记录。"""
        self._save(kind="bazi", title="我的", params=BAZI_PARAMS)
        self._save(tag="other", kind="bazi", title="别人的", params=BAZI_PARAMS)

        mine = self._ok(self.client.get("/api/v1/records", headers=self._auth()))[
            "items"
        ]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]["title"], "我的")
        self.assertNotIn("params", mine[0])

        theirs = self._ok(
            self.client.get("/api/v1/records", headers=self._auth("other"))
        )["items"]
        self.assertEqual(len(theirs), 1)
        self.assertEqual(theirs[0]["title"], "别人的")

    def test_resame_params_updates_instead_of_duplicating(self):
        """同参重存：id 不变、行数不变、标题刷新——列表语义是「最近再看一次」。"""
        first = self._save(kind="bazi", title="旧标题", params=BAZI_PARAMS)
        second = self._save(kind="bazi", title="新标题", params=BAZI_PARAMS)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(second["title"], "新标题")

        items = self._ok(
            self.client.get("/api/v1/records", headers=self._auth())
        )["items"]
        self.assertEqual(len(items), 1)

        session = SessionLocal()
        try:
            rows = (
                session.query(CalcRecord)
                .filter(CalcRecord.owner_id == self.users["owner"].id)
                .all()
            )
            self.assertEqual(len(rows), 1)
        finally:
            session.close()

    def test_same_params_different_kind_are_two_rows(self):
        """换 kind 是另一次测算：八字与八宅即使用同一份出生信息也各存一条。"""
        self._save(kind="bazi", title="八字", params=BAZI_PARAMS)
        self._save(kind="bazhai", title="八宅", params=BAZI_PARAMS)
        items = self._ok(
            self.client.get("/api/v1/records", headers=self._auth())
        )["items"]
        self.assertEqual({i["kind"] for i in items}, {"bazi", "bazhai"})

    def test_list_orders_by_updated_desc(self):
        a = self._save(kind="bazi", title="A", params=BAZI_PARAMS)
        b = self._save(
            kind="bazi",
            title="B",
            params={**BAZI_PARAMS, "year": 1991},
        )
        # 重存 A，A 应浮到最前
        self._save(kind="bazi", title="A 又看一次", params=BAZI_PARAMS)
        items = self._ok(
            self.client.get("/api/v1/records", headers=self._auth())
        )["items"]
        self.assertEqual(items[0]["id"], a["id"])
        self.assertEqual(items[0]["title"], "A 又看一次")
        self.assertEqual(items[1]["id"], b["id"])

    # ------------------------------------------------------------ 删除
    def test_delete_then_detail_is_404(self):
        saved = self._save(kind="bazi", title="待删除", params=BAZI_PARAMS)
        rid = saved["id"]

        res = self.client.delete(f"/api/v1/records/{rid}", headers=self._auth())
        data = self._ok(res)
        self.assertTrue(data["deleted"])
        self.assertEqual(data["id"], rid)

        self.assertEqual(
            self.client.get(
                f"/api/v1/records/{rid}", headers=self._auth()
            ).status_code,
            404,
        )
        # 重复删除同一 id：第二次只是 nothing to delete，同样不泄露
        res = self.client.delete(f"/api/v1/records/{rid}", headers=self._auth())
        self.assertFalse(self._ok(res)["deleted"])

    # ------------------------------------------------------------ 分界未破
    def test_compute_endpoints_still_login_free(self):
        """加档案路由不能顺手给纯计算接口装上鉴权。"""
        res = self.client.get("/api/v1/almanac/today")
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["code"], 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
