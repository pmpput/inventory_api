from fastapi import APIRouter,FastAPI, Depends, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from typing import List, Dict
import os, shutil
import json
import cloudinary
import cloudinary.uploader
from models import Product 
import pandas as pd
import nest_asyncio
import sys
import asyncio
from pydantic import BaseModel
import re

import firebase_admin
from firebase_admin import credentials, messaging
import models, schemas, crud
from database import engine, get_db, Base

# import roles
from auth import get_current_user, require_owner
from permissions import require_branch_member
from models import BranchRoleEnum as BranchRole, UserGlobalRole as GlobalRole, User, UserBranchRole
from auth import create_access_token, verify_password
from schemas import LoginRequest, Token, UserCreate
from auth import router as auth_router  # << นำ router เข้ามา
from firebase_utils import send_inventory_notification 
from models import Branch
from line_webhook import router as line_router

# 1. Allow nested event loops
nest_asyncio.apply()

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# IMPORT YOUR SCRAPERS
from retailer_scraper import scrape_search, find_best_deals
from ai_matcher import SmartMatcher

# ==========================================
# 🔧 CONFIG
# ==========================================
# REPLACE WITH YOUR KEYS
# LINE_CHANNEL_ACCESS_TOKEN = "YOUR_ACCESS_TOKEN_HERE" 
# LINE_CHANNEL_SECRET = "YOUR_CHANNEL_SECRET_HERE"

# line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
# handler = WebhookHandler(LINE_CHANNEL_SECRET)

CACHE = {"engine": None}

TARGETS = [
    {
        "name": "BigC",
        "search_url": "https://www.bigc.co.th/en/search?q={q}",
        "selectors": {"product_card": 'div.productItem, div[data-testid="product-card"]', "name": ".product-name", "price": ".product-price"},
    },
    {
        "name": "Tops",
        "search_url": "https://www.tops.co.th/en/search/{q}",
        "selectors": {"product_card": ".product-item-info", "name": ".product-item-link", "price": ".price"},
    },
    {
        "name": "Makro",
        "search_url": "https://www.makro.pro/en/c/search?q={q}",
        "selectors": {"product_card": 'div[class*="product-card"]', "name": 'span[class*="name"]', "price": 'span[class*="price"]'},
    },
]
# ----- สร้างตารางเมื่อรันครั้งแรก (ถ้ายังไม่มี) -----
# Base.metadata.create_all(bind=engine)

app = FastAPI(title="Inventory API")

cloudinary.config(
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME")
)
router = APIRouter(prefix="/branches", tags=["Branches"])
app.include_router(auth_router)  # << เพิ่มบรรทัดนี้
app.include_router(router)
app.include_router(line_router)

class CompareRequest(BaseModel):
    items: List[str]

# ==========================================
# 🧠 CORE LOGIC
# ==========================================
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())

