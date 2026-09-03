"""Iteration 3 tests:
- Label template GET/PUT roundtrip + label PDF with price/expiry
- Approval rules CRUD + default_threshold + resolve_threshold behavior
- Realtime webhook + cron endpoint auth
- Role guards + multi-tenant isolation
"""
import os, uuid
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://ai-inventory-worker.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api"

# read cron secret from backend .env
CRON_SECRET = None
try:
    with open("/app/backend/.env") as f:
        for ln in f:
            if ln.startswith("WEBHOOK_CRON_SECRET="):
                CRON_SECRET = ln.strip().split("=", 1)[1]
                break
except Exception:
    pass

ADMIN_EMAIL = "borgavakarshashikant@gmail.com"
ADMIN_PASSWORD = "AdminPass@2026"
WORKER_EMAIL = "worker1@example.com"
WORKER_PASSWORD = "Worker@2026"


def _login(email, password):
    return requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)


def _auth(t): return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="session")
def admin_token():
    r = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def worker_token(admin_token):
    r = _login(WORKER_EMAIL, WORKER_PASSWORD)
    if r.status_code != 200:
        rc = requests.post(f"{API}/users", headers=_auth(admin_token),
                           json={"email": WORKER_EMAIL, "password": WORKER_PASSWORD, "name": "Worker One", "role": "worker"}, timeout=20)
        assert rc.status_code == 200, rc.text
        r = _login(WORKER_EMAIL, WORKER_PASSWORD)
    assert r.status_code == 200
    return r.json()["token"]


