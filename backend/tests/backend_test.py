"""Backend tests for AI Inventory Worker iteration 2:
- Voice transcription
- Connectors CRUD (REST) + role guard + multi-tenant
- Approval workflow (>50 delta by worker)
- Barcode/QR PDF labels + auth
"""
import os, io, wave, struct, math, uuid, time
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://ai-inventory-worker.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "borgavakarshashikant@gmail.com"
ADMIN_PASSWORD = "AdminPass@2026"
WORKER_EMAIL = "worker1@example.com"
WORKER_PASSWORD = "Worker@2026"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    return r


@pytest.fixture(scope="session")
def admin_token():
    r = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def worker_token(admin_token):
    r = _login(WORKER_EMAIL, WORKER_PASSWORD)
    if r.status_code != 200:
        # Create worker
        rc = requests.post(f"{API}/users",
                           headers={"Authorization": f"Bearer {admin_token}"},
                           json={"email": WORKER_EMAIL, "password": WORKER_PASSWORD, "name": "Worker One", "role": "worker"},
                           timeout=20)
        assert rc.status_code == 200, f"Failed to create worker: {rc.status_code} {rc.text}"
        r = _login(WORKER_EMAIL, WORKER_PASSWORD)
    assert r.status_code == 200, f"Worker login failed: {r.text}"
    return r.json()["token"]


def _auth(t): return {"Authorization": f"Bearer {t}"}