def clean_search_results(query: str, results: List[dict]) -> List[dict]:
    q = _norm(query)

    PET_WORDS = ["nekko", "me-o", "meo", "whiskas", "friskies", "purina", "kaniva", "cat", "kitten", "dog", "puppy", "pet", "cesar", "pedigree", "smartheart", "royal canin", "jerhigh", "tito", "bok dok", "monchou", "อาหารแมว", "อาหารสุนัข", "แมว", "สุนัข", "pouch", "jelly", "gravy", "topping", "litter", "sand"]
    
    NON_FOOD_WORDS = ["ตุ๊กตา", "ของเล่น", "พวงกุญแจ", "หมอน", "เสื้อ", "กระเป๋า", "ผ้า", "รองเท้า", "ของใช้", "ของตกแต่ง", "toy", "doll", "plush", "stuffed", "keychain", "shirt", "bag", "decor", "mouthwash", "toothpaste", "dental", "น้ำยาบ้วนปาก", "ยาสีฟัน", "แปรงสีฟัน", "shampoo", "soap", "แชมพู", "สบู่", "listerine", "colgate"]
    
    COOKED_WORDS = ["ทอด", "ย่าง", "อบ", "ต้ม", "นึ่ง", "ปรุงสุก", "พร้อมทาน", "สำเร็จรูป", "ready", "cooked", "fried", "roasted", "bbq", "grilled", "meal", "set", "box", "retort"]
    
    # ✅ Baby Food Block List
    BABY_FOOD_WORDS = ["baby", "puree", "peachy", "cerelac", "hooray", "picnic", "kiddy", "kid", "toddler", "infant", "อาหารเด็ก", "อาหารทารก", "บดละเอียด", "pouch"]

    # ✅ Added Porridge/Soup/Broth
    PROCESSED_WORDS = [
        "สูตร", "ผสม", "แปรรูป", "เส้น", "แป้ง", "ขนม", "ขนมจีน", "บะหมี่", "พาสต้า", 
        "น้ำ", "ซอส", "ผง", "แหนม", "ไส้กรอก", "กุนเชียง", "ลูกชิ้น", "ข้าว", "ข้าวหอม", 
        "โจ๊ก", "ข้าวต้ม", "ซุป", "porridge", "soup", "broth", "chowder",
        "mix", "mixed", "powder", "sauce", "noodle", "pasta", "snack", "processed",
        "sausage", "bites", "rice", "jasmine", "stick", "chip", "roll", "cracker",
        "nugget", "burger", "marinated", "pickled", "dry", "dried", "อบแห้ง"
    ]

    # 🎯 SPECIFICITY RULES
    SPEC_RULES = [
        # ✅ EGGS: Strict Block Quail
        {"triggers": ["ไข่ไก่", "chicken egg", "egg", "ไข่"], 
         "must": ["ไข่", "egg"], 
         "block": ["quail", "กระทา", "เยี่ยวม้า", "century", "เค็ม", "salted", "liquid", "white", "yolk"]},

        # ✅ COKE: Strict Block Sprite
        {"triggers": ["coke zero", "โค้กซีโร่", "โค้ก zero"], 
         "must": ["coke", "zero", "โค้ก", "ซีโร่", "cola", "ไม่มีน้ำตาล"], 
         "block": ["sprite", "สไปรท์", "fanta", "แฟนก้า", "pepsi", "เป๊ปซี่", "schweppes", "est", "เอส"]},

        # Meat/Fish
        {"triggers": ["สามชั้น", "belly"], "must": ["สามชั้น", "belly"], "block": []},
        {"triggers": ["สันคอ", "collar"], "must": ["สันคอ", "collar"], "block": []},
        {"triggers": ["สันนอก", "loin"], "must": ["สันนอก", "loin"], "block": ["ใน", "tender"]},
        {"triggers": ["สันใน", "tenderloin"], "must": ["สันใน", "tenderloin"], "block": ["นอก", "sirloin"]},
        {"triggers": ["หมูบด", "minced", "ground"], "must": ["บด", "minced", "ground"], "block": ["slice", "ชิ้น"]},
        {"triggers": ["ซี่โครง", "rib"], "must": ["ซี่โครง", "rib"], "block": ["แหนม"]},
        {"triggers": ["อกไก่", "breast"], "must": ["อก", "breast"], "block": ["น่อง", "drumstick"]},
        {"triggers": ["น่อง", "drumstick"], "must": ["น่อง", "drumstick"], "block": ["ปีก", "wing", "อก", "breast"]},
        {"triggers": ["ปีก", "wing"], "must": ["ปีก", "wing", "กลาง", "บน"], "block": []},
        {"triggers": ["สะโพก", "thigh"], "must": ["สะโพก", "thigh"], "block": []},
        {"triggers": ["ทับทิม", "tabtim", "red tilapia"], "must": ["ทับทิม", "red tilapia", "ruby"], "block": ["นิล", "black"]},
        {"triggers": ["นิล", "tilapia"], "must": ["นิล", "tilapia"], "block": ["ทับทิม", "red"]},
        {"triggers": ["salmon", "แซลมอน"], "must": ["salmon", "แซลมอน"], "block": ["head", "bone", "scrap", "หัว", "กาง"]},
        {"triggers": ["dory", "ดอรี่"], "must": ["dory", "ดอรี่", "pangasius"], "block": []},
        {"triggers": ["saba", "ซาบะ"], "must": ["saba", "ซาบะ"], "block": ["noodle", "bento"]},
        {"triggers": ["apple", "แอปเปิ้ล"], "must": ["apple", "แอปเปิ้ล"], "block": ["juice", "cider", "pie", "น้ำ"]},
        {"triggers": ["orange", "ส้ม"], "must": ["orange", "ส้ม"], "block": ["juice", "น้ำ"]},
    ]

    active_musts = []
    active_blocks = []
    
    for rule in SPEC_RULES:
        if any(t in q for t in rule["triggers"]):
            active_musts.extend(rule["must"])
            active_blocks.extend(rule["block"])

    is_fresh_query = any(w in q for w in ["หมู", "ไก่", "เนื้อ", "ปลา", "ผัก", "ผลไม้", "pork", "chicken", "beef", "fish", "veg", "fruit", "salmon", "แซลมอน"])

    egg_grade = None
    m = re.search(r"(?:เบอร์|no[\.\s]|number|size)\s*(\d)", q)
    if m: egg_grade = m.group(1)

    cleaned = []

    for r in results:
        raw_name = str(r.get("Product Name", ""))
        name = _norm(raw_name)
        if not name: continue
        
        if len(re.sub(r"[^\d]", "", name)) > 4 and len(name) < 15: continue

        if any(w in name for w in PET_WORDS): continue
        if any(w in name for w in NON_FOOD_WORDS): continue
        if any(w in name for w in COOKED_WORDS): continue
        
        if is_fresh_query:
            if any(w in name for w in PROCESSED_WORDS): continue
            if any(w in name for w in BABY_FOOD_WORDS): continue

        # ✅ TYPO FIXED HERE: 'n' -> 'name'
        if "coke" in q or "โค้ก" in q:
            if any(w in name for w in NON_FOOD_WORDS): continue

        if active_musts:
            if not any(w in name for w in active_musts): continue
        if active_blocks:
            if any(w in name for w in active_blocks): continue

        if egg_grade:
            found_grades = re.findall(r"(?:เบอร์|no[\.\s]|number|size)\s*(\d)", name)
            if found_grades and egg_grade not in found_grades: continue

        cleaned.append(r)

    return cleaned

