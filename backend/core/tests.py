import threading
from decimal import Decimal

from django.db import close_old_connections
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from accounts.models import User
from core.models import ClothRoll, DipRun, Loft


def make_users_and_lofts():
    admin = User.objects.create_user("admin_a", password="x", role=User.ROLE_ADMIN)
    admin_b = User.objects.create_user("admin_b", password="x", role=User.ROLE_ADMIN)
    worker = User.objects.create_user("worker", password="x", role=User.ROLE_WORKER)

    loft_a = Loft.objects.create(name="东岸帆布间", location="一库")
    loft_b = Loft.objects.create(name="西岸帆布间", location="二库")

    roll_a = ClothRoll.objects.create(
        loft=loft_a, roll_code="A-01", status=ClothRoll.STATUS_DIPPING
    )
    ClothRoll.objects.create(
        loft=loft_a, roll_code="A-02", status=ClothRoll.STATUS_RAW
    )
    ClothRoll.objects.create(
        loft=loft_b, roll_code="B-01", status=ClothRoll.STATUS_CURED
    )
    dip = DipRun.objects.create(
        roll=roll_a,
        started_at=timezone.now(),
        resin_pct=Decimal("28.00"),
        cure_hours=Decimal("13.00"),
    )
    return admin, admin_b, worker, loft_a, loft_b, roll_a, dip


