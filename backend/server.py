"""AI INVENTORY WORKER - Backend API"""
from fastapi import FastAPI, APIRouter, HTTPException, Depends, status, UploadFile, File, Form, Request, Body
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime, timezone, timedelta
from pathlib import Path
import os, uuid, logging, json, bcrypt, jwt, io, base64, asyncio, secrets
import pandas as pd

from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent, TextDelta, ToolCallStart, ToolCallReady, StreamDone
from emergentintegrations.llm.openai import OpenAISpeechToText

import barcode as barcode_lib
from barcode.writer import ImageWriter
import qrcode as qrcode_lib
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
import requests as ext_requests
from sqlalchemy import create_engine, text as sa_text

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

MONGO_URL = os.environ['MONGO_URL']
DB_NAME = os.environ['DB_NAME']
JWT_SECRET = os.environ['JWT_SECRET']
JWT_EXPIRE_HOURS = int(os.environ.get('JWT_EXPIRE_HOURS', '168'))
EMERGENT_LLM_KEY = os.environ['EMERGENT_LLM_KEY']
ADMIN_EMAIL = os.environ['ADMIN_EMAIL']
ADMIN_PASSWORD = os.environ['ADMIN_PASSWORD']
ADMIN_NAME = os.environ['ADMIN_NAME']
WEBHOOK_CRON_SECRET = os.environ.get('WEBHOOK_CRON_SECRET', 'unset')

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

app = FastAPI(title="AI Inventory Worker API")
api = APIRouter(prefix="/api")
security = HTTPBearer(auto_error=False)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger("aiw")

# ---------- Helpers ----------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def new_id() -> str:
    return str(uuid.uuid4())

def hash_pw(p: str) -> str:
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()

