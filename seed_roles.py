from database import SessionLocal, Base, engine
from models import User, UserBranchRole, GlobalRole, BranchRole
from passlib.hash import bcrypt

Base.metadata.create_all(bind=engine)
db = SessionLocal()

# สร้างผู้ใช้ตัวอย่าง
owner = User(username="owner", password_hash=bcrypt.hash("1234"), global_role=GlobalRole.OWNER)
manager = User(username="manager1", password_hash=bcrypt.hash("1234"))
staff = User(username="staff1", password_hash=bcrypt.hash("1234"))

db.add_all([owner, manager, staff])
db.commit()
db.refresh(manager)
db.refresh(staff)

# ผูก manager/staff กับ branch_id=1
db.add(UserBranchRole(user_id=manager.id, branch_id=1, role=BranchRole.MANAGER))
db.add(UserBranchRole(user_id=staff.id, branch_id=1, role=BranchRole.STAFF))
db.commit()
db.close()