class LoftRenameTests(APITestCase):
    def setUp(self):
        (
            self.admin,
            self.admin_b,
            self.worker,
            self.loft_a,
            self.loft_b,
            self.roll_a,
            self.dip,
        ) = make_users_and_lofts()

    def _snapshot_rolls(self):
        return list(
            ClothRoll.objects.order_by("id").values_list(
                "id", "loft_id", "roll_code", "status", "updated_at"
            )
        )

    # ---- 正常改名 + 三处级联显示 ----

    def test_admin_rename_success_and_name_cascades_everywhere(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            f"/api/lofts/{self.loft_a.id}/rename/",
            {"name": "南岸帆布间"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data["name"], "南岸帆布间")

        self.loft_a.refresh_from_db()
        self.assertEqual(self.loft_a.name, "南岸帆布间")

        # 晾晒架架面（间名取自 lofts 列表）
        lofts = self.client.get("/api/lofts/").data
        results = lofts.get("results", lofts)
        names = {l["id"]: l["name"] for l in results}
        self.assertEqual(names[self.loft_a.id], "南岸帆布间")
        self.assertEqual(names[self.loft_b.id], "西岸帆布间")

        # 挂签所属间（布卷上的 loftName）
        rolls = self.client.get("/api/rolls/").data
        rolls = rolls.get("results", rolls)
        roll_names = {r["id"]: r["loftName"] for r in rolls}
        for r in rolls:
            if r["loftId"] == self.loft_a.id:
                self.assertEqual(r["loftName"], "南岸帆布间")
            if r["loftId"] == self.loft_b.id:
                self.assertEqual(r["loftName"], "西岸帆布间")

        # 浸渍流水上的间名
        dips = self.client.get("/api/dips/").data
        dips = dips.get("results", dips)
        dip_row = next(d for d in dips if d["id"] == self.dip.id)
        self.assertEqual(dip_row["loftName"], "南岸帆布间")

    def test_rename_trims_surrounding_whitespace(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            f"/api/lofts/{self.loft_a.id}/rename/",
            {"name": "  新帆布间  "},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.loft_a.refresh_from_db()
        self.assertEqual(self.loft_a.name, "新帆布间")

    # ---- 非法输入 ----

    def test_rename_empty_name_rejected(self):
        self.client.force_authenticate(self.admin)
        for bad in ("", "   "):
            resp = self.client.post(
                f"/api/lofts/{self.loft_a.id}/rename/",
                {"name": bad},
                format="json",
            )
            self.assertEqual(resp.status_code, 400, bad)
        self.loft_a.refresh_from_db()
        self.assertEqual(self.loft_a.name, "东岸帆布间")

    def test_rename_duplicate_name_rejected(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            f"/api/lofts/{self.loft_b.id}/rename/",
            {"name": "东岸帆布间"},
            format="json",
        )
        self.assertIn(resp.status_code, (400, 409))
        self.loft_b.refresh_from_db()
        self.assertEqual(self.loft_b.name, "西岸帆布间")

    # ---- 操作工权限 ----

    def test_worker_cannot_rename(self):
        self.client.force_authenticate(self.worker)
        resp = self.client.post(
            f"/api/lofts/{self.loft_a.id}/rename/",
            {"name": "想改的名"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)
        self.loft_a.refresh_from_db()
        self.assertEqual(self.loft_a.name, "东岸帆布间")

    def test_worker_cannot_create_or_patch_loft(self):
        self.client.force_authenticate(self.worker)
        self.assertEqual(
            self.client.post("/api/lofts/", {"name": "新间"}, format="json").status_code,
            403,
        )
        self.assertEqual(
            self.client.patch(
                f"/api/lofts/{self.loft_a.id}/",
                {"name": "偷偷改名"},
                format="json",
            ).status_code,
            403,
        )

    def test_worker_can_read_lofts(self):
        self.client.force_authenticate(self.worker)
        self.assertEqual(self.client.get("/api/lofts/").status_code, 200)

    def test_anonymous_cannot_rename(self):
        resp = self.client.post(
            f"/api/lofts/{self.loft_a.id}/rename/",
            {"name": "新名"},
            format="json",
        )
        self.assertEqual(resp.status_code, 401)

    # ---- 改名不得顺手删卷或改卷态 ----

    def test_rename_does_not_touch_rolls(self):
        before = self._snapshot_rolls()
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            f"/api/lofts/{self.loft_a.id}/rename/",
            {"name": "南岸帆布间"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(self._snapshot_rolls(), before)
        self.assertEqual(ClothRoll.objects.count(), 3)

    def test_rename_ignores_extra_fields(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            f"/api/lofts/{self.loft_a.id}/rename/",
            {"name": "南岸帆布间", "location": "被篡改的库位", "notes": "x"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.loft_a.refresh_from_db()
        self.assertEqual(self.loft_a.location, "一库")
        self.assertEqual(self.loft_a.notes, "")


class ConcurrentRenameTests(TransactionTestCase):
    """两名管理员交叉把两间改成同一个新名：只许一间改成。

    用 TransactionTestCase（非 TestCase）保证线程能看到已提交数据；
    测试库须为跨线程共享的文件型 SQLite（见 settings_test.TEST.NAME）。
    """

    reset_sequences = True

    def setUp(self):
        self.admin, self.admin_b, _, self.loft_a, self.loft_b, _, _ = (
            make_users_and_lofts()
        )

    def test_concurrent_cross_rename_only_one_wins(self):
        barrier = threading.Barrier(2)
        results = {}
        errors = {}

        def rename(user_id, loft_id, key):
            client = APIClient()
            try:
                # 线程持有独立数据库连接
                user = User.objects.get(id=user_id)
                client.force_authenticate(user)
                barrier.wait()
                resp = client.post(
                    f"/api/lofts/{loft_id}/rename/",
                    {"name": "同一个新名"},
                    format="json",
                )
                results[key] = resp.status_code
            except Exception as exc:  # noqa: BLE001
                errors[key] = repr(exc)
            finally:
                close_old_connections()

        t1 = threading.Thread(
            target=rename, args=(self.admin.id, self.loft_a.id, "a")
        )
        t2 = threading.Thread(
            target=rename, args=(self.admin_b.id, self.loft_b.id, "b")
        )
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(errors, {})
        self.assertEqual(set(results), {"a", "b"})
        self.assertIn(results["a"], (200, 400, 409))
        self.assertIn(results["b"], (200, 400, 409))

        winners = sum(1 for code in results.values() if code == 200)
        losers = [code for code in results.values() if code != 200]
        self.assertEqual(winners, 1, results)
        self.assertEqual(len(losers), 1)
        self.assertIn(losers[0], (400, 409))

        # 数据库层面同样保证：恰有一间叫新名，另一间保留原名
        names = set(Loft.objects.values_list("name", flat=True))
        self.assertEqual(len(names), 2)
        self.assertEqual(Loft.objects.filter(name="同一个新名").count(), 1)
        remaining = names - {"同一个新名"}
        self.assertEqual(len(remaining), 1)
        self.assertIn(next(iter(remaining)), {"东岸帆布间", "西岸帆布间"})
        # 布卷未被波及
        self.assertEqual(ClothRoll.objects.count(), 3)