def check_pw(p: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(p.encode(), h.encode())
    except Exception:
        return False

def make_token(user_id: str, org_id: str, role: str) -> str:
    payload = {
        "sub": user_id, "org_id": org_id, "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

async def current_user(creds: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    if not creds:
        raise HTTPException(401, "Missing token")
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid token")
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(401, "User not found")
    return user

def require_role(*roles: str):
    async def dep(user=Depends(current_user)):
        if user["role"] not in roles and user["role"] != "super_admin":
            raise HTTPException(403, f"Requires role: {roles}")
        return user
    return dep

async def audit(user: Dict, action: str, entity: str, entity_id: str, before: Any = None, after: Any = None, reason: str = ""):
    await db.audit_logs.insert_one({
        "id": new_id(), "org_id": user["org_id"], "user_id": user["id"],
        "user_name": user["name"], "action": action, "entity": entity,
        "entity_id": entity_id, "before": before, "after": after,
        "reason": reason, "timestamp": now_iso()
    })

# ---------- Models ----------
class SignupIn(BaseModel):
    email: EmailStr
    password: str
    name: str
    org_name: str

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: Literal["org_admin", "manager", "worker"] = "worker"

class WarehouseIn(BaseModel):
    name: str
    code: str
    address: Optional[str] = ""

class LocationIn(BaseModel):
    warehouse_id: str
    parent_id: Optional[str] = None
    type: Literal["zone", "aisle", "rack", "shelf", "bin"]
    name: str
    code: str

class ProductIn(BaseModel):
    sku: str
    barcode: Optional[str] = ""
    name: str
    description: Optional[str] = ""
    brand: Optional[str] = ""
    category: Optional[str] = ""
    model_number: Optional[str] = ""
    image_url: Optional[str] = ""
    attributes: Dict[str, Any] = {}

class InventoryIn(BaseModel):
    product_id: str
    warehouse_id: str
    location_id: Optional[str] = None
    quantity: int = 0
    reserved_quantity: int = 0
    reorder_level: int = 10

class InventoryAdjust(BaseModel):
    inventory_id: str
    new_quantity: int
    reason: str

class InventoryTransfer(BaseModel):
    product_id: str
    from_warehouse_id: str
    to_warehouse_id: str
    to_location_id: Optional[str] = None
    quantity: int
    reason: str

class ChatIn(BaseModel):
    message: str
    session_id: Optional[str] = None
    model: Literal["claude", "gemini"] = "claude"

class ImageScanIn(BaseModel):
    image_base64: str

class ConnectorIn(BaseModel):
    name: str
    kind: Literal["rest", "postgresql", "mysql"]
    config: Dict[str, Any] = {}

class ApprovalDecision(BaseModel):
    reason: Optional[str] = ""

class LabelTemplateIn(BaseModel):
    org_line: Optional[str] = ""
    logo_url: Optional[str] = ""
    show_brand: bool = True
    show_sku: bool = True
    show_price: bool = False
    show_expiry: bool = False
    footer: Optional[str] = ""

class ApprovalRuleIn(BaseModel):
    warehouse_id: Optional[str] = None
    category: Optional[str] = None
    threshold: int

class OrgSettingsIn(BaseModel):
    default_threshold: int

APPROVAL_THRESHOLD = 50  # legacy fallback; superseded by resolve_threshold()

async def resolve_threshold(org_id: str, warehouse_id: Optional[str], category: Optional[str]) -> int:
    rules = await db.approval_rules.find({"org_id": org_id}, {"_id": 0}).to_list(500)
    best, best_score = None, -1
    for r in rules:
        score = 0
        if r.get("warehouse_id"):
            if r["warehouse_id"] != warehouse_id: continue
            score += 2
        if r.get("category"):
            if r["category"] != category: continue
            score += 1
        if score > best_score:
            best_score, best = score, r
    if best: return int(best.get("threshold", APPROVAL_THRESHOLD))
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    return int((org or {}).get("default_threshold", APPROVAL_THRESHOLD))

# ---------- Auth ----------
@api.post("/auth/signup")
async def signup(inp: SignupIn):
    existing = await db.users.find_one({"email": inp.email.lower()})
    if existing:
        raise HTTPException(400, "Email already registered")
    org_id = new_id()
    user_id = new_id()
    await db.organizations.insert_one({
        "id": org_id, "name": inp.org_name, "owner_id": user_id,
        "created_at": now_iso()
    })
    await db.users.insert_one({
        "id": user_id, "org_id": org_id, "email": inp.email.lower(),
        "name": inp.name, "role": "org_admin",
        "password_hash": hash_pw(inp.password),
        "created_at": now_iso(), "active": True
    })
    token = make_token(user_id, org_id, "org_admin")
    return {"token": token, "user": {"id": user_id, "email": inp.email.lower(), "name": inp.name, "role": "org_admin", "org_id": org_id, "org_name": inp.org_name}}

@api.post("/auth/login")
async def login(inp: LoginIn):
    user = await db.users.find_one({"email": inp.email.lower()})
    if not user or not check_pw(inp.password, user["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    if not user.get("active", True):
        raise HTTPException(403, "Account disabled")
    org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0})
    token = make_token(user["id"], user["org_id"], user["role"])
    return {"token": token, "user": {"id": user["id"], "email": user["email"], "name": user["name"], "role": user["role"], "org_id": user["org_id"], "org_name": org["name"] if org else ""}}

@api.get("/auth/me")
async def me(user=Depends(current_user)):
    org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0})
    return {**user, "org_name": org["name"] if org else ""}

# ---------- Users ----------
@api.get("/users")
async def list_users(user=Depends(require_role("org_admin", "manager"))):
    users = await db.users.find({"org_id": user["org_id"]}, {"_id": 0, "password_hash": 0}).to_list(1000)
    return users

@api.post("/users")
async def create_user(inp: UserCreate, user=Depends(require_role("org_admin"))):
    if await db.users.find_one({"email": inp.email.lower()}):
        raise HTTPException(400, "Email exists")
    u = {"id": new_id(), "org_id": user["org_id"], "email": inp.email.lower(),
         "name": inp.name, "role": inp.role, "password_hash": hash_pw(inp.password),
         "created_at": now_iso(), "active": True}
    await db.users.insert_one(u)
    await audit(user, "create", "user", u["id"], after={"email": u["email"], "role": u["role"]})
    return {k: v for k, v in u.items() if k not in ("password_hash", "_id")}

@api.delete("/users/{uid}")
async def delete_user(uid: str, user=Depends(require_role("org_admin"))):
    if uid == user["id"]:
        raise HTTPException(400, "Cannot delete self")
    await db.users.update_one({"id": uid, "org_id": user["org_id"]}, {"$set": {"active": False}})
    await audit(user, "deactivate", "user", uid)
    return {"ok": True}

# ---------- Warehouses & Locations ----------
@api.get("/warehouses")
async def list_warehouses(user=Depends(current_user)):
    return await db.warehouses.find({"org_id": user["org_id"]}, {"_id": 0}).to_list(1000)

@api.post("/warehouses")
async def create_warehouse(inp: WarehouseIn, user=Depends(require_role("org_admin", "manager"))):
    w = {"id": new_id(), "org_id": user["org_id"], **inp.model_dump(), "created_at": now_iso()}
    await db.warehouses.insert_one(w)
    await audit(user, "create", "warehouse", w["id"], after=inp.model_dump())
    return {k: v for k, v in w.items() if k != "_id"}

@api.get("/locations")
async def list_locations(warehouse_id: Optional[str] = None, user=Depends(current_user)):
    q = {"org_id": user["org_id"]}
    if warehouse_id: q["warehouse_id"] = warehouse_id
    return await db.locations.find(q, {"_id": 0}).to_list(5000)

@api.post("/locations")
async def create_location(inp: LocationIn, user=Depends(require_role("org_admin", "manager"))):
    loc = {"id": new_id(), "org_id": user["org_id"], **inp.model_dump(), "created_at": now_iso()}
    await db.locations.insert_one(loc)
    return {k: v for k, v in loc.items() if k != "_id"}

# ---------- Products ----------
@api.get("/products")
async def list_products(q: Optional[str] = None, limit: int = 100, user=Depends(current_user)):
    query = {"org_id": user["org_id"]}
    if q:
        query["$or"] = [
            {"name": {"$regex": q, "$options": "i"}},
            {"sku": {"$regex": q, "$options": "i"}},
            {"barcode": q},
            {"brand": {"$regex": q, "$options": "i"}},
            {"model_number": {"$regex": q, "$options": "i"}},
            {"category": {"$regex": q, "$options": "i"}},
        ]
    return await db.products.find(query, {"_id": 0}).limit(limit).to_list(limit)

@api.post("/products")
async def create_product(inp: ProductIn, user=Depends(require_role("org_admin", "manager"))):
    if await db.products.find_one({"org_id": user["org_id"], "sku": inp.sku}):
        raise HTTPException(400, "SKU already exists")
    p = {"id": new_id(), "org_id": user["org_id"], **inp.model_dump(), "created_at": now_iso()}
    await db.products.insert_one(p)
    await audit(user, "create", "product", p["id"], after={"sku": p["sku"], "name": p["name"]})
    return {k: v for k, v in p.items() if k != "_id"}

@api.get("/products/{pid}")
async def get_product(pid: str, user=Depends(current_user)):
    p = await db.products.find_one({"id": pid, "org_id": user["org_id"]}, {"_id": 0})
    if not p: raise HTTPException(404, "Not found")
    inv = await db.inventory.find({"product_id": pid, "org_id": user["org_id"]}, {"_id": 0}).to_list(100)
    for i in inv:
        wh = await db.warehouses.find_one({"id": i["warehouse_id"]}, {"_id": 0})
        i["warehouse_name"] = wh["name"] if wh else ""
        if i.get("location_id"):
            loc = await db.locations.find_one({"id": i["location_id"]}, {"_id": 0})
            i["location_path"] = await build_location_path(loc) if loc else ""
    return {"product": p, "inventory": inv}

async def build_location_path(loc: Dict) -> str:
    parts = [f"{loc['type'].title()} {loc['code']}"]
    current = loc
    while current.get("parent_id"):
        parent = await db.locations.find_one({"id": current["parent_id"]}, {"_id": 0})
        if not parent: break
        parts.insert(0, f"{parent['type'].title()} {parent['code']}")
        current = parent
    wh = await db.warehouses.find_one({"id": loc["warehouse_id"]}, {"_id": 0})
    if wh: parts.insert(0, wh["name"])
    return " → ".join(parts)

# ---------- Inventory ----------
@api.get("/inventory")
async def list_inventory(low_stock: bool = False, user=Depends(current_user)):
    q = {"org_id": user["org_id"]}
    inv = await db.inventory.find(q, {"_id": 0}).to_list(2000)
    if low_stock:
        inv = [i for i in inv if i["quantity"] <= i.get("reorder_level", 10)]
    for i in inv:
        p = await db.products.find_one({"id": i["product_id"]}, {"_id": 0})
        w = await db.warehouses.find_one({"id": i["warehouse_id"]}, {"_id": 0})
        i["product"] = p
        i["warehouse_name"] = w["name"] if w else ""
        i["available_quantity"] = i["quantity"] - i.get("reserved_quantity", 0)
    return inv

@api.post("/inventory")
async def create_inventory(inp: InventoryIn, user=Depends(require_role("org_admin", "manager"))):
    inv = {"id": new_id(), "org_id": user["org_id"], **inp.model_dump(), "updated_at": now_iso()}
    await db.inventory.insert_one(inv)
    return {k: v for k, v in inv.items() if k != "_id"}

async def apply_adjust(user: Dict, inventory_id: str, new_qty: int, reason: str) -> Dict:
    inv = await db.inventory.find_one({"id": inventory_id, "org_id": user["org_id"]}, {"_id": 0})
    if not inv: raise HTTPException(404, "Inventory not found")
    before = inv["quantity"]
    await db.inventory.update_one({"id": inventory_id}, {"$set": {"quantity": new_qty, "updated_at": now_iso()}})
    await db.inventory_transactions.insert_one({
        "id": new_id(), "org_id": user["org_id"], "inventory_id": inventory_id,
        "product_id": inv["product_id"], "type": "adjustment",
        "before_qty": before, "after_qty": new_qty, "reason": reason,
        "user_id": user["id"], "timestamp": now_iso()
    })
    await audit(user, "adjust", "inventory", inventory_id, before={"qty": before}, after={"qty": new_qty}, reason=reason)
    return {"before": before, "after": new_qty}

@api.post("/inventory/adjust")
async def adjust_inventory(inp: InventoryAdjust, user=Depends(require_role("org_admin", "manager", "worker"))):
    inv = await db.inventory.find_one({"id": inp.inventory_id, "org_id": user["org_id"]}, {"_id": 0})
    if not inv: raise HTTPException(404, "Inventory not found")
    delta = abs(inp.new_quantity - inv["quantity"])
    prod = await db.products.find_one({"id": inv["product_id"]}, {"_id": 0, "name": 1, "sku": 1, "category": 1})
    threshold = await resolve_threshold(user["org_id"], inv["warehouse_id"], (prod or {}).get("category"))
    if user["role"] == "worker" and delta > threshold:
        wh = await db.warehouses.find_one({"id": inv["warehouse_id"]}, {"_id": 0, "name": 1})
        req = {
            "id": new_id(), "org_id": user["org_id"], "type": "inventory_adjust",
            "status": "pending", "requested_by": user["id"], "requested_by_name": user["name"],
            "product_name": prod["name"] if prod else "", "product_sku": prod["sku"] if prod else "",
            "warehouse_name": wh["name"] if wh else "",
            "payload": {"inventory_id": inp.inventory_id, "new_quantity": inp.new_quantity, "current": inv["quantity"], "delta": delta, "threshold_at_request": threshold},
            "reason": inp.reason, "created_at": now_iso(), "resolved_at": None, "resolved_by": None
        }
        await db.approvals.insert_one(req)
        await audit(user, "request", "approval", req["id"], after=req["payload"], reason=inp.reason)
        return {"ok": True, "approval_required": True, "approval_id": req["id"], "threshold": threshold, "before": inv["quantity"], "after": inp.new_quantity}
    res = await apply_adjust(user, inp.inventory_id, inp.new_quantity, inp.reason)
    return {"ok": True, "approval_required": False, "threshold": threshold, **res}

# ---------- Approvals ----------
@api.get("/approvals")
async def list_approvals(status_filter: str = "pending", user=Depends(current_user)):
    q = {"org_id": user["org_id"], "status": status_filter}
    return await db.approvals.find(q, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)

@api.post("/approvals/{aid}/approve")
async def approve(aid: str, inp: ApprovalDecision, user=Depends(require_role("org_admin", "manager"))):
    req = await db.approvals.find_one({"id": aid, "org_id": user["org_id"], "status": "pending"}, {"_id": 0})
    if not req: raise HTTPException(404, "Not found or already resolved")
    if req["type"] == "inventory_adjust":
        p = req["payload"]
        await apply_adjust(user, p["inventory_id"], p["new_quantity"], f"[Approved by {user['name']}] {req.get('reason', '')} {inp.reason or ''}")
    await db.approvals.update_one({"id": aid}, {"$set": {"status": "approved", "resolved_at": now_iso(), "resolved_by": user["name"], "resolver_note": inp.reason or ""}})
    await audit(user, "approve", "approval", aid, reason=inp.reason or "")
    return {"ok": True}

@api.post("/approvals/{aid}/reject")
async def reject(aid: str, inp: ApprovalDecision, user=Depends(require_role("org_admin", "manager"))):
    req = await db.approvals.find_one({"id": aid, "org_id": user["org_id"], "status": "pending"}, {"_id": 0})
    if not req: raise HTTPException(404, "Not found or already resolved")
    await db.approvals.update_one({"id": aid}, {"$set": {"status": "rejected", "resolved_at": now_iso(), "resolved_by": user["name"], "resolver_note": inp.reason or ""}})
    await audit(user, "reject", "approval", aid, reason=inp.reason or "")
    return {"ok": True}

# ---------- Voice (Whisper) ----------
@api.post("/voice/transcribe")
async def voice_transcribe(file: UploadFile = File(...), language: Optional[str] = Form(None), user=Depends(current_user)):
    content = await file.read()
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(400, "File too large (>25MB)")
    stt = OpenAISpeechToText(api_key=EMERGENT_LLM_KEY)
    audio = io.BytesIO(content)
    audio.name = file.filename or "voice.webm"
    try:
        resp = await stt.transcribe(
            file=audio, model="whisper-1", response_format="json",
            language=language if language else None,
            prompt="Warehouse inventory query. May mention SKUs, product names, brands, warehouse locations."
        )
        return {"text": resp.text}
    except Exception as e:
        log.error(f"transcribe error: {e}")
        raise HTTPException(500, str(e))

# ---------- Barcode / QR label PDF ----------
@api.get("/products/{pid}/label")
async def product_label(pid: str, count: int = 6, kind: str = "barcode", price: Optional[str] = None, expiry: Optional[str] = None, user=Depends(current_user)):
    p = await db.products.find_one({"id": pid, "org_id": user["org_id"]}, {"_id": 0})
    if not p: raise HTTPException(404, "Not found")
    org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0, "name": 1}) or {}
    tpl = await db.label_templates.find_one({"org_id": user["org_id"]}, {"_id": 0}) or {}
    org_line = (tpl.get("org_line") or org.get("name") or "AIW")[:40]
    show_brand = tpl.get("show_brand", True)
    show_sku = tpl.get("show_sku", True)
    show_price = tpl.get("show_price", False) and price
    show_expiry = tpl.get("show_expiry", False) and expiry
    footer = (tpl.get("footer") or "").strip()
    count = max(1, min(count, 40))
    code_value = p.get("barcode") or p["sku"]

    def make_code_img() -> io.BytesIO:
        out = io.BytesIO()
        if kind == "qr":
            qr = qrcode_lib.QRCode(box_size=6, border=2)
            qr.add_data(code_value); qr.make(fit=True)
            qr.make_image(fill_color="black", back_color="white").save(out, format="PNG")
        else:
            bc_cls = barcode_lib.get_barcode_class("code128")
            bc = bc_cls(code_value, writer=ImageWriter())
            bc.write(out, options={"module_height": 10.0, "font_size": 8, "text_distance": 3.0, "quiet_zone": 2.0, "write_text": True})
        out.seek(0); return out

    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    label_w, label_h = 90 * mm, 45 * mm
    cols, rows = 2, 5
    per_page = cols * rows
    gap_x, gap_y = 5 * mm, 5 * mm
    margin_x = (W - cols * label_w - (cols - 1) * gap_x) / 2
    margin_y = 15 * mm

    for i in range(count):
        if i > 0 and i % per_page == 0:
            c.showPage()
        col = i % cols
        row = (i // cols) % rows
        x = margin_x + col * (label_w + gap_x)
        y = H - margin_y - (row + 1) * label_h - row * gap_y
        c.setStrokeColorRGB(0.75, 0.75, 0.75)
        c.setLineWidth(0.5)
        c.rect(x, y, label_w, label_h)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(x + 5, y + label_h - 12, org_line)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(x + 5, y + label_h - 26, p["name"][:32])
        c.setFont("Helvetica", 8)
        line_y = y + label_h - 38
        if show_sku:
            c.drawString(x + 5, line_y, f"SKU {p['sku']}"); line_y -= 10
        if show_price:
            c.setFont("Helvetica-Bold", 10)
            c.drawString(x + 5, line_y, f"₹ {price}")
            c.setFont("Helvetica", 8); line_y -= 12
        if show_expiry:
            c.drawString(x + 5, line_y, f"EXP {expiry}"); line_y -= 10
        if show_brand and p.get("brand"):
            c.drawString(x + 5, y + 6, p["brand"][:32])
        if footer:
            c.setFont("Helvetica-Oblique", 6)
            c.drawString(x + 5, y + 2, footer[:60])
        img = ImageReader(make_code_img())
        img_w = 42 * mm
        img_h = label_h - 12
        c.drawImage(img, x + label_w - img_w - 4, y + 6, width=img_w, height=img_h, preserveAspectRatio=True, mask="auto")

    c.save()
    buf.seek(0)
    return StreamingResponse(io.BytesIO(buf.getvalue()), media_type="application/pdf",
                             headers={"Content-Disposition": f'inline; filename="labels-{p["sku"]}.pdf"'})

# ---------- ERP Connectors ----------
async def connector_fetch(c: Dict, limit: int = 1000) -> List[Dict]:
    kind = c["kind"]; cfg = c.get("config", {}) or {}
    fmap = cfg.get("field_map", {}) or {}
    def apply_map(row: Dict) -> Dict:
        row_l = {str(k).lower(): v for k, v in row.items()}
        if not fmap:
            return {k: row_l.get(k) for k in ["sku", "name", "barcode", "brand", "category", "model_number", "description"]}
        return {std: row_l.get(str(src).lower()) for std, src in fmap.items() if src}
    if kind == "rest":
        if not cfg.get("url"): raise ValueError("Missing 'url' in config")
        headers = {}
        if cfg.get("auth_header") and cfg.get("auth_value"):
            headers[cfg["auth_header"]] = cfg["auth_value"]
        r = ext_requests.get(cfg["url"], headers=headers, timeout=20)
        r.raise_for_status()
        data = r.json()
        path = (cfg.get("data_path") or "").strip()
        for step in [s for s in path.split(".") if s]:
            data = data.get(step) if isinstance(data, dict) else None
        if not isinstance(data, list):
            raise ValueError("REST endpoint must return (or point to) a JSON array")
        return [apply_map(row) for row in data[:limit] if isinstance(row, dict)]
    if kind in ("postgresql", "mysql"):
        for req_k in ("host", "user", "password", "database"):
            if not cfg.get(req_k): raise ValueError(f"Missing '{req_k}' in config")
        if kind == "postgresql":
            url = f"postgresql+psycopg2://{cfg['user']}:{cfg['password']}@{cfg['host']}:{cfg.get('port', 5432)}/{cfg['database']}"
        else:
            url = f"mysql+pymysql://{cfg['user']}:{cfg['password']}@{cfg['host']}:{cfg.get('port', 3306)}/{cfg['database']}"
        engine = create_engine(url, connect_args={"connect_timeout": 10} if kind == "postgresql" else {"connect_timeout": 10})
        query = cfg.get("query") or f"SELECT * FROM {cfg.get('table', 'products')} LIMIT {limit}"
        with engine.connect() as conn:
            res = conn.execute(sa_text(query))
            rows = [dict(r._mapping) for r in res.fetchall()]
        return [apply_map(r) for r in rows[:limit]]
    raise ValueError(f"Unknown connector kind: {kind}")

@api.get("/connectors")
async def list_connectors(user=Depends(require_role("org_admin"))):
    items = await db.connectors.find({"org_id": user["org_id"]}, {"_id": 0}).to_list(200)
    # Hide password fields in responses
    for it in items:
        cfg = it.get("config") or {}
        if "password" in cfg: cfg["password"] = "••••••" if cfg["password"] else ""
        if "auth_value" in cfg: cfg["auth_value"] = "••••••" if cfg["auth_value"] else ""
    return items

@api.post("/connectors")
async def create_connector(inp: ConnectorIn, user=Depends(require_role("org_admin"))):
    c = {"id": new_id(), "org_id": user["org_id"], **inp.model_dump(), "active": False, "last_sync": None, "webhook_token": secrets.token_urlsafe(24), "created_at": now_iso()}
    await db.connectors.insert_one(c)
    await audit(user, "create", "connector", c["id"], after={"name": c["name"], "kind": c["kind"]})
    return {k: v for k, v in c.items() if k != "_id"}

@api.delete("/connectors/{cid}")
async def delete_connector(cid: str, user=Depends(require_role("org_admin"))):
    await db.connectors.delete_one({"id": cid, "org_id": user["org_id"]})
    await audit(user, "delete", "connector", cid)
    return {"ok": True}

@api.post("/connectors/{cid}/test")
async def test_connector(cid: str, user=Depends(require_role("org_admin"))):
    c = await db.connectors.find_one({"id": cid, "org_id": user["org_id"]}, {"_id": 0})
    if not c: raise HTTPException(404, "Not found")
    try:
        sample = await connector_fetch(c, limit=3)
        return {"ok": True, "sample": sample, "count": len(sample)}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@api.post("/connectors/{cid}/sync")
async def sync_connector(cid: str, user=Depends(require_role("org_admin"))):
    c = await db.connectors.find_one({"id": cid, "org_id": user["org_id"]}, {"_id": 0})
    if not c: raise HTTPException(404, "Not found")
    try:
        rows = await connector_fetch(c, limit=2000)
    except Exception as e:
        raise HTTPException(400, f"Fetch failed: {e}")
    imported, updated, skipped = 0, 0, 0
    for row in rows:
        sku = str(row.get("sku") or "").strip()
        name = str(row.get("name") or "").strip()
        if not sku or not name:
            skipped += 1; continue
        base = {
            "name": name,
            "barcode": str(row.get("barcode") or ""), "brand": str(row.get("brand") or ""),
            "category": str(row.get("category") or ""), "model_number": str(row.get("model_number") or ""),
            "description": str(row.get("description") or "")
        }
        existing = await db.products.find_one({"org_id": user["org_id"], "sku": sku})
        if existing:
            await db.products.update_one({"id": existing["id"]}, {"$set": base})
            updated += 1
        else:
            await db.products.insert_one({"id": new_id(), "org_id": user["org_id"], "sku": sku, **base, "image_url": "", "attributes": {}, "created_at": now_iso()})
            imported += 1
    await db.connectors.update_one({"id": cid}, {"$set": {"last_sync": now_iso(), "active": True}})
    await audit(user, "sync", "connector", cid, after={"imported": imported, "updated": updated, "skipped": skipped})
    return {"imported": imported, "updated": updated, "skipped": skipped}

@api.post("/inventory/transfer")
async def transfer_inventory(inp: InventoryTransfer, user=Depends(require_role("org_admin", "manager"))):
    src = await db.inventory.find_one({"org_id": user["org_id"], "product_id": inp.product_id, "warehouse_id": inp.from_warehouse_id}, {"_id": 0})
    if not src or src["quantity"] < inp.quantity:
        raise HTTPException(400, "Insufficient stock in source")
    dst = await db.inventory.find_one({"org_id": user["org_id"], "product_id": inp.product_id, "warehouse_id": inp.to_warehouse_id}, {"_id": 0})
    await db.inventory.update_one({"id": src["id"]}, {"$set": {"quantity": src["quantity"] - inp.quantity, "updated_at": now_iso()}})
    if dst:
        await db.inventory.update_one({"id": dst["id"]}, {"$set": {"quantity": dst["quantity"] + inp.quantity, "location_id": inp.to_location_id or dst.get("location_id"), "updated_at": now_iso()}})
    else:
        await db.inventory.insert_one({"id": new_id(), "org_id": user["org_id"], "product_id": inp.product_id, "warehouse_id": inp.to_warehouse_id, "location_id": inp.to_location_id, "quantity": inp.quantity, "reserved_quantity": 0, "reorder_level": 10, "updated_at": now_iso()})
    await audit(user, "transfer", "inventory", src["id"], after={"qty": inp.quantity, "from": inp.from_warehouse_id, "to": inp.to_warehouse_id}, reason=inp.reason)
    return {"ok": True}

# ---------- Scan ----------
@api.get("/scan/barcode/{barcode}")
async def scan_barcode(barcode: str, user=Depends(current_user)):
    p = await db.products.find_one({"org_id": user["org_id"], "barcode": barcode}, {"_id": 0})
    if not p: raise HTTPException(404, "Product not found")
    inv = await db.inventory.find({"product_id": p["id"], "org_id": user["org_id"]}, {"_id": 0}).to_list(50)
    for i in inv:
        wh = await db.warehouses.find_one({"id": i["warehouse_id"]}, {"_id": 0})
        i["warehouse_name"] = wh["name"] if wh else ""
        if i.get("location_id"):
            loc = await db.locations.find_one({"id": i["location_id"]}, {"_id": 0})
            i["location_path"] = await build_location_path(loc) if loc else ""
    return {"product": p, "inventory": inv}

@api.post("/scan/image")
async def scan_image(inp: ImageScanIn, user=Depends(current_user)):
    """Send image to Gemini for product identification, then search catalog."""
    products = await db.products.find({"org_id": user["org_id"]}, {"_id": 0, "name": 1, "sku": 1, "brand": 1, "category": 1, "model_number": 1}).to_list(500)
    catalog_hint = "\n".join([f"- {p['name']} (SKU: {p['sku']}, Brand: {p.get('brand','')}, Model: {p.get('model_number','')})" for p in products[:100]])
    chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"scan-{new_id()}",
                   system_message=f"""You are a product identification assistant for a warehouse. You will be shown an image and must identify the product.
Your organization's catalog contains these products:
{catalog_hint}

Respond ONLY in strict JSON:
{{"identified_name": "...", "brand": "...", "model_number": "...", "category": "...", "confidence": 0.0-1.0, "matched_sku": "sku_if_matches_catalog_else_null", "notes": "brief description"}}""").with_model("gemini", "gemini-3-flash-preview")
    img = ImageContent(image_base64=inp.image_base64)
    try:
        resp = await chat.send_message(UserMessage(text="Identify this product from the image. Match against the catalog if possible.", file_contents=[img]))
        text = resp.strip()
        if text.startswith("```"):
            text = text.split("```")[1].replace("json", "", 1).strip()
        result = json.loads(text)
    except Exception as e:
        log.error(f"Image scan error: {e}")
        return {"error": str(e), "identified_name": "Unknown", "confidence": 0}
    matches = []
    if result.get("matched_sku"):
        p = await db.products.find_one({"org_id": user["org_id"], "sku": result["matched_sku"]}, {"_id": 0})
        if p: matches.append({"product": p, "confidence": result.get("confidence", 0.8)})
    if not matches and result.get("identified_name"):
        q = result["identified_name"]
        found = await db.products.find({"org_id": user["org_id"], "$or": [
            {"name": {"$regex": q, "$options": "i"}},
            {"brand": {"$regex": result.get("brand", ""), "$options": "i"}} if result.get("brand") else {"_id": None},
        ]}, {"_id": 0}).limit(3).to_list(3)
        for f in found:
            matches.append({"product": f, "confidence": 0.6})
    return {"identification": result, "matches": matches}