# ---------------- Label template ----------------
class TestLabelTemplate:
    def test_put_get_roundtrip(self, admin_token):
        payload = {
            "org_line": "Acme Warehouse Co.",
            "logo_url": "",
            "show_brand": True,
            "show_sku": True,
            "show_price": True,
            "show_expiry": True,
            "footer": "Handle with care",
        }
        r = requests.put(f"{API}/label-template", headers=_auth(admin_token), json=payload, timeout=20)
        assert r.status_code == 200, r.text
        g = requests.get(f"{API}/label-template", headers=_auth(admin_token), timeout=20)
        assert g.status_code == 200
        t = g.json()
        assert t["show_price"] is True
        assert t["show_expiry"] is True
        assert t["footer"] == "Handle with care"
        assert t["org_line"] == "Acme Warehouse Co."

    def test_worker_cannot_put_template(self, worker_token):
        r = requests.put(f"{API}/label-template", headers=_auth(worker_token),
                         json={"org_line": "X", "logo_url": "", "show_brand": True, "show_sku": True,
                               "show_price": False, "show_expiry": False, "footer": ""}, timeout=20)
        assert r.status_code == 403

    def test_label_pdf_with_price_and_expiry(self, admin_token):
        pr = requests.get(f"{API}/products", headers=_auth(admin_token), timeout=20)
        assert pr.status_code == 200 and pr.json()
        pid = pr.json()[0]["id"]
        r = requests.get(f"{API}/products/{pid}/label",
                         params={"kind": "barcode", "count": 2, "price": "499.00", "expiry": "2027-01-31"},
                         headers=_auth(admin_token), timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert len(r.content) > 1024
        assert r.content[:4] == b"%PDF"


# ---------------- Approval rules + resolve_threshold ----------------
class TestApprovalRules:
    created_rule_id = None

    def test_reset_default_and_clear_rules(self, admin_token):
        # reset default threshold to 25 baseline for later tests
        r = requests.put(f"{API}/org-settings", headers=_auth(admin_token),
                         json={"default_threshold": 25}, timeout=20)
        assert r.status_code == 200, r.text
        # clean existing rules
        lr = requests.get(f"{API}/approval-rules", headers=_auth(admin_token), timeout=20)
        assert lr.status_code == 200
        j = lr.json()
        assert "rules" in j and "default_threshold" in j
        assert j["default_threshold"] == 25
        for rule in j["rules"]:
            rd = requests.delete(f"{API}/approval-rules/{rule['id']}", headers=_auth(admin_token), timeout=20)
            assert rd.status_code == 200

    def test_worker_cannot_post_rule(self, worker_token):
        r = requests.post(f"{API}/approval-rules", headers=_auth(worker_token),
                          json={"warehouse_id": None, "category": "Electronics", "threshold": 200}, timeout=20)
        assert r.status_code == 403

    def test_create_rule_pune_electronics(self, admin_token):
        # find Pune warehouse id
        wr = requests.get(f"{API}/warehouses", headers=_auth(admin_token), timeout=20)
        assert wr.status_code == 200
        pune = next((w for w in wr.json() if "pune" in w["name"].lower()), None)
        assert pune, "Pune warehouse not seeded"
        r = requests.post(f"{API}/approval-rules", headers=_auth(admin_token),
                          json={"warehouse_id": pune["id"], "category": "Electronics", "threshold": 200}, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("threshold") == 200
        assert data.get("warehouse_id") == pune["id"]
        assert "id" in data
        TestApprovalRules.created_rule_id = data["id"]

    def test_resolve_threshold_auto_apply_electronics(self, admin_token, worker_token):
        # Find inventory row for Samsung Monitor at Pune
        pr = requests.get(f"{API}/products", headers=_auth(admin_token), timeout=20)
        prod = next((p for p in pr.json() if "samsung" in p["name"].lower() and (p.get("category") or "").lower() == "electronics"), None)
        assert prod, "Samsung Monitor Electronics not found"
        inv = requests.get(f"{API}/inventory", headers=_auth(admin_token), timeout=20).json()
        wr = requests.get(f"{API}/warehouses", headers=_auth(admin_token), timeout=20).json()
        pune = next(w for w in wr if "pune" in w["name"].lower())
        row = next((i for i in inv if i["product_id"] == prod["id"] and i["warehouse_id"] == pune["id"]), None)
        assert row, "No inventory row for Samsung at Pune"
        cur = row["quantity"]
        r = requests.post(f"{API}/inventory/adjust", headers=_auth(worker_token),
                          json={"inventory_id": row["id"], "new_quantity": cur + 100, "reason": "iter3 auto"}, timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["approval_required"] is False, f"expected auto-apply, got: {j}"
        assert j.get("threshold") == 200
        # revert
        requests.post(f"{API}/inventory/adjust", headers=_auth(worker_token),
                      json={"inventory_id": row["id"], "new_quantity": cur, "reason": "iter3 revert"}, timeout=20)

    def test_resolve_threshold_non_electronics_requires_approval(self, admin_token, worker_token):
        pr = requests.get(f"{API}/products", headers=_auth(admin_token), timeout=20).json()
        non_elec = next((p for p in pr if (p.get("category") or "").lower() != "electronics"), None)
        assert non_elec, "no non-electronics product"
        inv = requests.get(f"{API}/inventory", headers=_auth(admin_token), timeout=20).json()
        wr = requests.get(f"{API}/warehouses", headers=_auth(admin_token), timeout=20).json()
        pune = next(w for w in wr if "pune" in w["name"].lower())
        row = next((i for i in inv if i["product_id"] == non_elec["id"] and i["warehouse_id"] == pune["id"]), None)
        if not row:
            # fallback: any non-electronics row (rule only matches Pune+Electronics, so default=25 applies)
            row = next((i for i in inv if i["product_id"] == non_elec["id"]), None)
        assert row, "no inventory for non-electronics"
        cur = row["quantity"]
        r = requests.post(f"{API}/inventory/adjust", headers=_auth(worker_token),
                          json={"inventory_id": row["id"], "new_quantity": cur + 100, "reason": "iter3 non-elec big"}, timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["approval_required"] is True, f"expected approval, got {j}"
        assert j.get("threshold") == 25
        assert "approval_id" in j

    def test_delete_rule(self, admin_token):
        assert TestApprovalRules.created_rule_id
        r = requests.delete(f"{API}/approval-rules/{TestApprovalRules.created_rule_id}",
                            headers=_auth(admin_token), timeout=20)
        assert r.status_code == 200
        g = requests.get(f"{API}/approval-rules", headers=_auth(admin_token), timeout=20).json()
        assert all(rl["id"] != TestApprovalRules.created_rule_id for rl in g["rules"])


# ---------------- Realtime webhook + cron ----------------
class TestRealtime:
    def test_webhook_upsert_and_bad_token(self, admin_token):
        cname = f"TEST_wh_{uuid.uuid4().hex[:6]}"
        c = requests.post(f"{API}/connectors", headers=_auth(admin_token),
                          json={"name": cname, "kind": "rest",
                                "config": {"url": "https://jsonplaceholder.typicode.com/todos",
                                           "field_map": {"sku": "sku", "name": "name"}}}, timeout=20)
        assert c.status_code == 200, c.text
        cid = c.json()["id"]
        token = c.json().get("webhook_token")
        assert token, "connector must expose webhook_token"

        # correct token
        r = requests.post(f"{API}/webhooks/connectors/{cid}/{token}",
                          json={"records": [{"sku": "W-01", "name": "Test WH"}]}, timeout=20)
        assert r.status_code == 200, r.text
        # product upserted?
        pr = requests.get(f"{API}/products", headers=_auth(admin_token), timeout=20).json()
        assert any(p["sku"] == "W-01" for p in pr), "Webhook did not upsert product"

        # wrong token
        rb = requests.post(f"{API}/webhooks/connectors/{cid}/wrongtoken123",
                           json={"records": [{"sku": "X", "name": "X"}]}, timeout=20)
        assert rb.status_code == 404

        # cleanup connector
        requests.delete(f"{API}/connectors/{cid}", headers=_auth(admin_token), timeout=20)

    def test_cron_endpoint_auth(self):
        # No auth -> 401
        r = requests.post(f"{API}/cron/sync-connectors", timeout=20)
        assert r.status_code == 401
        # Wrong bearer -> 401
        r2 = requests.post(f"{API}/cron/sync-connectors",
                           headers={"Authorization": "Bearer wrong-secret"}, timeout=20)
        assert r2.status_code == 401
        # Correct -> 200 queued
        assert CRON_SECRET, "WEBHOOK_CRON_SECRET missing"
        r3 = requests.post(f"{API}/cron/sync-connectors",
                           headers={"Authorization": f"Bearer {CRON_SECRET}"}, timeout=20)
        assert r3.status_code == 200, r3.text
        j = r3.json()
        assert j.get("ok") is True and j.get("queued") is True


# ---------------- Multi-tenant isolation ----------------
class TestMultiTenantIter3:
    def test_isolation_template_and_rules(self, admin_token):
        # first ensure org A has a template with distinct footer
        requests.put(f"{API}/label-template", headers=_auth(admin_token),
                     json={"org_line": "Acme Warehouse Co.", "logo_url": "", "show_brand": True,
                           "show_sku": True, "show_price": True, "show_expiry": True,
                           "footer": "ORG_A_FOOTER"}, timeout=20)
        # create org B via signup
        email = f"TEST_iter3_org2_{uuid.uuid4().hex[:8]}@example.com"
        r = requests.post(f"{API}/auth/signup", json={
            "email": email, "password": "SecondOrg@2026",
            "name": "B Admin", "org_name": "TEST_IterB"
        }, timeout=20)
        assert r.status_code == 200, r.text
        tok = r.json()["token"]

        gt = requests.get(f"{API}/label-template", headers=_auth(tok), timeout=20).json()
        assert gt.get("footer", "") != "ORG_A_FOOTER"

        gr = requests.get(f"{API}/approval-rules", headers=_auth(tok), timeout=20).json()
        assert gr["rules"] == [] or all("org_id" not in r_ for r_ in gr["rules"])
