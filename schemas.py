from pydantic import BaseModel , Field, EmailStr, field_validator
from typing import Optional , Literal , List
# schemas.py
from models import UserGlobalRole as GlobalRole, BranchRoleEnum as BranchRole


class BranchBase(BaseModel):
    id: Optional[int] = None
    name: str
    location: Optional[str] = None

class BranchCreate(BranchBase): pass
class BranchUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None

class Branch(BranchBase):
    id: int
    model_config = {"from_attributes": True}

class ProductBase(BaseModel):
    id: Optional[int] = None
    name: str
    price: float        # ถ้าเปลี่ยนเป็น int ให้ตรงกับ models
    quantity: int
    category: Optional[str] = None
    image_url: Optional[str] = None
    branch_id: int      # ต้องส่งมาเสมอ
    unit: Optional[str] = None 

class ProductCreate(ProductBase): pass

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = None
    quantity: Optional[int] = None
    category: Optional[str] = None
    image_url: Optional[str] = None
    branch_id: Optional[int] = None
    unit: Optional[str] = None 

class Product(ProductBase):
    id: int
    model_config = {"from_attributes": True}


 # เพิ่ม roles 

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class LoginRequest(BaseModel):
    username: str
    password: str

class UserOut(BaseModel):
    id: int
    username: str
    global_role: GlobalRole
    class Config:
        from_attributes = True

class UserCreate(BaseModel):
    username: str
    password: str
    global_role: Optional[GlobalRole] = GlobalRole.EMPLOYEE

class UserBranchRoleOut(BaseModel):
    branch_id: int
    role: BranchRole

class RegisterRequest(BaseModel):
    username: str
    password: str
    global_role: str
    default_branch_id: Optional[int] = None 
    branch_id: Optional[int] = None  # 👈 เพิ่มบรรทัดนี้

    @field_validator("global_role")
    @classmethod
    def normalize_role(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in {"owner", "manager", "employee"}:
            raise ValueError("global_role must be one of: owner, manager, employee")
        return v


class UserOut(BaseModel):
    id: int
    username: str
    email: Optional[str]
    role: str
    branch_id: Optional[int]
    class Config:
        from_attributes = True    
   