# ---------- AI Chat with tools ----------
async def tool_search_product(user: Dict, args: Dict) -> Dict:
    q = args.get("query", "")
    results = await db.products.find({"org_id": user["org_id"], "$or": [
        {"name": {"$regex": q, "$options": "i"}},
        {"sku": {"$regex": q, "$options": "i"}},
        {"brand": {"$regex": q, "$options": "i"}},
        {"model_number": {"$regex": q, "$options": "i"}},
    ]}, {"_id": 0}).limit(5).to_list(5)
    return {"products": results, "count": len(results)}

async def tool_get_inventory(user: Dict, args: Dict) -> Dict:
    sku = args.get("sku")
    p = await db.products.find_one({"org_id": user["org_id"], "sku": sku}, {"_id": 0})
    if not p: return {"error": f"No product with SKU {sku}"}
    inv = await db.inventory.find({"product_id": p["id"], "org_id": user["org_id"]}, {"_id": 0}).to_list(50)
    total = sum(i["quantity"] for i in inv)
    available = sum(i["quantity"] - i.get("reserved_quantity", 0) for i in inv)
    locations = []
    for i in inv:
        wh = await db.warehouses.find_one({"id": i["warehouse_id"]}, {"_id": 0})
        path = ""
        if i.get("location_id"):
            loc = await db.locations.find_one({"id": i["location_id"]}, {"_id": 0})
            path = await build_location_path(loc) if loc else ""
        locations.append({"warehouse": wh["name"] if wh else "", "path": path, "quantity": i["quantity"], "available": i["quantity"] - i.get("reserved_quantity", 0)})
    return {"product_name": p["name"], "sku": sku, "total_quantity": total, "available": available, "locations": locations}