# ---------- Voice ----------
def _make_silent_wav_bytes(duration_s=1, sr=16000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(b"\x00\x00" * (sr * duration_s))
    buf.seek(0)
    return buf.read()


class TestVoice:
    def test_transcribe_silent_wav(self, admin_token):
        wav = _make_silent_wav_bytes()
        r = requests.post(f"{API}/voice/transcribe",
                          headers=_auth(admin_token),
                          files={"file": ("silent.wav", wav, "audio/wav")},
                          timeout=60)
        # Should not 500. Accept 200 with (possibly empty) text.
        assert r.status_code == 200, f"Voice transcribe failed: {r.status_code} {r.text[:300]}"
        j = r.json()
        assert "text" in j
        assert isinstance(j["text"], str)


# ---------- Connectors ----------
class TestConnectors:
    connector_id = None

    def test_create_rest_connector(self, admin_token):
        payload = {
            "name": "TEST_JSONPlaceholder",
            "kind": "rest",
            "config": {
                "url": "https://jsonplaceholder.typicode.com/todos",
                "field_map": {"sku": "id", "name": "title"}
            }
        }
        r = requests.post(f"{API}/connectors", headers=_auth(admin_token), json=payload, timeout=20)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        data = r.json()
        assert data["name"] == "TEST_JSONPlaceholder"
        assert data["kind"] == "rest"
        assert "id" in data
        TestConnectors.connector_id = data["id"]

    def test_list_connectors_contains(self, admin_token):
        r = requests.get(f"{API}/connectors", headers=_auth(admin_token), timeout=20)
        assert r.status_code == 200
        items = r.json()
        assert any(c["id"] == TestConnectors.connector_id for c in items)

    def test_test_connector(self, admin_token):
        assert TestConnectors.connector_id
        r = requests.post(f"{API}/connectors/{TestConnectors.connector_id}/test",
                          headers=_auth(admin_token), timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True, f"Test failed: {j}"
        assert isinstance(j.get("sample"), list)
        assert len(j["sample"]) > 0
        # Verify field_map applied
        first = j["sample"][0]
        assert "sku" in first and "name" in first

    def test_worker_cannot_create_connector(self, worker_token):
        r = requests.post(f"{API}/connectors", headers=_auth(worker_token),
                          json={"name": "x", "kind": "rest", "config": {"url": "http://x"}}, timeout=20)
        assert r.status_code == 403, f"Expected 403 got {r.status_code}"

    def test_multi_tenant_isolation(self, admin_token):
        # Create second org via signup
        email = f"TEST_org2_{uuid.uuid4().hex[:8]}@example.com"
        r = requests.post(f"{API}/auth/signup", json={
            "email": email, "password": "SecondOrg@2026",
            "name": "Second Admin", "org_name": "TEST_SecondOrg"
        }, timeout=20)
        assert r.status_code == 200, r.text
        tok2 = r.json()["token"]
        r2 = requests.get(f"{API}/connectors", headers=_auth(tok2), timeout=20)
        assert r2.status_code == 200
        items = r2.json()
        # Should NOT contain first org's connector
        assert all(c["id"] != TestConnectors.connector_id for c in items)

    def test_delete_connector(self, admin_token):
        assert TestConnectors.connector_id
        r = requests.delete(f"{API}/connectors/{TestConnectors.connector_id}",
                            headers=_auth(admin_token), timeout=20)
        assert r.status_code == 200
        # verify gone
        r2 = requests.get(f"{API}/connectors", headers=_auth(admin_token), timeout=20)
        assert all(c["id"] != TestConnectors.connector_id for c in r2.json())

    def test_manager_cannot_create_connector(self, admin_token):
        # Create a manager
        email = f"TEST_mgr_{uuid.uuid4().hex[:6]}@example.com"
        rc = requests.post(f"{API}/users", headers=_auth(admin_token),
                           json={"email": email, "password": "Mgr@2026", "name": "Test Mgr", "role": "manager"},
                           timeout=20)
        assert rc.status_code == 200
        rl = _login(email, "Mgr@2026")
        assert rl.status_code == 200
        mtok = rl.json()["token"]
        r = requests.post(f"{API}/connectors", headers=_auth(mtok),
                          json={"name": "x", "kind": "rest", "config": {"url": "http://x"}}, timeout=20)
        assert r.status_code == 403


# ---------- Approvals ----------
class TestApprovals:
    approval_id = None
    inventory_id = None
    orig_qty = None

    def _get_inventory_row(self, admin_token):
        r = requests.get(f"{API}/inventory", headers=_auth(admin_token), timeout=20)
        assert r.status_code == 200
        inv = r.json()
        # pick one with sufficient qty for +delta > 50 (or just any; delta is abs)
        assert len(inv) > 0
        return inv[0]

    def test_small_delta_applies_directly(self, admin_token, worker_token):
        row = self._get_inventory_row(admin_token)
        TestApprovals.inventory_id = row["id"]
        TestApprovals.orig_qty = row["quantity"]
        new_qty = row["quantity"] + 1  # delta=1
        r = requests.post(f"{API}/inventory/adjust", headers=_auth(worker_token),
                          json={"inventory_id": row["id"], "new_quantity": new_qty, "reason": "small"},
                          timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["approval_required"] is False
        # Verify persisted
        r2 = requests.get(f"{API}/inventory", headers=_auth(admin_token), timeout=20)
        row2 = next(x for x in r2.json() if x["id"] == row["id"])
        assert row2["quantity"] == new_qty

    def test_large_delta_requires_approval(self, admin_token, worker_token):
        # Get current qty
        r0 = requests.get(f"{API}/inventory", headers=_auth(admin_token), timeout=20)
        row = next(x for x in r0.json() if x["id"] == TestApprovals.inventory_id)
        cur = row["quantity"]
        new_qty = cur + 100  # delta 100 > 50
        r = requests.post(f"{API}/inventory/adjust", headers=_auth(worker_token),
                          json={"inventory_id": row["id"], "new_quantity": new_qty, "reason": "big change"},
                          timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["approval_required"] is True
        assert "approval_id" in j
        TestApprovals.approval_id = j["approval_id"]
        # Verify inventory NOT changed
        r2 = requests.get(f"{API}/inventory", headers=_auth(admin_token), timeout=20)
        row2 = next(x for x in r2.json() if x["id"] == row["id"])
        assert row2["quantity"] == cur, "Inventory should not change until approved"

    def test_list_pending_approvals(self, admin_token):
        r = requests.get(f"{API}/approvals?status_filter=pending", headers=_auth(admin_token), timeout=20)
        assert r.status_code == 200
        items = r.json()
        assert any(a["id"] == TestApprovals.approval_id for a in items), "Pending approval not in list"
        a = next(a for a in items if a["id"] == TestApprovals.approval_id)
        assert a["status"] == "pending"
        assert "product_name" in a
        assert a["payload"]["delta"] == 100

    def test_approve_mutates_inventory(self, admin_token):
        r0 = requests.get(f"{API}/inventory", headers=_auth(admin_token), timeout=20)
        row = next(x for x in r0.json() if x["id"] == TestApprovals.inventory_id)
        before = row["quantity"]
        r = requests.post(f"{API}/approvals/{TestApprovals.approval_id}/approve",
                          headers=_auth(admin_token), json={"reason": "ok"}, timeout=20)
        assert r.status_code == 200, r.text
        # Verify inventory updated
        r2 = requests.get(f"{API}/inventory", headers=_auth(admin_token), timeout=20)
        row2 = next(x for x in r2.json() if x["id"] == TestApprovals.inventory_id)
        assert row2["quantity"] == before + 100, f"expected {before+100}, got {row2['quantity']}"

    def test_reject_flow(self, admin_token, worker_token):
        # create a new pending approval
        r0 = requests.get(f"{API}/inventory", headers=_auth(admin_token), timeout=20)
        row = next(x for x in r0.json() if x["id"] == TestApprovals.inventory_id)
        cur = row["quantity"]
        new_qty = cur + 200
        r = requests.post(f"{API}/inventory/adjust", headers=_auth(worker_token),
                          json={"inventory_id": row["id"], "new_quantity": new_qty, "reason": "reject test"}, timeout=20)
        assert r.status_code == 200
        aid = r.json()["approval_id"]
        rr = requests.post(f"{API}/approvals/{aid}/reject", headers=_auth(admin_token),
                           json={"reason": "no"}, timeout=20)
        assert rr.status_code == 200
        # Inventory unchanged
        r2 = requests.get(f"{API}/inventory", headers=_auth(admin_token), timeout=20)
        row2 = next(x for x in r2.json() if x["id"] == row["id"])
        assert row2["quantity"] == cur, "Rejected approval must not mutate inventory"


# ---------- Labels ----------
class TestLabels:
    def test_barcode_label_pdf(self, admin_token):
        # Get any product
        pr = requests.get(f"{API}/products", headers=_auth(admin_token), timeout=20)
        assert pr.status_code == 200 and len(pr.json()) > 0
        pid = pr.json()[0]["id"]
        r = requests.get(f"{API}/products/{pid}/label?kind=barcode", headers=_auth(admin_token), timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:4] == b"%PDF"

    def test_qr_label_pdf(self, admin_token):
        pr = requests.get(f"{API}/products", headers=_auth(admin_token), timeout=20)
        pid = pr.json()[0]["id"]
        r = requests.get(f"{API}/products/{pid}/label?kind=qr", headers=_auth(admin_token), timeout=30)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:4] == b"%PDF"

    def test_label_unauthorized(self):
        pr = requests.get(f"{API}/products", timeout=20)
        # products also requires auth => probing endpoint without token
        r = requests.get(f"{API}/products/anyid/label?kind=barcode", timeout=20)
        assert r.status_code == 401