def best_per_retailer(item: str, deals: List[dict]) -> List[dict]:
    best: Dict[str, dict] = {}
    for d in deals:
        retailer = d.get("WINNER", "Unknown")
        try: unit_price = float(d.get("Unit Price", 999999))
        except: unit_price = 999999.0

        if retailer not in best or unit_price < float(best[retailer].get("Unit Price", 999999)):
            best[retailer] = d

    out = []
    for retailer, d in best.items():
        unit = d.get("BaseUnit", "unit")
        try: raw_price = float(d.get("Price", 0))
        except: raw_price = 0.0
        try: raw_unit_price = float(d.get("Unit Price", 0))
        except: raw_unit_price = 0.0
        try: original_price = float(d.get("Original Price", raw_price))
        except: original_price = raw_price
        
        is_promo = original_price > raw_price

        out.append({
            "WINNER": retailer,
            "Product Name": d.get("Product Name", ""),
            "Product Type": "",
            "Best Price": f"฿{raw_price:.2f}",
            "Unit Price": f"฿{raw_unit_price:.2f}/{unit}",
            "_raw_price": raw_price,
            "_raw_unit_price": raw_unit_price,
            "is_promo": is_promo,
            "original_price": original_price if is_promo else None,
            "query_item": item,
        })
    out.sort(key=lambda x: float(x.get("_raw_unit_price", 999999)))
    return out

def expand_query_for_bigc(query: str) -> List[str]:
    q = query.lower().strip()
    expanded = [query]

    if q in ["coke zero", "coca cola zero", "โค้ก zero", "โค้กซีโร่"]:
        expanded += ["โค้ก สูตรไม่มีน้ำตาล", "โค้ก ไม่มีน้ำตาล", "coke no sugar"]

    if "สันคอ" in q or "collar" in q: 
        expanded += ["หมูสันคอ", "เนื้อหมูสันคอ", "s-pure สันคอ", "betagro สันคอ"]
    if "สามชั้น" in q or "belly" in q: 
        expanded += ["หมูสามชั้น", "เนื้อหมูสามชั้น", "s-pure สามชั้น", "betagro สามชั้น"]
    if "สันนอก" in q or "loin" in q: 
        expanded += ["หมูสันนอก", "เนื้อหมูสันนอก"]
    if "บด" in q or "minced" in q: 
        expanded += ["หมูบด", "เนื้อหมูบด"]

    if "อกไก่" in q or "breast" in q: 
        expanded += ["เนื้ออกไก่", "อกไก่ลอกหนัง", "s-pure อกไก่"]
    if "น่อง" in q or "drumstick" in q: 
        expanded += ["น่องไก่", "ปีกบน"]

    if "ไข่" in q and "เบอร์" in q:
        expanded.append(q.replace("เบอร์", "เบอร์ที่"))

    return list(dict.fromkeys(expanded))