async def tool_find_product_location(user: Dict, args: Dict) -> Dict:
    q = args.get("product_query", "")
    p = await db.products.find_one({"org_id": user["org_id"], "$or": [
        {"name": {"$regex": q, "$options": "i"}}, {"sku": {"$regex": q, "$options": "i"}}, {"barcode": q}
    ]}, {"_id": 0})
    if not p: return {"error": f"Not found: {q}"}
    return await tool_get_inventory(user, {"sku": p["sku"]})

async def tool_get_low_stock(user: Dict, args: Dict) -> Dict:
    inv = await db.inventory.find({"org_id": user["org_id"]}, {"_id": 0}).to_list(2000)
    low = [i for i in inv if i["quantity"] <= i.get("reorder_level", 10)]
    out = []
    for i in low[:20]:
        p = await db.products.find_one({"id": i["product_id"]}, {"_id": 0, "name": 1, "sku": 1})
        out.append({"product": p["name"] if p else "?", "sku": p["sku"] if p else "?", "quantity": i["quantity"], "reorder_level": i.get("reorder_level", 10)})
    return {"low_stock_items": out, "count": len(low)}

AI_TOOLS = [
    {"type": "function", "function": {"name": "search_product", "description": "Search products by name, SKU, brand, or model", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "get_inventory", "description": "Get inventory levels and locations for a specific SKU", "parameters": {"type": "object", "properties": {"sku": {"type": "string"}}, "required": ["sku"]}}},
    {"type": "function", "function": {"name": "find_product_location", "description": "Find where a product is stored", "parameters": {"type": "object", "properties": {"product_query": {"type": "string"}}, "required": ["product_query"]}}},
    {"type": "function", "function": {"name": "get_low_stock", "description": "List products with low stock", "parameters": {"type": "object", "properties": {}}}},
]

