"""AI INVENTORY WORKER - Backend API"""
from fastapi import FastAPI, APIRouter, HTTPException, Depends, status, UploadFile, File, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime, timezone, timedelta
from pathlib import Path
import os, uuid, logging, json, bcrypt, jwt, io, base64, asyncio
import pandas as pd

from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent, TextDelta, ToolCallStart, ToolCallReady, StreamDone

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
    return {k: v for k, v in u.items() if k != "password_hash"}

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

@api.post("/inventory/adjust")
async def adjust_inventory(inp: InventoryAdjust, user=Depends(require_role("org_admin", "manager", "worker"))):
    inv = await db.inventory.find_one({"id": inp.inventory_id, "org_id": user["org_id"]}, {"_id": 0})
    if not inv: raise HTTPException(404, "Inventory not found")
    before = inv["quantity"]
    await db.inventory.update_one({"id": inp.inventory_id}, {"$set": {"quantity": inp.new_quantity, "updated_at": now_iso()}})
    await db.inventory_transactions.insert_one({
        "id": new_id(), "org_id": user["org_id"], "inventory_id": inp.inventory_id,
        "product_id": inv["product_id"], "type": "adjustment",
        "before_qty": before, "after_qty": inp.new_quantity, "reason": inp.reason,
        "user_id": user["id"], "timestamp": now_iso()
    })
    await audit(user, "adjust", "inventory", inp.inventory_id, before={"qty": before}, after={"qty": inp.new_quantity}, reason=inp.reason)
    return {"ok": True, "before": before, "after": inp.new_quantity}

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
