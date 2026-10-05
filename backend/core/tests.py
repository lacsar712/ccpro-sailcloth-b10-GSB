import threading
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connections
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from .models import ClothRoll, DipRun, Loft

User = get_user_model()


class LoftRenameTests(TransactionTestCase):
    """帆布间改名台验收测试。

    使用 TransactionTestCase 而非 TestCase：并发撞名用例需要跨线程/连接
    真正提交事务，才能验证数据库层唯一约束兜底。
    """

    reset_sequences = True

    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin", password="123456", role=User.ROLE_ADMIN
        )
        self.admin2 = User.objects.create_user(
            username="admin2", password="123456", role=User.ROLE_ADMIN
        )
        self.worker = User.objects.create_user(
            username="worker", password="123456", role=User.ROLE_WORKER
        )
        self.north = Loft.objects.create(name="北岸帆布间", location="港区二号库")
        self.south = Loft.objects.create(name="南岬帆布间", location="港区七号棚")
        self.r1 = ClothRoll.objects.create(
            loft=self.north, roll_code="R-01", status=ClothRoll.STATUS_DIPPING
        )
        self.r2 = ClothRoll.objects.create(
            loft=self.north, roll_code="R-02", status=ClothRoll.STATUS_RAW
        )
        self.r3 = ClothRoll.objects.create(
            loft=self.south, roll_code="S-01", status=ClothRoll.STATUS_CURED
        )
        self.dip = DipRun.objects.create(
            roll=self.r1,
            started_at="2026-10-05T08:00:00+08:00",
            resin_pct=Decimal("28.5"),
            cure_hours=None,
        )

    def _client(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    # ---- 正常路径 -------------------------------------------------------

    def test_admin_can_rename_and_everywhere_follows(self):
        client = self._client(self.admin)
        resp = client.post(
            f"/api/lofts/{self.north.id}/rename/",
            {"name": "  东港帆布间  "},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["name"], "东港帆布间")

        self.north.refresh_from_db()
        self.assertEqual(self.north.name, "东港帆布间")

        # 布卷没有被删、归属未变，挂签所属间认新名
        self.assertEqual(ClothRoll.objects.count(), 3)
        self.assertEqual(set(self.north.rolls.values_list("roll_code", flat=True)), {"R-01", "R-02"})

        rolls = client.get("/api/rolls/").data
        rolls = rolls["results"] if isinstance(rolls, dict) else rolls
        north_rolls = [r for r in rolls if r["loftId"] == self.north.id]
        self.assertTrue(north_rolls)
        self.assertTrue(all(r["loftName"] == "东港帆布间" for r in north_rolls))

        # 浸渍流水上的间名同样认新名
        dips = client.get("/api/dips/").data
        dips = dips["results"] if isinstance(dips, dict) else dips
        row = next(d for d in dips if d["id"] == self.dip.id)
        self.assertEqual(row["loftName"], "东港帆布间")

    def test_rename_does_not_delete_rolls_or_change_status(self):
        before = list(ClothRoll.objects.values("id", "status", "loft_id"))
        resp = self._client(self.admin).post(
            f"/api/lofts/{self.north.id}/rename/",
            {"name": "新名帆布间"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        after = list(ClothRoll.objects.values("id", "status", "loft_id"))
        self.assertEqual(before, after)  # 卷数、卷态、归属完全不动
        self.assertEqual(DipRun.objects.count(), 1)

    def test_rename_to_same_name_is_noop(self):
        resp = self._client(self.admin).post(
            f"/api/lofts/{self.south.id}/rename/",
            {"name": self.south.name},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["name"], self.south.name)

    # ---- 非法输入 -------------------------------------------------------

    def test_empty_name_rejected(self):
        for bad in ["", "   ", "\t\n"]:
            resp = self._client(self.admin).post(
                f"/api/lofts/{self.north.id}/rename/",
                {"name": bad},
                format="json",
            )
            self.assertEqual(resp.status_code, 400, bad)
            self.assertIn("name", resp.data)
        self.north.refresh_from_db()
        self.assertEqual(self.north.name, "北岸帆布间")

    def test_duplicate_name_rejected(self):
        resp = self._client(self.admin).post(
            f"/api/lofts/{self.north.id}/rename/",
            {"name": "南岬帆布间"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("name", resp.data)
        self.north.refresh_from_db()
        self.assertEqual(self.north.name, "北岸帆布间")

    def test_whitespace_trimmed_duplicate_rejected(self):
        # "南岬帆布间  " 去空格后与既有间撞名，必须挡住
        resp = self._client(self.admin).post(
            f"/api/lofts/{self.north.id}/rename/",
            {"name": "  南岬帆布间 "},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_missing_name_field_rejected(self):
        resp = self._client(self.admin).post(
            f"/api/lofts/{self.south.id}/rename/", {}, format="json"
        )
        self.assertEqual(resp.status_code, 400)

    # ---- 权限 -----------------------------------------------------------

    def test_worker_cannot_rename(self):
        resp = self._client(self.worker).post(
            f"/api/lofts/{self.north.id}/rename/",
            {"name": "工人想改的名"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)
        self.north.refresh_from_db()
        self.assertEqual(self.north.name, "北岸帆布间")

    def test_anonymous_cannot_rename(self):
        resp = self.client.post(
            f"/api/lofts/{self.north.id}/rename/",
            {"name": "匿名想改的名"},
            format="json",
        )
        self.assertEqual(resp.status_code, 401)

    def test_loft_collection_is_read_only(self):
        # 改名台没有新增/删除帆布间的入口：任何角色 POST 集合地址都 405
        for user in (self.admin, self.worker):
            resp = self._client(user).post(
                "/api/lofts/", {"name": "偷渡的新间"}, format="json"
            )
            self.assertEqual(resp.status_code, 405, user.username)
        # PATCH/PUT/DELETE 详情同样不开放，杜绝顺手删间（级联删卷）
        for method in ("patch", "put", "delete"):
            resp = getattr(self._client(self.admin), method)(
                f"/api/lofts/{self.north.id}/", {"name": "x"}, format="json"
            )
            self.assertEqual(resp.status_code, 405, method)

    def test_worker_may_still_read_loft_list(self):
        resp = self._client(self.worker).get("/api/lofts/")
        self.assertEqual(resp.status_code, 200)

    # ---- 并发 -----------------------------------------------------------

    def test_concurrent_rename_to_same_name_only_one_wins(self):
        """两名管理员交叉把两间改成同一个新名：只许一间改成，另一间挡住。"""
        results = {}
        barrier = threading.Barrier(2)

        def rename(user, loft, tag):
            client = self._client(user)
            try:
                barrier.wait(timeout=10)
                resp = client.post(
                    f"/api/lofts/{loft.id}/rename/",
                    {"name": "中央帆布间"},
                    format="json",
                )
                results[tag] = resp.status_code
            finally:
                # 线程独立连接，用完即关，避免泄漏
                connections["default"].close()

        t1 = threading.Thread(target=rename, args=(self.admin, self.north, "a"))
        t2 = threading.Thread(target=rename, args=(self.admin2, self.south, "b"))
        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)

        self.assertEqual(set(results), {"a", "b"})
        self.assertEqual(
            sorted(results.values()),
            [200, 400],
            f"必须一成一挡，实际：{results}",
        )
        self.assertEqual(Loft.objects.filter(name="中央帆布间").count(), 1)
        self.assertEqual(Loft.objects.count(), 2)
        # 两间的布卷都还在、状态未动
        self.assertEqual(ClothRoll.objects.count(), 3)
        self.assertEqual(
            set(ClothRoll.objects.values_list("id", "status")),
            {
                (self.r1.id, ClothRoll.STATUS_DIPPING),
                (self.r2.id, ClothRoll.STATUS_RAW),
                (self.r3.id, ClothRoll.STATUS_CURED),
            },
        )
