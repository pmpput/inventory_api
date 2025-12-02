# auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from database import get_db
from models import User, UserBranchRole, Branch, BranchRoleEnum, UserGlobalRole
from passlib.hash import pbkdf2_sha256
from pydantic import BaseModel
import jwt, os
from datetime import datetime, timedelta, timezone
from schemas import RegisterRequest, LoginRequest
from typing import Optional

router = APIRouter(prefix="/auth", tags=["Auth"])

# ===== JWT config =====
# บน Cloud ให้ตั้ง ENV: JWT_SECRET_KEY
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    # เวลา dev บนเครื่องจะใช้ค่า default ได้
    # แต่บน Cloud แนะนำให้ตั้ง JWT_SECRET_KEY เสมอ
    SECRET_KEY = "dev-secret-key"
    print("⚠️ WARNING: using default dev SECRET_KEY. Set JWT_SECRET_KEY in environment for production.")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# -------- helpers --------
def hash_password(raw: str) -> str:
    return pbkdf2_sha256.hash(raw))

def verify_password(raw: str, hashed: str) -> bool:
    return pbkdf2_sha256.verify(raw, hashed)

def create_access_token(data: dict, expires_minutes: int = ACCESS_TOKEN_EXPIRE_MINUTES) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# -------- Schemas --------
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# -------- current user --------
def get_current_user(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)) -> User:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        return user

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def require_owner(user: User = Depends(get_current_user)) -> User:
    if user.global_role != UserGlobalRole.OWNER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner only access")
    return user


# -------- REGISTER --------
@router.post("/register")
def register_user(data: RegisterRequest, db: Session = Depends(get_db)):
    # ป้องกันซ้ำ
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")

    # ✅ แปลง role เป็นตัวเล็ก แล้ว map เป็น enum
    normalized_role = (data.global_role or "").strip().lower()

    try:
        role_enum = UserGlobalRole(normalized_role)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid role")

    new_user = User(
        username=data.username,
        password_hash=hash_password(data.password),
        global_role=role_enum,
        default_branch_id=data.default_branch_id,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # ถ้าเป็น manager/employee → map เข้า user_branch_roles
    if role_enum in (UserGlobalRole.MANAGER, UserGlobalRole.EMPLOYEE):
        if not data.branch_id:
            raise HTTPException(status_code=400, detail="Branch ID required for manager/employee")

        branch = db.query(Branch).filter(Branch.id == data.branch_id).first()
        if not branch:
            raise HTTPException(status_code=404, detail="Branch not found")

        branch_role = BranchRoleEnum.MANAGER if role_enum == UserGlobalRole.MANAGER else BranchRoleEnum.STAFF
        link = UserBranchRole(user_id=new_user.id, branch_id=branch.id, role=branch_role)
        db.add(link)
        db.commit()

    return {"message": "User registered successfully", "user_id": new_user.id}


# -------- LOGIN --------
@router.post("/login", response_model=TokenResponse)
def login_user(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # ใช้ default_branch_id ถ้ามี, ไม่งั้นดึงจาก user_branch_roles
    branch_id = user.default_branch_id
    if branch_id is None:
        ur = db.query(UserBranchRole).filter(UserBranchRole.user_id == user.id).first()
        branch_id = ur.branch_id if ur else None

    token = create_access_token({
        "sub": user.username,
        "uid": user.id,
        "global_role": user.global_role.value,
        "branch_id": branch_id,
    })
    return {"access_token": token, "token_type": "bearer"}