TOOL_DISPATCH = {
    "search_product": tool_search_product,
    "get_inventory": tool_get_inventory,
    "find_product_location": tool_find_product_location,
    "get_low_stock": tool_get_low_stock,
}

@api.post("/ai/chat")
async def ai_chat(inp: ChatIn, user=Depends(current_user)):
    session_id = inp.session_id or new_id()
    model_map = {"claude": ("anthropic", "claude-sonnet-4-6"), "gemini": ("gemini", "gemini-3-flash-preview")}
    provider, model = model_map[inp.model]
    system_msg = f"""You are AI Inventory Worker, an assistant for {user['name']} at organization {user['org_id']}.
Help users find products, check inventory, locate items in warehouses, and get low stock alerts.
Always use the provided tools to answer questions. Never invent data. Respond concisely and clearly.
When showing locations, format them as: Warehouse → Zone → Aisle → Rack → Shelf → Bin.
User role: {user['role']}. Organization has strict data isolation."""

    chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=session_id, system_message=system_msg).with_model(provider, model).with_tools(AI_TOOLS, tool_choice="auto")
    user_msg = UserMessage(text=inp.message)

    async def event_gen():
        nonlocal user_msg
        try:
            while True:
                pending = []
                async for ev in chat.stream_message(user_msg):
                    if isinstance(ev, TextDelta):
                        yield f"data: {json.dumps({'type':'text','content':ev.content})}\n\n"
                    elif isinstance(ev, ToolCallStart):
                        yield f"data: {json.dumps({'type':'tool_start','name':ev.name})}\n\n"
                    elif isinstance(ev, ToolCallReady):
                        pending.append(ev.tool_call)
                    elif isinstance(ev, StreamDone):
                        break
                if not pending:
                    break
                for tc in pending:
                    fn = TOOL_DISPATCH.get(tc.name)
                    result = await fn(user, tc.arguments) if fn else {"error": "unknown tool"}
                    yield f"data: {json.dumps({'type':'tool_result','name':tc.name,'result':result})}\n\n"
                    chat.add_tool_result(tc.id, json.dumps(result))
                user_msg = None
            yield f"data: {json.dumps({'type':'done','session_id':session_id})}\n\n"
            await db.ai_messages.insert_one({"id": new_id(), "org_id": user["org_id"], "user_id": user["id"], "session_id": session_id, "message": inp.message, "timestamp": now_iso()})
        except Exception as e:
            log.error(f"chat error: {e}")
            yield f"data: {json.dumps({'type':'error','error':str(e)})}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# ---------- CSV Import ----------
