# models.py
import enum as pyenum
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Index, UniqueConstraint, func
)
from sqlalchemy.types import Enum as SAEnum   # <<< ใช้ SAEnum เป็นของ SQLAlchemy เท่านั้น
from sqlalchemy.orm import relationship
from database import Base

# ===== Global role (ทั้งระบบ) =====
class UserGlobalRole(pyenum.Enum):           # <<< ใช้ Python enum
    OWNER = "owner"
    MANAGER = "manager"
    EMPLOYEE = "employee"

# ===== Branch role (บทบาทภายในสาขา) =====
class BranchRoleEnum(pyenum.Enum):           # <<< ใช้ Python enum เช่นกัน
    MANAGER = "MANAGER"
    STAFF   = "STAFF"

class Branch(Base):
    __tablename__ = "branches"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True, index=True)
    location = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    address = Column(String(500), nullable=True)

    products = relationship("Product", back_populates="branch", cascade="all, delete-orphan")

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False, default=0)
    category = Column(String(100), nullable=True, index=True)
    image_url = Column(String(512), nullable=True)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True)
    branch = relationship("Branch", back_populates="products")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    unit = Column(String(50), nullable=True)

Index("ix_products_name_category_branch", Product.name, Product.category, Product.branch_id)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(150), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)

    # <<< ย้าย global_role มาไว้ "ในคลาส" และบังคับใช้ค่า .value (ตัวเล็ก) กับ PG enum 'globalrole'
    global_role = Column(
        SAEnum(
            UserGlobalRole,
            name="globalrole",             # ชื่อ type ใน Postgres ต้องตรงกับที่สร้างไว้
            native_enum=True,
            create_type=False,             # ไม่สร้าง type ใหม่ ทับของเดิม
            values_callable=lambda e: [m.value for m in e],  # <<< สำคัญ!
        ),
        nullable=False,
        server_default="employee",
    )

    # default branch (optional)
    default_branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)

    branch_roles = relationship("UserBranchRole", back_populates="user", cascade="all, delete-orphan")

class UserBranchRole(Base):
    __tablename__ = "user_branch_roles"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)

    role = Column(
        SAEnum(
            BranchRoleEnum,
            name="branchrole",              # ตั้งชื่อ type ใน PG ให้คงที่
            native_enum=True,
            create_type=True,               # จะให้ SA สร้างครั้งแรกก็ได้ (ถ้ามีอยู่แล้วจะข้าม)
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )

    user = relationship("User", back_populates="branch_roles")
    __table_args__ = (UniqueConstraint("user_id", "branch_id", name="uq_user_branch"),)
