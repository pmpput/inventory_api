from fastapi import APIRouter,FastAPI, Depends, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from typing import List
import os, shutil
import json
import cloudinary
import cloudinary.uploader

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

# ----- สร้างตารางเมื่อรันครั้งแรก (ถ้ายังไม่มี) -----
# Base.metadata.create_all(bind=engine)

app = FastAPI(title="Inventory API")

cloudinary.config(
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME")
)
router = APIRouter(prefix="/branches", tags=["Branches"])
app.include_router(auth_router)  # << เพิ่มบรรทัดนี้
app.include_router(router)

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