@api.post("/import/products")
async def import_products(file: UploadFile = File(...), user=Depends(require_role("org_admin", "manager"))):
    content = await file.read()
    try:
        if file.filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        else:
            df = pd.read_excel(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(400, f"Parse error: {e}")
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    imported, skipped, errors = 0, 0, []
    for idx, row in df.iterrows():
        try:
            sku = str(row.get("sku") or row.get("item_code") or "").strip()
            name = str(row.get("name") or row.get("product_name") or row.get("item_name") or "").strip()
            if not sku or not name:
                skipped += 1; continue
            if await db.products.find_one({"org_id": user["org_id"], "sku": sku}):
                skipped += 1; continue
            p = {"id": new_id(), "org_id": user["org_id"], "sku": sku, "name": name,
                 "barcode": str(row.get("barcode") or ""), "brand": str(row.get("brand") or ""),
                 "category": str(row.get("category") or ""), "model_number": str(row.get("model_number") or row.get("model") or ""),
                 "description": str(row.get("description") or ""), "image_url": str(row.get("image_url") or ""),
                 "attributes": {}, "created_at": now_iso()}
            await db.products.insert_one(p)
            imported += 1
        except Exception as e:
            errors.append(f"Row {idx}: {e}")
    await audit(user, "import", "products", "bulk", after={"imported": imported, "skipped": skipped})
    return {"imported": imported, "skipped": skipped, "errors": errors[:10]}

# ---------- Dashboard ----------
@api.get("/dashboard/stats")
async def dashboard_stats(user=Depends(current_user)):
    org = user["org_id"]
    total_products = await db.products.count_documents({"org_id": org})
    total_warehouses = await db.warehouses.count_documents({"org_id": org})
    inv = await db.inventory.find({"org_id": org}, {"_id": 0}).to_list(5000)
    total_units = sum(i["quantity"] for i in inv)
    low_stock = len([i for i in inv if i["quantity"] <= i.get("reorder_level", 10)])
    out_of_stock = len([i for i in inv if i["quantity"] == 0])
    recent_scans = await db.ai_messages.count_documents({"org_id": org})
    recent_audit = await db.audit_logs.find({"org_id": org}, {"_id": 0}).sort("timestamp", -1).limit(8).to_list(8)
    # Stock by warehouse
    wh_stock = {}
    for i in inv:
        wh = await db.warehouses.find_one({"id": i["warehouse_id"]}, {"_id": 0, "name": 1})
        if wh:
            wh_stock[wh["name"]] = wh_stock.get(wh["name"], 0) + i["quantity"]
    return {
        "total_products": total_products, "total_warehouses": total_warehouses,
        "total_units": total_units, "low_stock": low_stock, "out_of_stock": out_of_stock,
        "recent_ai_queries": recent_scans, "recent_activity": recent_audit,
        "stock_by_warehouse": [{"name": k, "units": v} for k, v in wh_stock.items()]
    }

# ---------- Audit Logs ----------
@api.get("/audit-logs")
async def get_audit_logs(limit: int = 100, user=Depends(require_role("org_admin", "manager"))):
    return await db.audit_logs.find({"org_id": user["org_id"]}, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)

# ---------- Realtime: Webhooks + Cron polling ----------
async def _apply_records(org_id: str, fmap: Dict, records: List[Dict]) -> Dict:
    imported, updated, skipped = 0, 0, 0
    for row in records:
        if not isinstance(row, dict):
            skipped += 1; continue
        row_l = {str(k).lower(): v for k, v in row.items()}
        mapped = {std: row_l.get(str(src).lower()) for std, src in (fmap or {}).items() if src} if fmap else row_l
        sku = str(mapped.get("sku") or "").strip()
        name = str(mapped.get("name") or "").strip()
        if not sku or not name:
            skipped += 1; continue
        base = {"name": name, "barcode": str(mapped.get("barcode") or ""), "brand": str(mapped.get("brand") or ""),
                "category": str(mapped.get("category") or ""), "model_number": str(mapped.get("model_number") or ""),
                "description": str(mapped.get("description") or "")}
        existing = await db.products.find_one({"org_id": org_id, "sku": sku})
        if existing:
            await db.products.update_one({"id": existing["id"]}, {"$set": base})
            updated += 1
        else:
            await db.products.insert_one({"id": new_id(), "org_id": org_id, "sku": sku, **base, "image_url": "", "attributes": {}, "created_at": now_iso()})
            imported += 1
    return {"imported": imported, "updated": updated, "skipped": skipped}

@api.post("/webhooks/connectors/{cid}/{token}")
async def connector_webhook(cid: str, token: str, payload: Any = Body(...)):
    c = await db.connectors.find_one({"id": cid, "webhook_token": token}, {"_id": 0})
    if not c: raise HTTPException(404, "Invalid webhook")
    records = payload.get("records") if isinstance(payload, dict) and "records" in payload else (payload if isinstance(payload, list) else None)
    if not isinstance(records, list):
        raise HTTPException(400, "Payload must be an array or {records: [...]}")
    fmap = (c.get("config") or {}).get("field_map") or {}
    res = await _apply_records(c["org_id"], fmap, records)
    await db.connectors.update_one({"id": cid}, {"$set": {"last_sync": now_iso(), "active": True}})
    return {"ok": True, **res}

async def _run_all_connector_syncs():
    active = await db.connectors.find({"active": True}, {"_id": 0}).to_list(500)
    for c in active:
        try:
            rows = await connector_fetch(c, limit=2000)
            fmap_pass = None if fmap_already_applied_in_fetch() else (c.get("config") or {}).get("field_map")
            res = await _apply_records(c["org_id"], fmap_pass, rows)
            await db.connectors.update_one({"id": c["id"]}, {"$set": {"last_sync": now_iso()}})
            log.info(f"cron synced {c['name']}: {res}")
        except Exception as e:
            log.error(f"cron sync failed {c.get('name')}: {e}")

def fmap_already_applied_in_fetch() -> bool:
    return True  # connector_fetch already applies field_map

@api.post("/cron/sync-connectors")
async def cron_sync_connectors(request: Request):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or not secrets.compare_digest(auth[7:], WEBHOOK_CRON_SECRET):
        raise HTTPException(401, "unauthorized")
    asyncio.create_task(_run_all_connector_syncs())
    return {"ok": True, "queued": True}

# ---------- Label templates ----------
@api.get("/label-template")
async def get_label_template(user=Depends(current_user)):
    t = await db.label_templates.find_one({"org_id": user["org_id"]}, {"_id": 0})
    if not t:
        return {"org_line": "", "logo_url": "", "show_brand": True, "show_sku": True, "show_price": False, "show_expiry": False, "footer": ""}
    return t

@api.put("/label-template")
async def put_label_template(inp: LabelTemplateIn, user=Depends(require_role("org_admin", "manager"))):
    doc = {"org_id": user["org_id"], **inp.model_dump(), "updated_at": now_iso()}
    await db.label_templates.update_one({"org_id": user["org_id"]}, {"$set": doc}, upsert=True)
    await audit(user, "update", "label_template", user["org_id"], after=inp.model_dump())
    return {"ok": True}

# ---------- Approval rules ----------
@api.get("/approval-rules")
async def list_approval_rules(user=Depends(current_user)):
    rules = await db.approval_rules.find({"org_id": user["org_id"]}, {"_id": 0}).to_list(200)
    org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0}) or {}
    return {"rules": rules, "default_threshold": org.get("default_threshold", APPROVAL_THRESHOLD)}

