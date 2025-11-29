# permissions.py
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from database import get_db
from models import User, UserBranchRole, BranchRoleEnum as BranchRole, UserGlobalRole as GlobalRole

from auth import get_current_user

def require_branch_member(branch_id: int, min_role: Optional[BranchRole] = None):
    """
    ใช้เป็น dependency ใน endpoint ที่ต้องผูกกับ branch_id:
    - Owner: ผ่านเสมอ
    - Manager: ผ่านเฉพาะสาขาที่มีบทบาทเป็น MANAGER (และถ้า min_role=STAFF ก็ผ่านด้วย)
    - Staff: ผ่านเฉพาะสาขาที่มีบทบาทเป็น STAFF และ min_role ต้องไม่สูงกว่า STAFF
    """
    def wrapper(
        db: Session = Depends(get_db),
        user: User = Depends(get_current_user),
    ):
        if user.global_role == GlobalRole.OWNER:
            return user

        # หา role ของ user ในสาขานี้
        ur = db.query(UserBranchRole).filter(
            UserBranchRole.user_id == user.id,
            UserBranchRole.branch_id == branch_id
        ).first()

        if not ur:
            raise HTTPException(status_code=403, detail="Not a member of this branch")

        if min_role is None:
            return user

        # เทียบลำดับสิทธิ์: MANAGER > STAFF
        order = {BranchRole.MANAGER: 2, BranchRole.STAFF: 1}
        if order[ur.role] < order[min_role]:
            raise HTTPException(status_code=403, detail="Insufficient branch role")
        return user
    return wrapper