async def process_single_item(item: str) -> List[dict]:
    print(f"🔎 Processing: {item}")
    scrape_tasks = []
    
    for t in TARGETS:
        queries = [item]
        if t["name"] == "BigC":
            queries = expand_query_for_bigc(item)
            
        for q in queries:
            scrape_tasks.append(scrape_search(t["name"], t["search_url"], q, t["selectors"]))

    results_lists = await asyncio.gather(*scrape_tasks, return_exceptions=True)
    raw_data = []
    for res in results_lists:
        if isinstance(res, list): raw_data.extend(res)

    cleaned_data = clean_search_results(item, raw_data)
    if not cleaned_data: return []

    try:
        df = pd.DataFrame(cleaned_data)
        processed = find_best_deals(df)
        candidates = json.loads(processed.to_json(orient="records"))
        
        engine = SmartMatcher(candidates)
        matches = engine.find_matches(item, threshold=0.25)
        matches = clean_search_results(item, matches) 
        if not matches: matches = candidates

        return best_per_retailer(item, matches[:60])
    
    except Exception as e:
        print(f"❌ Core Logic Error: {e}")
        return []

@app.get("/ping")
def ping():
    return {"status": "ok"}
# ----- เปิด CORS (ช่วงพัฒนาให้ * ไปก่อน ถ้าโปรดักชันควรระบุโดเมน) -----

origins = [
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "*"  # ช่วง dev ใส่ * ง่ายสุด (โปรดล็อกให้แคบลงตอนโปรดักชัน)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----- Static files สำหรับเสิร์ฟรูป -----
app.mount("/static", StaticFiles(directory="static"), name="static")
UPLOAD_DIR = "static/images"


# --------------- Upload image ---------------
@app.post("/upload/")
async def upload_image(file: UploadFile = File(...)):
    # ตรวจว่าเป็นรูปคร่าว ๆ
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    try:
        # อัปโหลดขึ้น Cloudinary (ไปอยู่ในโฟลเดอร์ inventory)
        result = cloudinary.uploader.upload(
            file.file,          # ใช้ stream จาก UploadFile
            folder="inventory", # ชื่อโฟลเดอร์ใน Cloudinary จะรวมรูปไว้ด้วยกัน
            resource_type="image",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")

    image_url = result.get("secure_url")
    if not image_url:
        raise HTTPException(status_code=500, detail="No image url returned from Cloudinary")

    # ส่ง URL ถาวรกลับไปให้ Flutter
    return {"image_url": image_url}

# ---------- Branches ----------
@app.get("/branches/", response_model=List[schemas.Branch])
def read_branches(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),       # ต้องล็อกอิน
):
    # Owner เห็นทุกสาขา / คนอื่นอาจอยากเห็นเฉพาะสาขาที่ตัวเองสังกัดก็ได้
    # เบื้องต้นอนุญาตให้เห็นทั้งหมด (ถ้าต้องการจำกัด ให้ query ตาม membership)
    return crud.get_branches(db)

@app.post("/branches/", response_model=schemas.Branch, status_code=201)
def create_branch(
    branch: schemas.BranchCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),          # Owner เท่านั้น
):
    return crud.create_branch(db, branch)

@app.patch("/branches/{branch_id}/set_location")
def set_branch_location(
    branch_id: int,
    lat: float,
    lng: float,
    address: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),
):
    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")

    branch.latitude = lat
    branch.longitude = lng
    branch.address = address
    db.commit()
    db.refresh(branch)

    return {
        "id": branch.id,
        "name": branch.name,
        "latitude": branch.latitude,
        "longitude": branch.longitude,
        "address": branch.address,
    }


@app.get("/branches/{branch_id}/location")
def get_branch_location(branch_id: int, db: Session = Depends(get_db)):
    branch = db.query(Branch).filter(Branch.id == branch_id).first()

    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")

    return {
        "id": branch.id,
        "name": branch.name,
        "latitude": branch.latitude,
        "longitude": branch.longitude,
        "address": branch.address
    }


@app.put("/branches/{branch_id}", response_model=schemas.Branch)
def update_branch(
    branch_id: int,
    data: schemas.BranchUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),          # Owner เท่านั้น
):
    obj = crud.update_branch(db, branch_id, data)
    if not obj:
        raise HTTPException(status_code=404, detail="Branch not found")
    return obj


