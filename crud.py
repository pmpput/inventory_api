from sqlalchemy.orm import Session
from sqlalchemy import select, and_
from typing import List, Optional
import models, schemas

# ---------- Branch ----------
def get_branches(db: Session) -> List[models.Branch]:
    return db.execute(select(models.Branch).order_by(models.Branch.name.asc())).scalars().all()

def create_branch(db: Session, data: schemas.BranchCreate) -> models.Branch:
    obj = models.Branch(id=data.id, name=data.name, location=data.location)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

def update_branch(db: Session, branch_id: int, data: schemas.BranchUpdate) -> Optional[models.Branch]:
    obj = db.get(models.Branch, branch_id)
    if not obj:
        return None
    if data.name is not None:
        obj.name = data.name
    if data.location is not None:
        obj.location = data.location
    db.commit()
    db.refresh(obj)
    return obj

def delete_branch(db: Session, branch_id: int) -> bool:
    obj = db.get(models.Branch, branch_id)
    if not obj:
        return False
    db.delete(obj)
    db.commit()
    return True

# ------- Product ---------
def get_products(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Product).offset(skip).limit(limit).all()

def create_product(db: Session, product: schemas.ProductCreate):
    db_product = models.Product(**product.dict(exclude_unset=True))
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product

# ---------- Read (list + filters) ----------
def get_products(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    name: str | None = None,
    category: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    branch_id: int | None = None,   # ✅ รับเข้ามา
):
    q = db.query(models.Product)

    if name:
        q = q.filter(models.Product.name.ilike(f"%{name}%"))
    if category:
        q = q.filter(models.Product.category == category)
    if min_price is not None:
        q = q.filter(models.Product.price >= min_price)
    if max_price is not None:
        q = q.filter(models.Product.price <= max_price)
    if branch_id is not None:       # ✅ ฟิลเตอร์ตามสาขา
        q = q.filter(models.Product.branch_id == branch_id)

    return q.offset(skip).limit(limit).all()

# ---------- Read one ----------
def get_product(db: Session, product_id: int) -> models.Product | None:
    return db.get(models.Product, product_id)

# ---------- Update ----------
def update_product(db: Session, product_id: int, patch: schemas.ProductUpdate):
    db_obj = db.get(models.Product, product_id)
    if not db_obj:
        return None

    data = patch.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(db_obj, k, v)

    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

# ---------- Delete ----------
def delete_product(db: Session, product_id: int) -> bool:
    db_obj = db.get(models.Product, product_id)
    if not db_obj:
        return False
    db.delete(db_obj)
    db.commit()