@api.post("/approval-rules")
async def create_approval_rule(inp: ApprovalRuleIn, user=Depends(require_role("org_admin"))):
    r = {"id": new_id(), "org_id": user["org_id"], **inp.model_dump(), "created_at": now_iso()}
    await db.approval_rules.insert_one(r)
    await audit(user, "create", "approval_rule", r["id"], after=inp.model_dump())
    return {k: v for k, v in r.items() if k != "_id"}

@api.delete("/approval-rules/{rid}")
async def delete_approval_rule(rid: str, user=Depends(require_role("org_admin"))):
    await db.approval_rules.delete_one({"id": rid, "org_id": user["org_id"]})
    await audit(user, "delete", "approval_rule", rid)
    return {"ok": True}

@api.put("/org-settings")
async def put_org_settings(inp: OrgSettingsIn, user=Depends(require_role("org_admin"))):
    await db.organizations.update_one({"id": user["org_id"]}, {"$set": {"default_threshold": inp.default_threshold}})
    await audit(user, "update", "org_settings", user["org_id"], after=inp.model_dump())
    return {"ok": True}

# ---------- Seed admin ----------
async def seed_admin():
    existing = await db.users.find_one({"email": ADMIN_EMAIL.lower()})
    if existing:
        # ensure active
        await db.users.update_one({"id": existing["id"]}, {"$set": {"active": True, "role": "org_admin"}})
        log.info(f"Admin exists: {ADMIN_EMAIL}")
        return
    org_id = new_id()
    user_id = new_id()
    await db.organizations.insert_one({"id": org_id, "name": "Acme Warehouse Co.", "owner_id": user_id, "created_at": now_iso()})
    await db.users.insert_one({"id": user_id, "org_id": org_id, "email": ADMIN_EMAIL.lower(), "name": ADMIN_NAME, "role": "org_admin", "password_hash": hash_pw(ADMIN_PASSWORD), "created_at": now_iso(), "active": True})
    # Seed sample data
    wh1_id = new_id(); wh2_id = new_id()
    await db.warehouses.insert_many([
        {"id": wh1_id, "org_id": org_id, "name": "Pune Warehouse", "code": "PUN", "address": "Pune, MH", "created_at": now_iso()},
        {"id": wh2_id, "org_id": org_id, "name": "Mumbai Warehouse", "code": "MUM", "address": "Mumbai, MH", "created_at": now_iso()},
    ])
    # Locations for Pune
    zone_id = new_id(); aisle_id = new_id(); rack_id = new_id(); shelf_id = new_id()
    await db.locations.insert_many([
        {"id": zone_id, "org_id": org_id, "warehouse_id": wh1_id, "parent_id": None, "type": "zone", "name": "Zone B", "code": "B", "created_at": now_iso()},
        {"id": aisle_id, "org_id": org_id, "warehouse_id": wh1_id, "parent_id": zone_id, "type": "aisle", "name": "Aisle 4", "code": "4", "created_at": now_iso()},
        {"id": rack_id, "org_id": org_id, "warehouse_id": wh1_id, "parent_id": aisle_id, "type": "rack", "name": "Rack 12", "code": "12", "created_at": now_iso()},
        {"id": shelf_id, "org_id": org_id, "warehouse_id": wh1_id, "parent_id": rack_id, "type": "shelf", "name": "Shelf 3", "code": "3", "created_at": now_iso()},
    ])
    sample_products = [
        {"sku": "SM-XYZ-2026", "barcode": "8901234567890", "name": "Samsung Monitor 24M XYZ", "brand": "Samsung", "category": "Electronics", "model_number": "24M-XYZ"},
        {"sku": "DL-LT-14", "barcode": "8901234567891", "name": "Dell Latitude 14 Laptop", "brand": "Dell", "category": "Electronics", "model_number": "LAT-14"},
        {"sku": "HELM-BLU-M", "barcode": "8901234567892", "name": "Blue Safety Helmet Medium", "brand": "SafeGuard", "category": "Safety Gear", "model_number": "SG-BLU-M"},
        {"sku": "GLOV-NIT-L", "barcode": "8901234567893", "name": "Nitrile Gloves Large Box-100", "brand": "MedPro", "category": "Safety Gear", "model_number": "MP-NIT-L"},
        {"sku": "KBD-MECH-01", "barcode": "8901234567894", "name": "Mechanical Keyboard RGB", "brand": "Logitech", "category": "Electronics", "model_number": "LG-MK-01"},
        {"sku": "CRT-BOX-M", "barcode": "8901234567895", "name": "Cardboard Storage Box Medium", "brand": "PackWell", "category": "Packaging", "model_number": "PW-CB-M"},
        {"sku": "MSK-N95-B50", "barcode": "8901234567896", "name": "N95 Respirator Mask Box 50", "brand": "3M", "category": "Safety Gear", "model_number": "3M-N95-50"},
        {"sku": "TRO-HDT-01", "barcode": "8901234567897", "name": "Heavy Duty Trolley 200kg", "brand": "IronCart", "category": "Equipment", "model_number": "IC-HDT-200"},
    ]
    for sp in sample_products:
        pid = new_id()
        await db.products.insert_one({"id": pid, "org_id": org_id, **sp, "description": f"{sp['name']} — high quality {sp['category'].lower()}", "image_url": "", "attributes": {}, "created_at": now_iso()})
        # Add inventory
        qty1 = 24 if sp["sku"] == "SM-XYZ-2026" else (5 + (hash(sp["sku"]) % 60))
        await db.inventory.insert_one({"id": new_id(), "org_id": org_id, "product_id": pid, "warehouse_id": wh1_id, "location_id": shelf_id if sp["sku"] == "SM-XYZ-2026" else None, "quantity": qty1, "reserved_quantity": 0, "reorder_level": 10, "updated_at": now_iso()})
        await db.inventory.insert_one({"id": new_id(), "org_id": org_id, "product_id": pid, "warehouse_id": wh2_id, "location_id": None, "quantity": (hash(sp["sku"] + "b") % 40), "reserved_quantity": 0, "reorder_level": 10, "updated_at": now_iso()})
    log.info(f"Seeded admin: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")

@app.on_event("startup")
async def startup():
    await seed_admin()

@api.get("/")
async def root():
    return {"service": "AI Inventory Worker", "status": "ok"}

app.include_router(api)
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','), allow_methods=["*"], allow_headers=["*"])

@app.on_event("shutdown")
async def shutdown():
    client.close()