@app.delete("/branches/{branch_id}", status_code=204)
def delete_branch(
    branch_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_owner),          # Owner เท่านั้น
):
    ok = crud.delete_branch(db, branch_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Branch not found")
    return

# --------------- Create ---------------
@app.post("/products/", response_model=schemas.Product)
def create_product(
    product: schemas.ProductCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.global_role == GlobalRole.OWNER:
        return crud.create_product(db=db, product=product)
    # อนุญาตเฉพาะ Manager ในสาขา
    require_branch_member(product.branch_id, min_role=BranchRole.MANAGER)(db=db, user=user)
    return crud.create_product(db=db, product=product)



# --------------- List + Search/Filter + Pagination ---------------
@app.get("/products/")
def read_products(
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, gt=0, le=1000),
    name: str | None = None,
    category: str | None = None,
    min_price: float | None = Query(None, ge=0),
    max_price: float | None = Query(None, ge=0),
    branch_id: int | None = Query(None),
    user: User = Depends(get_current_user),       # ต้องล็อกอิน
):
    # Owner: ผ่าน
    if user.global_role != GlobalRole.OWNER:
        # Non-owner: ต้องมี branch_id และเป็นสมาชิกสาขานี้
        if branch_id is None:
            raise HTTPException(400, "branch_id is required for non-owner")
        require_branch_member(branch_id)(db=db, user=user)

    return crud.get_products(
        db=db,
        skip=skip,
        limit=limit,
        name=name,
        category=category,
        min_price=min_price,
        max_price=max_price,
        branch_id=branch_id,
    )

# --------------- Read one ---------------
@app.get("/products/{product_id}", response_model=schemas.Product)
def read_product(
    product_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    obj = crud.get_product(db, product_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Product not found")
    if user.global_role != GlobalRole.OWNER:
        require_branch_member(obj.branch_id)(db=db, user=user)
    return obj



# --------------- Update ---------------
@app.put("/products/{product_id}", response_model=schemas.Product)
def update_product(
    product_id: int,
    patch: schemas.ProductUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    current = crud.get_product(db, product_id)
    if not current:
        raise HTTPException(status_code=404, detail="Product not found")

    # Owner: แก้ได้ทุก field
    if user.global_role == GlobalRole.OWNER:
        updated = crud.update_product(db, product_id, patch)
    else:
        # ต้องเป็นสมาชิกสาขานี้
        require_branch_member(current.branch_id)(db=db, user=user)

        ur = db.query(UserBranchRole).filter_by(
            user_id=user.id,
            branch_id=current.branch_id,
        ).first()
        if not ur:
            raise HTTPException(403, "Not a member of this branch")

        if ur.role == BranchRole.MANAGER:
            updated = crud.update_product(db, product_id, patch)
        else:
            # STAFF: อัปเดตได้เฉพาะ quantity
            if patch.quantity is None or any([
                patch.name is not None,
                patch.price is not None,
                patch.category is not None,
                patch.image_url is not None,
                patch.branch_id is not None,
            ]):
                raise HTTPException(403, "Staff can only update quantity")

            updated = crud.update_product(
                db, product_id, schemas.ProductUpdate(quantity=patch.quantity)
            )

    # ==== แจ้งเตือน FCM แบบใช้ helper ====
    if patch.quantity is not None:
        title = None
        body = None

        if patch.quantity == 0:
            title = "สินค้าหมดสต็อก"
            body = f"{updated.name} หมดแล้วในสาขา ID {updated.branch_id}"
        elif patch.quantity <= 5:
            title = "สินค้าใกล้หมด"
            body = f"{updated.name} เหลือเพียง {patch.quantity} ชิ้น"

        if title:
            send_inventory_notification(title, body)

    return updated


# --------------- Delete ---------------
@app.delete("/products/{product_id}")
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    obj = crud.get_product(db, product_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Product not found")

    if user.global_role == GlobalRole.OWNER:
        ok = crud.delete_product(db, product_id)
        return {"deleted": ok, "id": product_id}

    # Manager เท่านั้นในสาขาตน
    require_branch_member(obj.branch_id, min_role=BranchRole.MANAGER)(db=db, user=user)
    ok = crud.delete_product(db, product_id)
    return {"deleted": ok, "id": product_id}

# === LINE PUBLIC API ===
@app.get("/line/products")
def line_products(
    branch_id: int,
    db: Session = Depends(get_db),
):
    try:
        products = (
            db.query(Product)
            .filter(Product.branch_id == branch_id)
            .all()
        )

        return [
            {
                "id": p.id,
                "name": p.name,
                "price": p.price,
                "quantity": p.quantity,
                "unit": p.unit,
                "category": p.category,
            }
            for p in products
        ]

    except Exception as e:
        print("🔥 LINE PRODUCTS ERROR:", str(e))
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/line/add-product")
def line_add_product(data: schemas.ProductCreate, db: Session = Depends(get_db)):
    product = models.Product(**data.dict())
    db.add(product)
    db.commit()
    db.refresh(product)
    return {"id": product.id, "name": product.name}    

@app.post("/api/compare")
async def compare_prices(req: CompareRequest):
    final_results = []
    for item in req.items:
        item = (item or "").strip()
        if not item: continue
        results = await process_single_item(item)
        final_results.extend(results)
    return {"status": "success", "message": "", "data": final_results}

